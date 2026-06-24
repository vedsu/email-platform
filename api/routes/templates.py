from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from bson import ObjectId

from models.database import get_db
from models.template import TemplateCategory
from core.auth import get_current_user
from core.render import render_template

router = APIRouter(prefix="/templates", tags=["templates"])


class TemplateCreate(BaseModel):
    name: str
    category: TemplateCategory = TemplateCategory.OTHER
    subject: str
    preheader: str = ""
    html_body: str
    text_body: Optional[str] = None


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[TemplateCategory] = None
    subject: Optional[str] = None
    preheader: Optional[str] = None
    html_body: Optional[str] = None
    text_body: Optional[str] = None


@router.post("")
async def create_template(payload: TemplateCreate, user: dict = Depends(get_current_user)):
    db = get_db()
    doc = payload.model_dump()
    doc["created_by"] = user["sub"]
    doc["created_at"] = datetime.utcnow()
    doc["updated_at"] = datetime.utcnow()

    try:
        result = await db.templates.insert_one(doc)
    except Exception as e:
        if "duplicate key" in str(e):
            raise HTTPException(status_code=409, detail="Template name already exists")
        raise
    return {"id": str(result.inserted_id), "name": payload.name}


@router.get("")
async def list_templates(
    category: Optional[TemplateCategory] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    user: dict = Depends(get_current_user),
):
    db = get_db()
    query = {}
    if category:
        query["category"] = category.value

    cursor = db.templates.find(query).skip(skip).limit(limit).sort("created_at", -1)
    templates = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        templates.append(doc)

    total = await db.templates.count_documents(query)
    return {"templates": templates, "total": total}


@router.get("/{template_id}")
async def get_template(template_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    doc = await db.templates.find_one({"_id": ObjectId(template_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Template not found")
    doc["_id"] = str(doc["_id"])
    return doc


@router.put("/{template_id}")
async def update_template(template_id: str, payload: TemplateUpdate, user: dict = Depends(get_current_user)):
    db = get_db()
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updates["updated_at"] = datetime.utcnow()
    result = await db.templates.update_one({"_id": ObjectId(template_id)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"updated": True}


@router.delete("/{template_id}")
async def delete_template(template_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    result = await db.templates.delete_one({"_id": ObjectId(template_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"deleted": True}


@router.post("/{template_id}/clone")
async def clone_template(template_id: str, new_name: str, user: dict = Depends(get_current_user)):
    db = get_db()
    doc = await db.templates.find_one({"_id": ObjectId(template_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Template not found")

    doc.pop("_id")
    doc["name"] = new_name
    doc["created_by"] = user["sub"]
    doc["created_at"] = datetime.utcnow()
    doc["updated_at"] = datetime.utcnow()

    try:
        result = await db.templates.insert_one(doc)
    except Exception as e:
        if "duplicate key" in str(e):
            raise HTTPException(status_code=409, detail="Template name already exists")
        raise
    return {"id": str(result.inserted_id), "name": new_name}


@router.post("/{template_id}/preview")
async def preview_template(template_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    doc = await db.templates.find_one({"_id": ObjectId(template_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Template not found")

    sample_contact = {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john.doe@example.com",
    }

    return {
        "subject": render_template(doc["subject"], sample_contact),
        "preheader": render_template(doc.get("preheader", ""), sample_contact),
        "html_body": render_template(doc["html_body"], sample_contact),
        "text_body": render_template(doc.get("text_body") or "", sample_contact) or None,
    }
