from datetime import datetime
from fastapi import APIRouter, Depends
import redis as redis_lib

from models.database import get_db
from core.config import settings
from core.auth import require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/system-health")
async def system_health(admin: dict = Depends(require_admin)):
    db = get_db()

    mongo_ok = False
    try:
        r = await db.command("ping")
        mongo_ok = r.get("ok") == 1.0
    except Exception:
        pass

    redis_ok = False
    try:
        r = redis_lib.from_url(settings.redis_uri)
        redis_ok = r.ping()
    except Exception:
        pass

    postal_ok = False
    try:
        import httpx
        resp = httpx.get(f"{settings.postal_api_url}", timeout=5)
        postal_ok = resp.status_code in (200, 301, 302, 403)
    except Exception:
        pass

    collections = {}
    for name in ["contacts", "campaigns", "events", "suppressions", "users", "templates", "domains", "ip_pools", "ip_addresses"]:
        collections[name] = await db[name].count_documents({})

    return {
        "services": {
            "mongodb": "connected" if mongo_ok else "disconnected",
            "redis": "connected" if redis_ok else "disconnected",
            "postal": "reachable" if postal_ok else "unreachable",
        },
        "collections": collections,
    }


@router.get("/per-user-stats")
async def per_user_stats(admin: dict = Depends(require_admin)):
    db = get_db()

    users = []
    async for user in db.users.find({}, {"password_hash": 0}):
        user_id = str(user["_id"])
        campaigns = await db.campaigns.count_documents({"created_by": user_id})
        templates = await db.templates.count_documents({"created_by": user_id})

        sent_pipeline = [
            {"$match": {"created_by": user_id}},
            {"$group": {"_id": None, "total_sent": {"$sum": "$stats.sent"}, "total_opened": {"$sum": "$stats.opened"}, "total_bounced": {"$sum": "$stats.bounced"}}},
        ]
        send_stats = {}
        async for doc in db.campaigns.aggregate(sent_pipeline):
            doc.pop("_id")
            send_stats = doc

        users.append({
            "id": user_id,
            "email": user.get("email"),
            "name": user.get("name"),
            "role": user.get("role"),
            "campaigns": campaigns,
            "templates": templates,
            "total_sent": send_stats.get("total_sent", 0),
            "total_opened": send_stats.get("total_opened", 0),
            "total_bounced": send_stats.get("total_bounced", 0),
        })

    return {"users": users}


@router.get("/audit-log")
async def audit_log(admin: dict = Depends(require_admin)):
    db = get_db()

    recent_campaigns = []
    async for c in db.campaigns.find().sort("created_at", -1).limit(10):
        recent_campaigns.append({
            "name": c["name"],
            "status": c["status"],
            "created_by": c.get("created_by"),
            "created_at": c.get("created_at"),
            "started_at": c.get("started_at"),
        })

    recent_logins = []
    async for u in db.users.find({"last_login_at": {"$ne": None}}).sort("last_login_at", -1).limit(10):
        recent_logins.append({
            "email": u["email"],
            "name": u["name"],
            "last_login_at": u["last_login_at"],
        })

    return {
        "recent_campaigns": recent_campaigns,
        "recent_logins": recent_logins,
    }


@router.post("/backfill-hard-bounces")
async def backfill_hard_bounces(admin: dict = Depends(require_admin)):
    """
    Scan the events collection for hard bounce events and add those emails
    to the suppression list. Safe to run multiple times (skips duplicates).
    """
    db = get_db()

    # Match events that were hard bounces — use raw_event name as ground truth
    # because old code sometimes misclassified bounce_type
    hard_bounce_query = {
        "event_type": "bounced",
        "$or": [
            {"bounce_type": "hard"},
            {"metadata.raw_event": {"$in": ["MessageBounced", "MessageDeliveryFailed"]}},
        ],
    }

    emails = set()
    async for evt in db.events.find(hard_bounce_query, {"email": 1, "campaign_id": 1}):
        if evt.get("email"):
            emails.add((evt["email"], evt.get("campaign_id", "")))

    added = 0
    skipped = 0
    now = datetime.utcnow()

    for email, campaign_id in emails:
        try:
            await db.suppressions.insert_one({
                "email": email,
                "reason": "hard_bounce",
                "source": "backfill",
                "campaign_id": campaign_id or None,
                "created_at": now,
            })
            await db.contacts.update_one(
                {"email": email},
                {"$set": {"status": "suppressed", "updated_at": now}},
            )
            added += 1
        except Exception as e:
            if "duplicate key" in str(e):
                skipped += 1
            else:
                raise

    return {"added": added, "already_suppressed": skipped, "total_hard_bounces_in_events": len(emails)}
