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
        postal_ok = resp.status_code in (200, 301, 302)
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
