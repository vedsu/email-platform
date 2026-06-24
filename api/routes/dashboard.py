from fastapi import APIRouter
from models.database import get_db

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview")
async def overview():
    db = get_db()

    total_contacts = await db.contacts.count_documents({})
    active_contacts = await db.contacts.count_documents({"status": "active"})
    suppressed_contacts = await db.suppressions.count_documents({})
    total_campaigns = await db.campaigns.count_documents({})
    total_events = await db.events.count_documents({})

    stream_pipeline = [
        {"$match": {"status": "active"}},
        {"$group": {"_id": "$stream", "count": {"$sum": 1}}},
    ]
    stream_counts = {}
    async for doc in db.contacts.aggregate(stream_pipeline):
        stream_counts[doc["_id"]] = doc["count"]

    return {
        "contacts": {
            "total": total_contacts,
            "active": active_contacts,
            "suppressed": suppressed_contacts,
            "by_stream": stream_counts,
        },
        "campaigns": {"total": total_campaigns},
        "events": {"total": total_events},
    }


@router.get("/stream/{stream}")
async def stream_stats(stream: str):
    db = get_db()

    contacts = await db.contacts.count_documents({"stream": stream, "status": "active"})

    event_pipeline = [
        {"$match": {"stream": stream}},
        {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
    ]
    event_stats = {}
    async for doc in db.events.aggregate(event_pipeline):
        event_stats[doc["_id"]] = doc["count"]

    campaign_pipeline = [
        {"$match": {"stream": stream}},
        {"$group": {
            "_id": None,
            "total": {"$sum": 1},
            "sent": {"$sum": "$stats.sent"},
            "delivered": {"$sum": "$stats.delivered"},
            "opened": {"$sum": "$stats.opened"},
            "clicked": {"$sum": "$stats.clicked"},
            "bounced": {"$sum": "$stats.bounced"},
        }},
    ]
    campaign_stats = {}
    async for doc in db.campaigns.aggregate(campaign_pipeline):
        doc.pop("_id", None)
        campaign_stats = doc

    return {
        "stream": stream,
        "active_contacts": contacts,
        "events": event_stats,
        "campaigns": campaign_stats,
    }


@router.get("/suppression-breakdown")
async def suppression_breakdown():
    db = get_db()
    pipeline = [
        {"$group": {"_id": "$reason", "count": {"$sum": 1}}},
    ]
    breakdown = {}
    async for doc in db.suppressions.aggregate(pipeline):
        breakdown[doc["_id"]] = doc["count"]

    return {"total": sum(breakdown.values()), "by_reason": breakdown}
