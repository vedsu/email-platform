from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum

from models.contact import StreamType


class CampaignStatus(str, Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CampaignStats(BaseModel):
    total_recipients: int = 0
    sent: int = 0
    delivered: int = 0
    opened: int = 0
    clicked: int = 0
    bounced: int = 0
    complained: int = 0
    unsubscribed: int = 0


class Campaign(BaseModel):
    name: str
    subject: str
    from_name: str
    from_email: str
    html_body: str
    text_body: Optional[str] = None
    stream: StreamType = StreamType.COLD
    target_list_id: Optional[str] = None
    target_segment_id: Optional[str] = None
    status: CampaignStatus = CampaignStatus.DRAFT
    stats: CampaignStats = Field(default_factory=CampaignStats)
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


CAMPAIGN_INDEXES = [
    {"keys": [("status", 1)]},
    {"keys": [("stream", 1)]},
    {"keys": [("created_at", -1)]},
]
