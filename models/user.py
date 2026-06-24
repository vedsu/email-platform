from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    MEMBER = "member"


class User(BaseModel):
    email: EmailStr
    name: str
    password_hash: str
    role: UserRole = UserRole.MEMBER
    is_active: bool = True
    last_login_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


USER_INDEXES = [
    {"keys": [("email", 1)], "unique": True},
    {"keys": [("role", 1)]},
]
