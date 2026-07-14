from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from bson import ObjectId
import dns.resolver

from models.database import get_db
from core.auth import get_current_user, require_admin

router = APIRouter(prefix="/domains", tags=["domains"])

class DomainCreate(BaseModel):
    domain: str



@router.post("")
async def add_domain(payload: DomainCreate, user: dict = Depends(get_current_user)):
    db = get_db()

    domain = payload.domain.strip().lower()
    existing = await db.domains.find_one({"domain": domain})
    if existing:
        raise HTTPException(status_code=409, detail=f"Domain {domain} already exists")

    doc = {
        "domain": domain,
        "full_domain": domain,
        "status": "pending",
        "ip_pool_id": None,
        "created_by": user["sub"],
        "verified_at": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    result = await db.domains.insert_one(doc)
    return {
        "id": str(result.inserted_id),
        "domain": domain,
        "message": "Domain added. Configure DNS in Postal, then verify.",
    }


@router.get("")
async def list_domains(user: dict = Depends(get_current_user)):
    db = get_db()
    cursor = db.domains.find().sort("created_at", -1)
    domains = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        domains.append(doc)
    return {"domains": domains}


@router.get("/{domain_id}")
async def get_domain(domain_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    doc = await db.domains.find_one({"_id": ObjectId(domain_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Domain not found")
    doc["_id"] = str(doc["_id"])
    return doc


@router.post("/{domain_id}/verify")
async def verify_domain(domain_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    doc = await db.domains.find_one({"_id": ObjectId(domain_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Domain not found")

    full_domain = doc["full_domain"]
    results = []
    all_passed = True

    for i, record in enumerate(doc["dns_records"]):
        check = {"record_type": record["record_type"], "hostname": record["hostname"], "expected": record["value"], "verified": False, "found": None}

        try:
            if record["record_type"] == "TXT":
                answers = dns.resolver.resolve(record["hostname"], "TXT")
                found_values = [r.to_text().strip('"') for r in answers]
                check["found"] = found_values
                check["verified"] = any(record["value"] in v for v in found_values)

            elif record["record_type"] == "MX":
                answers = dns.resolver.resolve(record["hostname"], "MX")
                found_values = [str(r.exchange).rstrip('.') for r in answers]
                check["found"] = found_values
                check["verified"] = any(record["value"] in v for v in found_values)

            elif record["record_type"] == "A":
                answers = dns.resolver.resolve(record["hostname"], "A")
                found_values = [str(r) for r in answers]
                check["found"] = found_values
                check["verified"] = record["value"] in found_values if record["value"] != "YOUR_SERVER_IP" else len(found_values) > 0

            elif record["record_type"] == "PTR":
                check["verified"] = False
                check["found"] = ["PTR must be set at hosting provider"]

        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers, dns.resolver.Timeout) as e:
            check["found"] = [f"DNS lookup failed: {type(e).__name__}"]
            check["verified"] = False

        if not check["verified"]:
            all_passed = False
        results.append(check)

        doc["dns_records"][i]["verified"] = check["verified"]

    new_status = "verified" if all_passed else "pending"
    update = {"dns_records": doc["dns_records"], "status": new_status, "updated_at": datetime.utcnow()}
    if all_passed:
        update["verified_at"] = datetime.utcnow()

    await db.domains.update_one({"_id": ObjectId(domain_id)}, {"$set": update})

    return {
        "domain": full_domain,
        "status": new_status,
        "all_passed": all_passed,
        "checks": results,
    }


POSTAL_POOL_IDS = {"optin": 2, "engaged": 3, "cold": 4, "inactive": 5}


class PoolAssign(BaseModel):
    pool: str


@router.put("/{domain_id}/pool")
async def assign_domain_pool(domain_id: str, payload: PoolAssign, user: dict = Depends(get_current_user)):
    db = get_db()
    pool_name = payload.pool.lower()
    if pool_name not in POSTAL_POOL_IDS:
        raise HTTPException(status_code=400, detail=f"Invalid pool. Choose from: {', '.join(POSTAL_POOL_IDS)}")
    doc = await db.domains.find_one({"_id": ObjectId(domain_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Domain not found")
    postal_pool_id = POSTAL_POOL_IDS[pool_name]
    await db.domains.update_one(
        {"_id": ObjectId(domain_id)},
        {"$set": {"pool": pool_name, "ip_pool_id": postal_pool_id, "updated_at": datetime.utcnow()}},
    )
    domain = doc["domain"]
    sql = (
        f"-- Run in Postal MariaDB to update routing:\n"
        f"UPDATE ip_pool_rules SET ip_pool_id = {postal_pool_id} WHERE from_text = '@{domain}';\n"
        f"-- If no rule exists yet:\n"
        f"INSERT IGNORE INTO ip_pool_rules (uuid, owner_type, owner_id, ip_pool_id, from_text, to_text, created_at, updated_at) "
        f"VALUES (UUID(), 'Server', 1, {postal_pool_id}, '@{domain}', NULL, NOW(), NOW());"
    )
    return {"updated": True, "pool": pool_name, "postal_pool_id": postal_pool_id, "postal_sql": sql}


@router.delete("/{domain_id}")
async def delete_domain(domain_id: str, admin: dict = Depends(require_admin)):
    db = get_db()
    result = await db.domains.delete_one({"_id": ObjectId(domain_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Domain not found")
    return {"deleted": True}
