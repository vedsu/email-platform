from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr

from models.database import get_db
from core.auth import hash_password, verify_password, create_access_token, get_current_user, require_admin

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    name: str
    password: str
    role: str = "member"


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/login")
async def login(payload: LoginRequest):
    db = get_db()
    user = await db.users.find_one({"email": payload.email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account is disabled")

    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"last_login_at": datetime.utcnow()}},
    )

    token = create_access_token(str(user["_id"]), user["email"], user["role"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(user["_id"]),
            "email": user["email"],
            "name": user["name"],
            "role": user["role"],
        },
    }


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    db = get_db()
    doc = await db.users.find_one({"email": user["email"]})
    if not doc:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": str(doc["_id"]),
        "email": doc["email"],
        "name": doc["name"],
        "role": doc["role"],
        "is_active": doc.get("is_active", True),
        "last_login_at": doc.get("last_login_at"),
        "created_at": doc.get("created_at"),
    }


@router.post("/change-password")
async def change_password(payload: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    db = get_db()
    doc = await db.users.find_one({"email": user["email"]})
    if not verify_password(payload.current_password, doc["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    await db.users.update_one(
        {"_id": doc["_id"]},
        {"$set": {"password_hash": hash_password(payload.new_password), "updated_at": datetime.utcnow()}},
    )
    return {"status": "password_changed"}


# --- Admin endpoints ---

@router.post("/users")
async def create_user(payload: RegisterRequest, admin: dict = Depends(require_admin)):
    db = get_db()
    existing = await db.users.find_one({"email": payload.email})
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    from models.user import User
    user = User(
        email=payload.email,
        name=payload.name,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    result = await db.users.insert_one(user.model_dump())
    return {"id": str(result.inserted_id), "email": payload.email, "role": payload.role}


@router.get("/users")
async def list_users(admin: dict = Depends(require_admin)):
    db = get_db()
    cursor = db.users.find({}, {"password_hash": 0})
    users = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        users.append(doc)
    return {"users": users}


@router.patch("/users/{user_id}")
async def update_user(user_id: str, updates: dict, admin: dict = Depends(require_admin)):
    from bson import ObjectId
    db = get_db()
    allowed = {"name", "role", "is_active"}
    filtered = {k: v for k, v in updates.items() if k in allowed}
    if not filtered:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    filtered["updated_at"] = datetime.utcnow()
    result = await db.users.update_one({"_id": ObjectId(user_id)}, {"$set": filtered})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"updated": True}


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(user_id: str, admin: dict = Depends(require_admin)):
    from bson import ObjectId
    import secrets
    db = get_db()
    new_password = secrets.token_urlsafe(12)
    await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"password_hash": hash_password(new_password), "updated_at": datetime.utcnow()}},
    )
    return {"new_password": new_password}


@router.post("/setup")
async def initial_setup():
    """Create the first admin user. Only works if no users exist."""
    db = get_db()
    count = await db.users.count_documents({})
    if count > 0:
        raise HTTPException(status_code=400, detail="Setup already completed. Users exist.")

    admin_email = settings.default_admin_email or "admin@platform.local"
    if "@localhost" in admin_email:
        admin_email = "admin@platform.local"

    user_doc = {
        "email": admin_email,
        "name": "Admin",
        "password_hash": hash_password("admin123"),
        "role": "admin",
        "is_active": True,
        "last_login_at": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    result = await db.users.insert_one(user_doc)
    return {
        "message": "Admin user created",
        "email": admin_email,
        "password": "admin123",
        "note": "Change this password immediately after first login",
    }


from core.config import settings
