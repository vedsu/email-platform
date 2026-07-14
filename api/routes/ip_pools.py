import asyncio
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from models.database import get_db
from core.auth import get_current_user
from core.config import settings
from core.postal_mariadb import postal_sql as _postal_sql

router = APIRouter(prefix="/ip-pools", tags=["ip-pools"])

POOL_NAMES = ["optin", "engaged", "cold", "inactive", "default"]


# ---------------------------------------------------------------------------
# Live Postal data
# ---------------------------------------------------------------------------

@router.get("/postal-live")
async def postal_live(user: dict = Depends(get_current_user)):
    """Pools, IPs, queue counts, and delivery summary from Postal MariaDB."""

    def _fetch():
        # Pools
        pool_rows = _postal_sql("SELECT id, name FROM ip_pools ORDER BY id;")
        pools = {}
        for r in pool_rows:
            pools[r[0]] = {"id": int(r[0]), "name": r[1], "ips": [], "domains": [], "queued": 0}

        # IPs with pool name
        ip_rows = _postal_sql(
            "SELECT ia.id, ia.ipv4, ia.hostname, ia.ip_pool_id, p.name "
            "FROM ip_addresses ia LEFT JOIN ip_pools p ON ia.ip_pool_id = p.id "
            "ORDER BY ia.ip_pool_id, ia.id;"
        )
        ips = []
        for r in ip_rows:
            ip_id, ipv4, hostname, pool_id, pool_name = r
            ips.append({
                "id": int(ip_id),
                "ipv4": ipv4,
                "hostname": hostname or "",
                "pool_id": int(pool_id) if pool_id and pool_id != "NULL" else None,
                "pool_name": pool_name or "unassigned",
                "queued": 0,
            })
            if pool_id and pool_id in pools:
                pools[pool_id]["ips"].append(ipv4)

        # Current queue per IP
        try:
            q_rows = _postal_sql(
                "SELECT ip_address_id, COUNT(*) FROM queued_messages "
                "WHERE ip_address_id IS NOT NULL GROUP BY ip_address_id;"
            )
            q_map = {int(r[0]): int(r[1]) for r in q_rows}
            for ip in ips:
                ip["queued"] = q_map.get(ip["id"], 0)
                if ip["pool_id"]:
                    pools.get(str(ip["pool_id"]), {})["queued"] = (
                        pools.get(str(ip["pool_id"]), {}).get("queued", 0) + ip["queued"]
                    )
        except Exception:
            pass

        # Domain routing rules
        try:
            rule_rows = _postal_sql("SELECT ip_pool_id, from_text FROM ip_pool_rules ORDER BY ip_pool_id;")
            for r in rule_rows:
                pid = r[0]
                if pid in pools:
                    pools[pid]["domains"].append(r[1])
        except Exception:
            pass

        # Delivery status summary (all-time)
        try:
            stat_rows = _postal_sql(
                "SELECT status, COUNT(*) FROM deliveries GROUP BY status;",
                db=settings.postal_message_db,
            )
            delivery_stats = {r[0]: int(r[1]) for r in stat_rows}
        except Exception:
            delivery_stats = {}

        return {"pools": list(pools.values()), "ips": ips, "delivery_stats": delivery_stats}

    return await asyncio.to_thread(_fetch)


@router.get("/postal-errors")
async def postal_errors(limit: int = 100, user: dict = Depends(get_current_user)):
    """Recent SoftFail / HardFail / Bounced deliveries from Postal."""

    def _fetch():
        rows = _postal_sql(
            f"SELECT d.status, d.output, d.code, "
            f"FROM_UNIXTIME(d.timestamp) AS sent_at, m.rcpt_to, m.mail_from, m.tag "
            f"FROM deliveries d JOIN messages m ON d.message_id = m.id "
            f"WHERE d.status IN ('SoftFail','HardFail','Bounced') "
            f"ORDER BY d.timestamp DESC LIMIT {min(int(limit), 500)};",
            db=settings.postal_message_db,
        )
        return [
            {"status": r[0], "output": r[1], "code": r[2],
             "sent_at": r[3], "rcpt_to": r[4], "mail_from": r[5], "tag": r[6]}
            for r in rows
        ]

    return {"errors": await asyncio.to_thread(_fetch)}


# ---------------------------------------------------------------------------
# Move Postal IP to a different pool
# ---------------------------------------------------------------------------

class PoolMove(BaseModel):
    pool_id: int


