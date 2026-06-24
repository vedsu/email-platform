from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


class DomainStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"


class DNSRecord(BaseModel):
    record_type: str
    hostname: str
    value: str
    priority: Optional[int] = None
    verified: bool = False


class Domain(BaseModel):
    domain: str
    stream: str = "optin"
    subdomain: str
    full_domain: str
    status: DomainStatus = DomainStatus.PENDING
    dkim_selector: str = "postal"
    dns_records: list[DNSRecord] = Field(default_factory=list)
    ip_pool_id: Optional[str] = None
    created_by: Optional[str] = None
    verified_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


DOMAIN_INDEXES = [
    {"keys": [("full_domain", 1)], "unique": True},
    {"keys": [("domain", 1)]},
    {"keys": [("stream", 1)]},
    {"keys": [("status", 1)]},
]
