import csv
import io
from typing import Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from models.database import get_db
from core.cleaning import clean_email
from core.suppression import add_suppression

router = APIRouter(prefix="/cleaning", tags=["cleaning"])


class CleanRequest(BaseModel):
    emails: list[str]
    suppress_invalid: bool = False


class CleanSingleRequest(BaseModel):
    email: str


@router.post("/verify")
async def verify_email(payload: CleanSingleRequest):
    return clean_email(payload.email)


@router.post("/bulk")
async def bulk_clean(payload: CleanRequest):
    results = {"valid": [], "invalid_syntax": [], "no_mx": [], "disposable": [], "role": [], "duplicate": []}

    seen = set()
    for email in payload.emails:
        email = email.strip().lower()
        if email in seen:
            results["duplicate"].append(email)
            continue
        seen.add(email)

        result = clean_email(email)
        verdict = result["verdict"]

        if verdict == "valid":
            results["valid"].append(email)
        else:
            results[verdict].append(email)
            if payload.suppress_invalid and verdict in ("no_mx", "disposable"):
                add_suppression(email, "manual", source=f"cleaning_{verdict}")

    summary = {k: len(v) for k, v in results.items()}
    return {"summary": summary, "details": results}


@router.post("/clean-list/{list_id}")
async def clean_list(list_id: str, suppress_invalid: bool = False):
    from bson import ObjectId

    db = get_db()
    lst = await db.lists.find_one({"_id": ObjectId(list_id)})
    if not lst:
        raise HTTPException(status_code=404, detail="List not found")

    cursor = db.contacts.find({"list_ids": list_id}, {"email": 1})
    emails = [doc["email"] async for doc in cursor]

    if not emails:
        return {"summary": {"total": 0}, "details": {}}

    payload = CleanRequest(emails=emails, suppress_invalid=suppress_invalid)
    return await bulk_clean(payload)


@router.post("/bulk-csv")
async def bulk_clean_csv(
    file: UploadFile = File(...),
    suppress_invalid: bool = Form(False),
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    emails = []
    for row in reader:
        email = row.get("email", "").strip().lower()
        if email and "@" in email:
            emails.append(email)

    if not emails:
        raise HTTPException(status_code=400, detail="No valid emails found in CSV")

    payload = CleanRequest(emails=emails, suppress_invalid=suppress_invalid)
    return await bulk_clean(payload)
