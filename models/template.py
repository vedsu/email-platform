from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


class TemplateCategory(str, Enum):
    WELCOME = "welcome"
    PROMOTIONAL = "promotional"
    TRANSACTIONAL = "transactional"
    NEWSLETTER = "newsletter"
    RE_ENGAGEMENT = "re_engagement"
    OTHER = "other"


class Template(BaseModel):
    name: str
    category: TemplateCategory = TemplateCategory.OTHER
    subject: str
    preheader: str = ""
    html_body: str
    text_body: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


TEMPLATE_INDEXES = [
    {"keys": [("name", 1)], "unique": True},
    {"keys": [("category", 1)]},
    {"keys": [("created_by", 1)]},
    {"keys": [("created_at", -1)]},
]
