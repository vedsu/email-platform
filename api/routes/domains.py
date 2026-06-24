from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from bson import ObjectId
import dns.resolver

from models.database import get_db
from core.auth import get_current_user, require_admin

router = APIRouter(prefix="/domains", tags=["domains"])

STREAM_PREFIXES = {
    "optin": "mail",
    "engaged": "eng",
    "cold": "out",
}


class DomainCreate(BaseModel):
    domain: str
    stream: str = "optin"
    subdomain_prefix: Optional[str] = None


def generate_dns_records(full_domain: str, domain: str, dkim_selector: str = "postal") -> list[dict]:
    return [
        {
            "record_type": "TXT",
            "hostname": full_domain,
            "value": f"v=spf1 include:spf.{full_domain} ~all",
            "verified": False,
        },
        {
            "record_type": "TXT",
            "hostname": f"{dkim_selector}._domainkey.{full_domain}",
            "value": "v=DKIM1; k=rsa; p=YOUR_DKIM_PUBLIC_KEY_HERE",
            "verified": False,
        },
        {
            "record_type": "TXT",
            "hostname": f"_dmarc.{domain}",
            "value": f"v=DMARC1; p=quarantine; rua=mailto:dmarc@{domain}; pct=100",
            "verified": False,
        },
        {
            "record_type": "MX",
            "hostname": full_domain,
            "value": f"mx.{full_domain}",
            "priority": 10,
            "verified": False,
        },
        {
            "record_type": "A",
            "hostname": full_domain,
            "value": "YOUR_SERVER_IP",
            "verified": False,
        },
        {
            "record_type": "PTR",
            "hostname": "YOUR_SERVER_IP",
            "value": full_domain,
            "verified": False,
        },
    ]


@router.post("")
async def add_domain(payload: DomainCreate, user: dict = Depends(get_current_user)):
    db = get_db()

    prefix = payload.subdomain_prefix or STREAM_PREFIXES.get(payload.stream, "mail")
    full_domain = f"{prefix}.{payload.domain}"

    existing = await db.domains.find_one({"full_domain": full_domain})
    if existing:
        raise HTTPException(status_code=409, detail=f"Domain {full_domain} already exists")

    dkim_selector = f"postal-{payload.stream}"
    records = generate_dns_records(full_domain, payload.domain, dkim_selector)

    doc = {
        "domain": payload.domain,
        "stream": payload.stream,
        "subdomain": prefix,
        "full_domain": full_domain,
        "status": "pending",
        "dkim_selector": dkim_selector,
        "dns_records": records,
        "ip_pool_id": None,
        "created_by": user["sub"],
        "verified_at": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    result = await db.domains.insert_one(doc)
    return {
        "id": str(result.inserted_id),
        "full_domain": full_domain,
        "stream": payload.stream,
        "dns_records": records,
        "message": "Add these DNS records at your domain provider (GoDaddy, etc.), then verify.",
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


@router.delete("/{domain_id}")
async def delete_domain(domain_id: str, admin: dict = Depends(require_admin)):
    db = get_db()
    result = await db.domains.delete_one({"_id": ObjectId(domain_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Domain not found")
    return {"deleted": True}
