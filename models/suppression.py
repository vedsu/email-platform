from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from enum import Enum


class SuppressionReason(str, Enum):
    HARD_BOUNCE = "hard_bounce"
    COMPLAINT = "complaint"
    UNSUBSCRIBE = "unsubscribe"
    ROLE_ADDRESS = "role_address"
    SPAM_TRAP = "spam_trap"
    MANUAL = "manual"


class Suppression(BaseModel):
    email: EmailStr
    reason: SuppressionReason
    source: Optional[str] = None
    campaign_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


SUPPRESSION_INDEXES = [
    {"keys": [("email", 1)], "unique": True},
    {"keys": [("reason", 1)]},
    {"keys": [("created_at", -1)]},
]
