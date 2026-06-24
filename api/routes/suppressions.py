from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, EmailStr

from models.database import get_db
from models.suppression import Suppression, SuppressionReason

router = APIRouter(prefix="/suppressions", tags=["suppressions"])


class SuppressionCreate(BaseModel):
    email: EmailStr
    reason: SuppressionReason
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
