from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from enum import Enum


class StreamType(str, Enum):
    OPTIN = "optin"
    ENGAGED = "engaged"
    COLD = "cold"


class ContactStatus(str, Enum):
    ACTIVE = "active"
    UNSUBSCRIBED = "unsubscribed"
    BOUNCED = "bounced"
    COMPLAINED = "complained"
    SUPPRESSED = "suppressed"


class ContactSource(str, Enum):
    IMPORT = "import"
    API = "api"
    SIGNUP = "signup"
    MANUAL = "manual"


class EngagementStats(BaseModel):
    last_sent_at: Optional[datetime] = None
    last_opened_at: Optional[datetime] = None
    last_clicked_at: Optional[datetime] = None
    total_sent: int = 0
    total_opened: int = 0
    total_clicked: int = 0


class Contact(BaseModel):
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    attributes: dict = Field(default_factory=dict)
    stream: StreamType = StreamType.COLD
    status: ContactStatus = ContactStatus.ACTIVE
    source: ContactSource = ContactSource.IMPORT
    list_ids: list[str] = Field(default_factory=list)
    engagement: EngagementStats = Field(default_factory=EngagementStats)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


CONTACT_INDEXES = [
    {"keys": [("email", 1)], "unique": True},
    {"keys": [("status", 1), ("stream", 1)]},
    {"keys": [("list_ids", 1)]},
    {"keys": [("stream", 1), ("engagement.last_opened_at", -1)]},
]
