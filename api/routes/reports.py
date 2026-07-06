from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from bson import ObjectId

from models.database import get_db
from core.auth import get_current_user

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/campaign/{campaign_id}")
async def campaign_report(campaign_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    campaign = await db.campaigns.find_one({"_id": ObjectId(campaign_id)})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    event_pipeline = [
        {"$match": {"campaign_id": campaign_id}},
        {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
    ]
    event_counts = {}
    async for doc in db.events.aggregate(event_pipeline):
        event_counts[doc["_id"]] = doc["count"]

    stats = campaign["stats"]
    # Base rates on sent (emails that left) not total_recipients (includes skipped)
    sent = stats.get("sent", 0) or 1

    skipped = event_counts.get("skipped", 0)

    return {
        "campaign_id": campaign_id,
        "name": campaign["name"],
        "stream": campaign.get("stream"),
        "status": campaign["status"],
        "started_at": campaign.get("started_at"),
        "completed_at": campaign.get("completed_at"),
        "stats": {**stats, "skipped": skipped},
        "rates": {
            "delivery_rate": f"{(stats.get('delivered', 0) / sent) * 100:.1f}%",
            "open_rate": f"{(stats.get('opened', 0) / sent) * 100:.1f}%",
            "click_rate": f"{(stats.get('clicked', 0) / sent) * 100:.1f}%",
            "bounce_rate": f"{(stats.get('bounced', 0) / sent) * 100:.1f}%",
            "complaint_rate": f"{(stats.get('complained', 0) / sent) * 100:.1f}%",
            "unsubscribe_rate": f"{(stats.get('unsubscribed', 0) / sent) * 100:.1f}%",
        },
        "event_counts": event_counts,
    }


@router.get("/campaign/{campaign_id}/recipients")
async def campaign_recipients(
    campaign_id: str,
    event_type: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    user: dict = Depends(get_current_user),
):
    db = get_db()
    query = {"campaign_id": campaign_id}
    if event_type:
        query["event_type"] = event_type

    cursor = db.events.find(query).skip(skip).limit(limit).sort("created_at", -1)
    events = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        events.append(doc)

    total = await db.events.count_documents(query)
    return {"events": events, "total": total}


@router.get("/contact/{email}")
async def contact_report(email: str, user: dict = Depends(get_current_user)):
    db = get_db()
    contact = await db.contacts.find_one({"email": email})
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    event_pipeline = [
        {"$match": {"email": email}},
        {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
    ]
    event_counts = {}
    async for doc in db.events.aggregate(event_pipeline):
        event_counts[doc["_id"]] = doc["count"]

    recent_events = []
    cursor = db.events.find({"email": email}).sort("created_at", -1).limit(50)
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        recent_events.append(doc)

    suppression = await db.suppressions.find_one({"email": email})

    contact["_id"] = str(contact["_id"])
    return {
        "contact": contact,
        "event_summary": event_counts,
        "recent_events": recent_events,
        "suppressed": suppression is not None,
        "suppression_reason": suppression["reason"] if suppression else None,
    }


@router.get("/overview")
async def global_report(user: dict = Depends(get_current_user)):
    db = get_db()

    total_sent_pipeline = [
        {"$group": {
            "_id": None,
            "total_sent": {"$sum": "$stats.sent"},
            "total_delivered": {"$sum": "$stats.delivered"},
            "total_opened": {"$sum": "$stats.opened"},
            "total_clicked": {"$sum": "$stats.clicked"},
            "total_bounced": {"$sum": "$stats.bounced"},
            "total_complained": {"$sum": "$stats.complained"},
        }}
    ]
    global_stats = {}
    async for doc in db.campaigns.aggregate(total_sent_pipeline):
        doc.pop("_id")
        global_stats = doc

    total = global_stats.get("total_sent", 1) or 1

    stream_pipeline = [
        {"$group": {
            "_id": "$stream",
            "sent": {"$sum": "$stats.sent"},
            "opened": {"$sum": "$stats.opened"},
            "bounced": {"$sum": "$stats.bounced"},
            "campaigns": {"$sum": 1},
        }}
    ]
    by_stream = {}
    async for doc in db.campaigns.aggregate(stream_pipeline):
        stream = doc.pop("_id")
        by_stream[stream] = doc

    return {
        "global": global_stats,
        "rates": {
            "delivery_rate": f"{(global_stats.get('total_delivered', 0) / total) * 100:.1f}%",
            "open_rate": f"{(global_stats.get('total_opened', 0) / total) * 100:.1f}%",
            "click_rate": f"{(global_stats.get('total_clicked', 0) / total) * 100:.1f}%",
            "bounce_rate": f"{(global_stats.get('total_bounced', 0) / total) * 100:.1f}%",
            "complaint_rate": f"{(global_stats.get('total_complained', 0) / total) * 100:.1f}%",
        },
        "by_stream": by_stream,
        "total_contacts": await db.contacts.count_documents({}),
        "active_contacts": await db.contacts.count_documents({"status": "active"}),
        "total_suppressions": await db.suppressions.count_documents({}),
    }
