from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


class ListType(str, Enum):
    STATIC = "static"
    SEGMENT = "segment"


class SegmentOperator(str, Enum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    IN = "in"
    NOT_IN = "not_in"
    EXISTS = "exists"


class SegmentRule(BaseModel):
    field: str
    operator: SegmentOperator
    value: object = None


class ContactList(BaseModel):
    name: str
    description: Optional[str] = None
    list_type: ListType = ListType.STATIC
    segment_rules: list[SegmentRule] = Field(default_factory=list)
    segment_match: str = "all"  # "all" = AND, "any" = OR
    contact_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


LIST_INDEXES = [
    {"keys": [("name", 1)], "unique": True},
    {"keys": [("list_type", 1)]},
]
