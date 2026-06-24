from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


class EventType(str, Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    CLICKED = "clicked"
    BOUNCED = "bounced"
    COMPLAINED = "complained"
    UNSUBSCRIBED = "unsubscribed"


class BounceType(str, Enum):
    HARD = "hard"
    SOFT = "soft"


class Event(BaseModel):
    campaign_id: str
    contact_id: str
    email: str
    event_type: EventType
    stream: str
    bounce_type: Optional[BounceType] = None
    bounce_message: Optional[str] = None
    click_url: Optional[str] = None
    postal_message_id: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


EVENT_INDEXES = [
    {"keys": [("campaign_id", 1), ("event_type", 1)]},
    {"keys": [("contact_id", 1), ("created_at", -1)]},
    {"keys": [("email", 1), ("event_type", 1)]},
    {"keys": [("created_at", -1)]},
]
