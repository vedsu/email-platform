import csv
import io
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, Query
from fastapi.responses import StreamingResponse

from models.database import get_db
from core.auth import get_current_user
from core.s3_client import upload_file

router = APIRouter(prefix="/csv", tags=["csv"])


@router.post("/import-contacts")
async def csv_import_contacts(
    file: UploadFile = File(...),
    stream: str = Form("cold"),
    list_id: Optional[str] = Form(None),
    user: dict = Depends(get_current_user),
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    db = get_db()
    imported = 0
    skipped = 0
    errors = []

    for row in reader:
        email = row.get("email", "").strip().lower()
        if not email:
            continue

        doc = {
            "email": email,
            "first_name": row.get("first_name", row.get("first name", "")).strip(),
            "last_name": row.get("last_name", row.get("last name", "")).strip(),
            "attributes": {k: v for k, v in row.items() if k not in ("email", "first_name", "last_name", "first name", "last name")},
            "stream": stream,
            "status": "active",
            "source": "import",
            "list_ids": [list_id] if list_id else [],
            "engagement": {
                "last_sent_at": None, "last_opened_at": None, "last_clicked_at": None,
                "total_sent": 0, "total_opened": 0, "total_clicked": 0,
            },
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        try:
            await db.contacts.insert_one(doc)
            imported += 1
        except Exception as e:
            if "duplicate key" in str(e):
                skipped += 1
            else:
                errors.append(f"{email}: {str(e)}")

    if list_id:
        from bson import ObjectId
        count = await db.contacts.count_documents({"list_ids": list_id})
        await db.lists.update_one({"_id": ObjectId(list_id)}, {"$set": {"contact_count": count}})

    return {"imported": imported, "skipped": skipped, "errors": errors[:50]}


@router.get("/export-contacts")
async def csv_export_contacts(
    stream: Optional[str] = None,
    status: Optional[str] = None,
    list_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    db = get_db()
    query = {}
    if stream:
        query["stream"] = stream
    if status:
        query["status"] = status
    if list_id:
        query["list_ids"] = list_id

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["email", "first_name", "last_name", "stream", "status", "total_sent", "total_opened", "total_clicked", "created_at"])

    async for doc in db.contacts.find(query).sort("created_at", -1):
        eng = doc.get("engagement", {})
        writer.writerow([
            doc.get("email", ""),
            doc.get("first_name", ""),
            doc.get("last_name", ""),
            doc.get("stream", ""),
            doc.get("status", ""),
            eng.get("total_sent", 0),
            eng.get("total_opened", 0),
            eng.get("total_clicked", 0),
            doc.get("created_at", ""),
        ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=contacts_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"},
    )


@router.get("/export-campaign/{campaign_id}")
async def csv_export_campaign_report(campaign_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    campaign = await db.campaigns.find_one({"_id": __import__("bson").ObjectId(campaign_id)})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["email", "event_type", "stream", "bounce_type", "bounce_message", "click_url", "timestamp"])

    async for doc in db.events.find({"campaign_id": campaign_id}).sort("created_at", 1):
        writer.writerow([
            doc.get("email", ""),
            doc.get("event_type", ""),
            doc.get("stream", ""),
            doc.get("bounce_type", ""),
            doc.get("bounce_message", ""),
            doc.get("click_url", ""),
            doc.get("created_at", ""),
        ])

    output.seek(0)
    filename = f"campaign_{campaign['name'].replace(' ', '_')}_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/export-suppressions")
async def csv_export_suppressions(user: dict = Depends(get_current_user)):
    db = get_db()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["email", "reason", "source", "campaign_id", "created_at"])

    async for doc in db.suppressions.find().sort("created_at", -1):
        writer.writerow([
            doc.get("email", ""),
            doc.get("reason", ""),
            doc.get("source", ""),
            doc.get("campaign_id", ""),
            doc.get("created_at", ""),
        ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=suppressions_{datetime.utcnow().strftime('%Y%m%d')}.csv"},
    )


@router.get("/export-bounces")
async def csv_export_bounces(user: dict = Depends(get_current_user)):
    db = get_db()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["email", "bounce_type", "bounce_message", "campaign_id", "stream", "timestamp"])

    async for doc in db.events.find({"event_type": "bounced"}).sort("created_at", -1):
        writer.writerow([
            doc.get("email", ""),
            doc.get("bounce_type", ""),
            doc.get("bounce_message", ""),
            doc.get("campaign_id", ""),
            doc.get("stream", ""),
            doc.get("created_at", ""),
        ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=bounces_{datetime.utcnow().strftime('%Y%m%d')}.csv"},
    )


@router.post("/export-to-s3/{export_type}")
async def export_to_s3(export_type: str, user: dict = Depends(get_current_user)):
    db = get_db()
    output = io.StringIO()
    writer = csv.writer(output)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    if export_type == "contacts":
        writer.writerow(["email", "first_name", "last_name", "stream", "status", "total_sent", "total_opened"])
        async for doc in db.contacts.find().sort("created_at", -1):
            eng = doc.get("engagement", {})
            writer.writerow([doc.get("email"), doc.get("first_name"), doc.get("last_name"), doc.get("stream"), doc.get("status"), eng.get("total_sent", 0), eng.get("total_opened", 0)])

    elif export_type == "suppressions":
        writer.writerow(["email", "reason", "source", "created_at"])
        async for doc in db.suppressions.find().sort("created_at", -1):
            writer.writerow([doc.get("email"), doc.get("reason"), doc.get("source"), doc.get("created_at")])

    else:
        raise HTTPException(status_code=400, detail="export_type must be 'contacts' or 'suppressions'")

    key = f"exports/{export_type}_{timestamp}.csv"
    url = upload_file(output.getvalue().encode(), key)

    return {"status": "exported", "url": url, "key": key}
