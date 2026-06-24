from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


class IPType(str, Enum):
    DEDICATED = "dedicated"
    SHARED = "shared"


class IPStatus(str, Enum):
    ACTIVE = "active"
    WARMING = "warming"
    PAUSED = "paused"
    BLOCKLISTED = "blocklisted"


class IPAddress(BaseModel):
    ip: str
    hostname: str = ""
    ip_type: IPType = IPType.DEDICATED
    status: IPStatus = IPStatus.WARMING
    stream: str = "optin"
    domain_id: Optional[str] = None
    pool_id: Optional[str] = None
    ptr_record: str = ""
    daily_cap: int = 100
    today_sent: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class IPPool(BaseModel):
    name: str
    description: str = ""
    stream: str = "optin"
    ip_ids: list[str] = Field(default_factory=list)
    domain_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


IP_POOL_INDEXES = [
    {"keys": [("name", 1)], "unique": True},
    {"keys": [("stream", 1)]},
]

IP_ADDRESS_INDEXES = [
    {"keys": [("ip", 1)], "unique": True},
    {"keys": [("stream", 1)]},
    {"keys": [("pool_id", 1)]},
    {"keys": [("domain_id", 1)]},
    {"keys": [("status", 1)]},
]
