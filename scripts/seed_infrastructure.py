#!/usr/bin/env python3
"""Seed MongoDB with current sending domains and IP pool configuration."""
import os, sys
from datetime import datetime
from pymongo import MongoClient

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://emailapp:emailapp123@127.0.0.1:27017/email_platform?authSource=email_platform")
client = MongoClient(MONGO_URI)
db = client.get_default_database()

now = datetime.utcnow()

# ── 1. Clear old domain entries ───────────────────────────────────────────────
deleted = db.domains.delete_many({})
print(f"Cleared {deleted.deleted_count} old domain record(s)")

# ── 2. Insert current sending domains ────────────────────────────────────────
domains = [
    {
        "domain": "webinarsorbit.com",
        "subdomain": "",
        "full_domain": "webinarsorbit.com",
        "stream": "all",
        "status": "verified",
        "dkim_selector": "postal-sXYVHG",
        "ip_pool_id": None,
        "created_by": "system",
        "verified_at": now,
        "created_at": now,
        "updated_at": now,
        "dns_records": [
            {"record_type": "TXT", "hostname": "webinarsorbit.com", "label": "SPF", "verified": True},
            {"record_type": "TXT", "hostname": "postal-sXYVHG._domainkey.webinarsorbit.com", "label": "DKIM", "verified": True},
            {"record_type": "CNAME", "hostname": "psrp.webinarsorbit.com", "label": "Return Path", "verified": True},
            {"record_type": "MX", "hostname": "webinarsorbit.com", "label": "MX", "verified": True},
        ],
    },
    {
        "domain": "onlinehrtraining.com",
        "subdomain": "",
        "full_domain": "onlinehrtraining.com",
        "stream": "all",
        "status": "verified",
        "dkim_selector": "postal-zrZdpR",
        "ip_pool_id": None,
        "created_by": "system",
        "verified_at": now,
        "created_at": now,
        "updated_at": now,
        "dns_records": [
            {"record_type": "TXT", "hostname": "onlinehrtraining.com", "label": "SPF", "verified": True},
            {"record_type": "TXT", "hostname": "postal-zrZdpR._domainkey.onlinehrtraining.com", "label": "DKIM", "verified": True},
            {"record_type": "CNAME", "hostname": "psrp.onlinehrtraining.com", "label": "Return Path", "verified": True},
            {"record_type": "MX", "hostname": "onlinehrtraining.com", "label": "MX", "verified": True},
        ],
    },
]
result = db.domains.insert_many(domains)
domain_ids = [str(i) for i in result.inserted_ids]
print(f"Inserted {len(domain_ids)} domain(s): webinarsorbit.com, onlinehrtraining.com")

# ── 3. Clear old IP pool entries ──────────────────────────────────────────────
db.ip_pools.delete_many({})
db.ip_addresses.delete_many({})
print("Cleared old IP pool/address records")

# ── 4. Create default IP pool ─────────────────────────────────────────────────
pool = {
    "name": "default",
    "description": "Primary sending pool — bulk campaigns",
    "stream": "all",
    "is_default": True,
    "ip_ids": [],
    "domain_ids": domain_ids,
    "created_at": now,
    "updated_at": now,
}
pool_result = db.ip_pools.insert_one(pool)
pool_id = str(pool_result.inserted_id)
print(f"Created IP pool 'default' (id: {pool_id})")

# ── 5. Insert sending IPs ─────────────────────────────────────────────────────
ips = [
    {
        "ip": "15.235.28.166",
        "hostname": "smtp2.vedsupost.com",
        "ip_type": "dedicated",
        "status": "warming",
        "stream": "all",
        "pool_id": pool_id,
        "ptr_record": "smtp2.vedsupost.com",
        "daily_cap": 300,
        "today_sent": 0,
        "created_at": now,
    },
    {
        "ip": "15.235.4.241",
        "hostname": "smtp3.vedsupost.com",
        "ip_type": "dedicated",
        "status": "warming",
        "stream": "all",
        "pool_id": pool_id,
        "ptr_record": "smtp3.vedsupost.com",
        "daily_cap": 300,
        "today_sent": 0,
        "created_at": now,
    },
]
ip_result = db.ip_addresses.insert_many(ips)
ip_ids = [str(i) for i in ip_result.inserted_ids]
print(f"Inserted {len(ip_ids)} IP(s): smtp2 (15.235.28.166), smtp3 (15.235.4.241)")

# ── 6. Link IPs + domains back to pool ───────────────────────────────────────
db.ip_pools.update_one(
    {"_id": pool_result.inserted_id},
    {"$set": {"ip_ids": ip_ids, "domain_ids": domain_ids}},
)
db.domains.update_many({}, {"$set": {"ip_pool_id": pool_id}})
print("Linked IPs and domains to pool 'default'")

print("\nDone. CRM Domains and IP Pools pages will now show current configuration.")
