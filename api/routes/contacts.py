from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, EmailStr

from models.database import get_db
from models.contact import Contact, StreamType, ContactSource, ContactStatus

router = APIRouter(prefix="/contacts", tags=["contacts"])


class ContactCreate(BaseModel):
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    attributes: dict = {}
    stream: StreamType = StreamType.COLD
    source: ContactSource = ContactSource.IMPORT
    list_ids: list[str] = []


class ContactImport(BaseModel):
    contacts: list[ContactCreate]


class ContactImportResult(BaseModel):
    imported: int
    skipped: int
    errors: list[str]


@router.post("/import", response_model=ContactImportResult)
async def import_contacts(payload: ContactImport):
    db = get_db()
    imported = 0
    skipped = 0
    errors = []

    for item in payload.contacts:
        contact = Contact(**item.model_dump())
        try:
            await db.contacts.insert_one(contact.model_dump())
            imported += 1
        except Exception as e:
            if "duplicate key" in str(e):
                skipped += 1
            else:
                errors.append(f"{item.email}: {str(e)}")

    return ContactImportResult(imported=imported, skipped=skipped, errors=errors)


@router.get("")
async def list_contacts(
    stream: Optional[StreamType] = None,
    status: Optional[ContactStatus] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
):
    db = get_db()
    query = {}
    if stream:
        query["stream"] = stream.value
    if status:
        query["status"] = status.value

    cursor = db.contacts.find(query).skip(skip).limit(limit).sort("created_at", -1)
    contacts = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        contacts.append(doc)

    total = await db.contacts.count_documents(query)
    return {"contacts": contacts, "total": total, "skip": skip, "limit": limit}


@router.get("/{email}")
async def get_contact(email: str):
    db = get_db()
    doc = await db.contacts.find_one({"email": email})
    if not doc:
        raise HTTPException(status_code=404, detail="Contact not found")
    doc["_id"] = str(doc["_id"])
    return doc


@router.patch("/{email}")
async def update_contact(email: str, updates: dict):
    db = get_db()
    updates["updated_at"] = datetime.utcnow()
    result = await db.contacts.update_one({"email": email}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Contact not found")
    return {"updated": True}


@router.delete("/{email}")
async def delete_contact(email: str):
    db = get_db()
    result = await db.contacts.delete_one({"email": email})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Contact not found")
    return {"deleted": True}
