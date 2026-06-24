from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from bson import ObjectId

from models.database import get_db
from core.auth import require_admin

router = APIRouter(prefix="/ip-pools", tags=["ip-pools"])


class IPPoolCreate(BaseModel):
    name: str
    description: str = ""
    stream: str = "optin"


class IPAddressCreate(BaseModel):
    ip: str
    hostname: str = ""
    ip_type: str = "dedicated"
    stream: str = "optin"
    pool_id: Optional[str] = None
    domain_id: Optional[str] = None
    daily_cap: int = 100


class IPAssign(BaseModel):
    domain_id: Optional[str] = None
    pool_id: Optional[str] = None
    stream: Optional[str] = None


# --- Pools ---

@router.post("")
async def create_pool(payload: IPPoolCreate, admin: dict = Depends(require_admin)):
    db = get_db()
    doc = {
        "name": payload.name,
        "description": payload.description,
        "stream": payload.stream,
        "ip_ids": [],
        "domain_ids": [],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    try:
        result = await db.ip_pools.insert_one(doc)
    except Exception as e:
        if "duplicate key" in str(e):
            raise HTTPException(status_code=409, detail="Pool name already exists")
        raise
    return {"id": str(result.inserted_id), "name": payload.name}


@router.get("")
async def list_pools(admin: dict = Depends(require_admin)):
    db = get_db()
    pools = []
    async for doc in db.ip_pools.find().sort("created_at", -1):
        doc["_id"] = str(doc["_id"])
        ip_count = await db.ip_addresses.count_documents({"pool_id": doc["_id"]})
        doc["ip_count"] = ip_count
        pools.append(doc)
    return {"pools": pools}


@router.get("/{pool_id}")
async def get_pool(pool_id: str, admin: dict = Depends(require_admin)):
    db = get_db()
    pool = await db.ip_pools.find_one({"_id": ObjectId(pool_id)})
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")
    pool["_id"] = str(pool["_id"])

    ips = []
    async for ip in db.ip_addresses.find({"pool_id": pool_id}):
        ip["_id"] = str(ip["_id"])
        ips.append(ip)
    pool["ips"] = ips

    domains = []
    for did in pool.get("domain_ids", []):
        d = await db.domains.find_one({"_id": ObjectId(did)})
        if d:
            d["_id"] = str(d["_id"])
            domains.append(d)
    pool["domains"] = domains

    return pool


@router.post("/{pool_id}/assign-domain/{domain_id}")
async def assign_domain_to_pool(pool_id: str, domain_id: str, admin: dict = Depends(require_admin)):
    db = get_db()
    pool = await db.ip_pools.find_one({"_id": ObjectId(pool_id)})
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")

    await db.ip_pools.update_one(
        {"_id": ObjectId(pool_id)},
        {"$addToSet": {"domain_ids": domain_id}, "$set": {"updated_at": datetime.utcnow()}},
    )
    await db.domains.update_one(
        {"_id": ObjectId(domain_id)},
        {"$set": {"ip_pool_id": pool_id, "updated_at": datetime.utcnow()}},
    )
    return {"assigned": True}


@router.delete("/{pool_id}")
async def delete_pool(pool_id: str, admin: dict = Depends(require_admin)):
    db = get_db()
    await db.ip_addresses.update_many({"pool_id": pool_id}, {"$set": {"pool_id": None}})
    await db.domains.update_many({"ip_pool_id": pool_id}, {"$set": {"ip_pool_id": None}})
    result = await db.ip_pools.delete_one({"_id": ObjectId(pool_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Pool not found")
    return {"deleted": True}


# --- IP Addresses ---

@router.post("/ips")
async def add_ip(payload: IPAddressCreate, admin: dict = Depends(require_admin)):
    db = get_db()
    doc = {
        "ip": payload.ip,
        "hostname": payload.hostname,
        "ip_type": payload.ip_type,
        "status": "warming",
        "stream": payload.stream,
        "domain_id": payload.domain_id,
        "pool_id": payload.pool_id,
        "ptr_record": "",
        "daily_cap": payload.daily_cap,
        "today_sent": 0,
        "created_at": datetime.utcnow(),
    }
    try:
        result = await db.ip_addresses.insert_one(doc)
    except Exception as e:
        if "duplicate key" in str(e):
            raise HTTPException(status_code=409, detail="IP already exists")
        raise

    if payload.pool_id:
        await db.ip_pools.update_one(
            {"_id": ObjectId(payload.pool_id)},
            {"$addToSet": {"ip_ids": str(result.inserted_id)}},
        )

    return {"id": str(result.inserted_id), "ip": payload.ip}


@router.get("/ips")
async def list_ips(admin: dict = Depends(require_admin)):
    db = get_db()
    ips = []
    async for doc in db.ip_addresses.find().sort("created_at", -1):
        doc["_id"] = str(doc["_id"])
        if doc.get("domain_id"):
            domain = await db.domains.find_one({"_id": ObjectId(doc["domain_id"])})
            doc["domain_name"] = domain["full_domain"] if domain else None
        if doc.get("pool_id"):
            pool = await db.ip_pools.find_one({"_id": ObjectId(doc["pool_id"])})
            doc["pool_name"] = pool["name"] if pool else None
        ips.append(doc)
    return {"ips": ips}


@router.patch("/ips/{ip_id}")
async def update_ip(ip_id: str, updates: dict, admin: dict = Depends(require_admin)):
    db = get_db()
    allowed = {"hostname", "ip_type", "status", "stream", "domain_id", "pool_id", "daily_cap", "ptr_record"}
    filtered = {k: v for k, v in updates.items() if k in allowed}
    if not filtered:
        raise HTTPException(status_code=400, detail="No valid fields")

    result = await db.ip_addresses.update_one({"_id": ObjectId(ip_id)}, {"$set": filtered})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="IP not found")
    return {"updated": True}


@router.delete("/ips/{ip_id}")
async def delete_ip(ip_id: str, admin: dict = Depends(require_admin)):
    db = get_db()
    ip = await db.ip_addresses.find_one({"_id": ObjectId(ip_id)})
    if not ip:
        raise HTTPException(status_code=404, detail="IP not found")

    if ip.get("pool_id"):
        await db.ip_pools.update_one(
            {"_id": ObjectId(ip["pool_id"])},
            {"$pull": {"ip_ids": ip_id}},
        )

    await db.ip_addresses.delete_one({"_id": ObjectId(ip_id)})
    return {"deleted": True}


@router.get("/overview")
async def ip_overview(admin: dict = Depends(require_admin)):
    db = get_db()
    total_ips = await db.ip_addresses.count_documents({})
    by_status = {}
    async for doc in db.ip_addresses.aggregate([{"$group": {"_id": "$status", "count": {"$sum": 1}}}]):
        by_status[doc["_id"]] = doc["count"]

    by_stream = {}
    async for doc in db.ip_addresses.aggregate([{"$group": {"_id": "$stream", "count": {"$sum": 1}}}]):
        by_stream[doc["_id"]] = doc["count"]

    total_pools = await db.ip_pools.count_documents({})

    return {
        "total_ips": total_ips,
        "total_pools": total_pools,
        "by_status": by_status,
        "by_stream": by_stream,
    }
