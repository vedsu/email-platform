from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from bson import ObjectId

from models.database import get_db
from models.contact import StreamType, ContactStatus
from models.campaign import CampaignStatus
from core.auth import get_current_user, require_admin

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


class CampaignCreate(BaseModel):
    name: str
    template_id: Optional[str] = None
    subject: Optional[str] = None
    preheader: str = ""
    from_name: Optional[str] = None
    from_email: Optional[str] = None
    html_body: Optional[str] = None
    text_body: Optional[str] = None
    stream: StreamType = StreamType.COLD
    target_list_ids: list[str] = []
    scheduled_at: Optional[datetime] = None
    auto_suppress: bool = True


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    preheader: Optional[str] = None
    from_name: Optional[str] = None
    from_email: Optional[str] = None
    html_body: Optional[str] = None
    text_body: Optional[str] = None
    stream: Optional[StreamType] = None
    target_list_ids: Optional[list[str]] = None
    scheduled_at: Optional[datetime] = None
    auto_suppress: Optional[bool] = None


@router.post("")
async def create_campaign(payload: CampaignCreate, user: dict = Depends(get_current_user)):
    db = get_db()

    subject = payload.subject
    preheader = payload.preheader
    from_name = payload.from_name
    from_email = payload.from_email
    html_body = payload.html_body
    text_body = payload.text_body

    if payload.template_id:
        template = await db.templates.find_one({"_id": ObjectId(payload.template_id)})
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        subject = subject or template["subject"]
        preheader = preheader or template.get("preheader", "")
        html_body = html_body or template["html_body"]
        text_body = text_body or template.get("text_body")

    if not subject or not html_body or not from_name or not from_email:
        raise HTTPException(status_code=400, detail="subject, html_body, from_name, and from_email are required")

    doc = {
        "name": payload.name,
        "template_id": payload.template_id,
        "subject": subject,
        "preheader": preheader,
        "from_name": from_name,
        "from_email": from_email,
        "html_body": html_body,
        "text_body": text_body,
        "stream": payload.stream.value,
        "target_list_ids": payload.target_list_ids,
        "status": CampaignStatus.SCHEDULED.value if payload.scheduled_at else CampaignStatus.DRAFT.value,
        "auto_suppress": payload.auto_suppress,
        "stats": {"total_recipients": 0, "sent": 0, "delivered": 0, "opened": 0, "clicked": 0, "bounced": 0, "soft_bounced": 0, "complained": 0, "unsubscribed": 0},
        "scheduled_at": payload.scheduled_at,
        "started_at": None,
        "completed_at": None,
        "created_by": user["sub"],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    result = await db.campaigns.insert_one(doc)
    return {"id": str(result.inserted_id), "name": payload.name, "status": doc["status"]}


@router.get("")
async def list_campaigns(
    status: Optional[CampaignStatus] = None,
    stream: Optional[StreamType] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    user: dict = Depends(get_current_user),
):
    db = get_db()
    query = {}
    if status:
        query["status"] = status.value
    if stream:
        query["stream"] = stream.value
    if user.get("role") != "admin":
        query["archived"] = {"$ne": True}

    cursor = db.campaigns.find(query).skip(skip).limit(limit).sort("created_at", -1)
    campaigns = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        campaigns.append(doc)

    total = await db.campaigns.count_documents(query)
    return {"campaigns": campaigns, "total": total}


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    doc = await db.campaigns.find_one({"_id": ObjectId(campaign_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Campaign not found")
    doc["_id"] = str(doc["_id"])
    return doc


@router.put("/{campaign_id}")
async def update_campaign(campaign_id: str, payload: CampaignUpdate, user: dict = Depends(get_current_user)):
    db = get_db()
    campaign = await db.campaigns.find_one({"_id": ObjectId(campaign_id)})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign["status"] not in (CampaignStatus.DRAFT.value, CampaignStatus.SCHEDULED.value):
        raise HTTPException(status_code=400, detail="Can only edit draft or scheduled campaigns")

    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "stream" in updates:
        updates["stream"] = updates["stream"].value
    updates["updated_at"] = datetime.utcnow()

    if "scheduled_at" in updates and updates["scheduled_at"]:
        updates["status"] = CampaignStatus.SCHEDULED.value

    await db.campaigns.update_one({"_id": ObjectId(campaign_id)}, {"$set": updates})
    return {"updated": True}


@router.post("/{campaign_id}/launch")
async def launch_campaign(campaign_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    campaign = await db.campaigns.find_one({"_id": ObjectId(campaign_id)})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign["status"] not in (CampaignStatus.DRAFT.value, CampaignStatus.SCHEDULED.value):
        raise HTTPException(
            status_code=400,
            detail=f"Campaign cannot be launched from '{campaign['status']}' status",
        )

    query = {"status": ContactStatus.ACTIVE.value}
    list_ids = campaign.get("target_list_ids", [])
    # Backward compat: support old single target_list_id
    if not list_ids and campaign.get("target_list_id"):
        list_ids = [campaign["target_list_id"]]

    if list_ids:
        query["list_ids"] = {"$in": list_ids}

    total_recipients = await db.contacts.count_documents(query)
    if total_recipients == 0:
        raise HTTPException(status_code=400, detail="No active contacts match this campaign's target")

    await db.campaigns.update_one(
        {"_id": ObjectId(campaign_id)},
        {
            "$set": {
                "status": CampaignStatus.SENDING.value,
                "started_at": datetime.utcnow(),
                "stats.total_recipients": total_recipients,
            }
        },
    )

    from worker.tasks import send_to_recipient

    cursor = db.contacts.find(query, {"_id": 1})
    enqueued = 0
    async for contact in cursor:
        send_to_recipient.delay(campaign_id, str(contact["_id"]))
        enqueued += 1

    return {
        "campaign_id": campaign_id,
        "status": "sending",
        "total_recipients": total_recipients,
        "enqueued": enqueued,
    }


@router.post("/{campaign_id}/pause")
async def pause_campaign(campaign_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    result = await db.campaigns.update_one(
        {"_id": ObjectId(campaign_id), "status": CampaignStatus.SENDING.value},
        {"$set": {"status": CampaignStatus.PAUSED.value}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=400, detail="Campaign is not currently sending")
    return {"campaign_id": campaign_id, "status": "paused"}


@router.post("/{campaign_id}/resume")
async def resume_campaign(campaign_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    campaign = await db.campaigns.find_one({"_id": ObjectId(campaign_id)})
    if not campaign or campaign["status"] != CampaignStatus.PAUSED.value:
        raise HTTPException(status_code=400, detail="Campaign is not paused")

    await db.campaigns.update_one(
        {"_id": ObjectId(campaign_id)},
        {"$set": {"status": CampaignStatus.SENDING.value}},
    )

    from worker.tasks import send_to_recipient

    sent_emails = set()
    async for evt in db.events.find(
        {"campaign_id": campaign_id, "event_type": {"$in": ["sent", "bounced"]}},
        {"contact_id": 1},
    ):
        sent_emails.add(evt["contact_id"])

    query = {"status": ContactStatus.ACTIVE.value}
    list_ids = campaign.get("target_list_ids", [])
    if list_ids:
        query["list_ids"] = {"$in": list_ids}

    cursor = db.contacts.find(query, {"_id": 1})
    enqueued = 0
    async for contact in cursor:
        if str(contact["_id"]) not in sent_emails:
            send_to_recipient.delay(campaign_id, str(contact["_id"]))
            enqueued += 1

    return {"campaign_id": campaign_id, "status": "sending", "enqueued": enqueued}


@router.post("/{campaign_id}/archive")
async def archive_campaign(campaign_id: str, user: dict = Depends(get_current_user)):
    """Member soft-delete: hides from member view but stays visible to admin."""
    db = get_db()
    campaign = await db.campaigns.find_one({"_id": ObjectId(campaign_id)})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign["status"] == CampaignStatus.SENDING.value:
        raise HTTPException(status_code=400, detail="Cannot archive a sending campaign. Pause it first.")

    await db.campaigns.update_one(
        {"_id": ObjectId(campaign_id)},
        {"$set": {"archived": True, "archived_by": user["sub"], "updated_at": datetime.utcnow()}},
    )
    return {"campaign_id": campaign_id, "archived": True}


@router.delete("/{campaign_id}")
async def delete_campaign(campaign_id: str, admin: dict = Depends(require_admin)):
    """Admin permanent delete: removes campaign and its events."""
    db = get_db()
    campaign = await db.campaigns.find_one({"_id": ObjectId(campaign_id)})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign["status"] == CampaignStatus.SENDING.value:
        raise HTTPException(status_code=400, detail="Cannot delete a sending campaign. Pause it first.")

    await db.events.delete_many({"campaign_id": campaign_id})
    await db.campaigns.delete_one({"_id": ObjectId(campaign_id)})
    return {"deleted": True, "events_deleted": True}
