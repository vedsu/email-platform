from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from bson import ObjectId

from models.database import get_db
from models.contact import StreamType, ContactStatus
from models.campaign import Campaign, CampaignStatus

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


class CampaignCreate(BaseModel):
    name: str
    subject: str
    from_name: str
    from_email: str
    html_body: str
    text_body: Optional[str] = None
    stream: StreamType = StreamType.COLD
    target_list_id: Optional[str] = None


@router.post("")
async def create_campaign(payload: CampaignCreate):
    db = get_db()
    campaign = Campaign(**payload.model_dump())
    result = await db.campaigns.insert_one(campaign.model_dump())
    return {"id": str(result.inserted_id), "name": payload.name, "status": "draft"}


@router.get("")
async def list_campaigns(
    status: Optional[CampaignStatus] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
):
    db = get_db()
    query = {}
    if status:
        query["status"] = status.value

    cursor = db.campaigns.find(query).skip(skip).limit(limit).sort("created_at", -1)
    campaigns = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        campaigns.append(doc)

    total = await db.campaigns.count_documents(query)
    return {"campaigns": campaigns, "total": total}


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: str):
    db = get_db()
    doc = await db.campaigns.find_one({"_id": ObjectId(campaign_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Campaign not found")
    doc["_id"] = str(doc["_id"])
    return doc


@router.post("/{campaign_id}/launch")
async def launch_campaign(campaign_id: str):
    db = get_db()
    campaign = await db.campaigns.find_one({"_id": ObjectId(campaign_id)})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign["status"] != CampaignStatus.DRAFT.value:
        raise HTTPException(
            status_code=400,
            detail=f"Campaign cannot be launched from '{campaign['status']}' status",
        )

    query = {"status": ContactStatus.ACTIVE.value}
    if campaign.get("target_list_id"):
        query["list_ids"] = campaign["target_list_id"]

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
async def pause_campaign(campaign_id: str):
    db = get_db()
    result = await db.campaigns.update_one(
        {"_id": ObjectId(campaign_id), "status": CampaignStatus.SENDING.value},
        {"$set": {"status": CampaignStatus.PAUSED.value}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=400, detail="Campaign is not currently sending")
    return {"campaign_id": campaign_id, "status": "paused"}