@router.put("/postal-ip/{ip_id}/pool")
async def move_postal_ip_pool(ip_id: int, payload: PoolMove, user: dict = Depends(get_current_user)):
    """Move a Postal IP address to a different pool (updates Postal MariaDB)."""

    def _update():
        pool_rows = _postal_sql(f"SELECT id, name FROM ip_pools WHERE id = {int(payload.pool_id)};")
        if not pool_rows:
            raise ValueError(f"Pool {payload.pool_id} not found in Postal")
        pool_name = pool_rows[0][1]
        _postal_sql(f"UPDATE ip_addresses SET ip_pool_id = {int(payload.pool_id)} WHERE id = {int(ip_id)};")
        return pool_name

    try:
        pool_name = await asyncio.to_thread(_update)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"moved": True, "ip_id": ip_id, "pool_id": payload.pool_id, "pool_name": pool_name}


# ---------------------------------------------------------------------------
# CRM stream stats (MongoDB events, last 7 days)
# ---------------------------------------------------------------------------

@router.get("/crm-stats")
async def crm_stream_stats(user: dict = Depends(get_current_user)):
    """Aggregate sent/delivered/bounced/opened/clicked per stream from CRM events."""
    db = get_db()
    since = datetime.utcnow() - timedelta(days=7)
    stats: dict[str, dict[str, int]] = {}
    async for doc in db.events.aggregate([
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {"_id": {"type": "$event_type", "stream": "$stream"}, "cnt": {"$sum": 1}}},
    ]):
        stream = doc["_id"].get("stream") or "unknown"
        event_type = doc["_id"].get("type", "")
        if stream not in stats:
            stats[stream] = {}
        stats[stream][event_type] = doc["cnt"]
    return {"stats": stats, "since": since.isoformat()}


# ---------------------------------------------------------------------------
# Overview (kept for backwards-compat, now reads from Postal DB)
# ---------------------------------------------------------------------------

@router.get("/overview")
async def ip_overview(user: dict = Depends(get_current_user)):
    def _fetch():
        ip_rows = _postal_sql("SELECT COUNT(*) FROM ip_addresses;")
        pool_rows = _postal_sql("SELECT COUNT(*) FROM ip_pools;")
        return {
            "total_ips": int(ip_rows[0][0]) if ip_rows else 0,
            "total_pools": int(pool_rows[0][0]) if pool_rows else 0,
        }

    return await asyncio.to_thread(_fetch)


# ---------------------------------------------------------------------------
# Per-IP hard bounce breakdown (CRM events, requires sending_ip in events)
# ---------------------------------------------------------------------------

@router.get("/ip-bounce-stats")
async def ip_bounce_stats(days: int = 7, user: dict = Depends(get_current_user)):
    """Hard bounce and sent counts grouped by sending_ip (last N days)."""
    db = get_db()
    since = datetime.utcnow() - timedelta(days=days)

    bounce_pipeline = [
        {"$match": {"event_type": "bounced", "bounce_type": "hard", "created_at": {"$gte": since}}},
        {"$group": {
            "_id": {
                "sending_ip": {"$ifNull": ["$sending_ip", "__unknown__"]},
                "ip_pool_name": {"$ifNull": ["$ip_pool_name", ""]},
                "ip_pool_id": {"$ifNull": ["$ip_pool_id", None]},
            },
            "hard_bounces": {"$sum": 1},
        }},
        {"$sort": {"hard_bounces": -1}},
    ]

    bounces_by_ip = []
    async for doc in db.events.aggregate(bounce_pipeline):
        ip = doc["_id"]["sending_ip"]
        bounces_by_ip.append({
            "sending_ip": None if ip == "__unknown__" else ip,
            "ip_pool_name": doc["_id"]["ip_pool_name"] or None,
            "ip_pool_id": doc["_id"]["ip_pool_id"],
            "hard_bounces": doc["hard_bounces"],
        })

    sent_pipeline = [
        {"$match": {"event_type": "sent", "created_at": {"$gte": since}}},
        {"$group": {
            "_id": {"$ifNull": ["$sending_ip", "__unknown__"]},
            "sent": {"$sum": 1},
        }},
    ]
    sent_by_ip: dict[str, int] = {}
    async for doc in db.events.aggregate(sent_pipeline):
        sent_by_ip[doc["_id"]] = doc["sent"]

    for item in bounces_by_ip:
        key = item["sending_ip"] or "__unknown__"
        sent = sent_by_ip.get(key, 0)
        item["sent"] = sent
        item["bounce_rate"] = round(item["hard_bounces"] / sent * 100, 2) if sent else None

    return {"by_ip": bounces_by_ip, "since": since.isoformat(), "days": days}
