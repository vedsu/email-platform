import csv
import io
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel, EmailStr

from models.database import get_db
from models.suppression import Suppression, SuppressionReason

router = APIRouter(prefix="/suppressions", tags=["suppressions"])


class SuppressionCreate(BaseModel):
    email: EmailStr
    reason: SuppressionReason
    source: Optional[str] = None


class BulkSuppressionCreate(BaseModel):
    emails: list[str]
    reason: SuppressionReason = SuppressionReason.MANUAL
    source: Optional[str] = None


@router.post("")
async def add_suppression(payload: SuppressionCreate):
    db = get_db()
    suppression = Suppression(**payload.model_dump())
    try:
        await db.suppressions.insert_one(suppression.model_dump())
    except Exception as e:
        if "duplicate key" in str(e):
            raise HTTPException(status_code=409, detail="Email already suppressed")
        raise

    await db.contacts.update_one(
        {"email": payload.email},
        {"$set": {"status": "suppressed"}},
    )

    return {"suppressed": payload.email, "reason": payload.reason}


@router.get("")
async def list_suppressions(
    reason: Optional[SuppressionReason] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    db = get_db()
    query = {}
    if reason:
        query["reason"] = reason.value

    cursor = db.suppressions.find(query).skip(skip).limit(limit).sort("created_at", -1)
    suppressions = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        suppressions.append(doc)

    total = await db.suppressions.count_documents(query)
    return {"suppressions": suppressions, "total": total}


@router.get("/check/{email}")
async def check_suppression(email: str):
    db = get_db()
    doc = await db.suppressions.find_one({"email": email})
    return {"email": email, "suppressed": doc is not None, "reason": doc["reason"] if doc else None}


@router.delete("/{email}")
async def remove_suppression(email: str):
    db = get_db()
    result = await db.suppressions.delete_one({"email": email})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Email not in suppression list")

    await db.contacts.update_one(
        {"email": email, "status": "suppressed"},
        {"$set": {"status": "active"}},
    )

    return {"removed": email}


@router.post("/bulk")
async def bulk_suppress(payload: BulkSuppressionCreate):
    db = get_db()
    added = 0
    skipped = 0
    now = datetime.utcnow()

    for email in payload.emails:
        email = email.strip().lower()
        if not email or "@" not in email:
            continue
        try:
            await db.suppressions.insert_one({
                "email": email,
                "reason": payload.reason.value,
                "source": payload.source or "bulk_upload",
                "campaign_id": None,
                "created_at": now,
            })
            await db.contacts.update_one({"email": email}, {"$set": {"status": "suppressed"}})
            added += 1
        except Exception as e:
            if "duplicate key" in str(e):
                skipped += 1

    return {"added": added, "skipped": skipped, "total": len(payload.emails)}


@router.post("/bulk-csv")
async def bulk_suppress_csv(
    file: UploadFile = File(...),
    reason: str = Form("manual"),
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    db = get_db()
    added = 0
    skipped = 0
    now = datetime.utcnow()

    for row in reader:
        email = row.get("email", "").strip().lower()
        if not email or "@" not in email:
            continue
        try:
            await db.suppressions.insert_one({
                "email": email,
                "reason": reason,
                "source": "csv_upload",
                "campaign_id": None,
                "created_at": now,
            })
            await db.contacts.update_one({"email": email}, {"$set": {"status": "suppressed"}})
            added += 1
        except Exception as e:
            if "duplicate key" in str(e):
                skipped += 1

    return {"added": added, "skipped": skipped}
