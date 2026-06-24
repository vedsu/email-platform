from typing import Optional
from fastapi import APIRouter, Query

from models.database import get_db
from models.event import EventType

router = APIRouter(prefix="/events", tags=["events"])


@router.get("")
async def list_events(
    campaign_id: Optional[str] = None,
    contact_id: Optional[str] = None,
    email: Optional[str] = None,
    event_type: Optional[EventType] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    db = get_db()
    query = {}
    if campaign_id:
        query["campaign_id"] = campaign_id
    if contact_id:
        query["contact_id"] = contact_id
    if email:
        query["email"] = email
    if event_type:
        query["event_type"] = event_type.value

    cursor = db.events.find(query).skip(skip).limit(limit).sort("created_at", -1)
    events = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        events.append(doc)

    total = await db.events.count_documents(query)
    return {"events": events, "total": total}


@router.get("/stats/{campaign_id}")
async def campaign_stats(campaign_id: str):
    db = get_db()
    pipeline = [
        {"$match": {"campaign_id": campaign_id}},
        {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
    ]
    stats = {}
    async for doc in db.events.aggregate(pipeline):
        stats[doc["_id"]] = doc["count"]

    return {"campaign_id": campaign_id, "stats": stats}
