from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from models.database import get_db
from models.list import ContactList, ListType, SegmentRule

router = APIRouter(prefix="/lists", tags=["lists"])


class ListCreate(BaseModel):
    name: str
    description: Optional[str] = None
    list_type: ListType = ListType.STATIC
    segment_rules: list[SegmentRule] = []
    segment_match: str = "all"


@router.post("")
async def create_list(payload: ListCreate):
    db = get_db()
    contact_list = ContactList(**payload.model_dump())
    try:
        result = await db.lists.insert_one(contact_list.model_dump())
    except Exception as e:
        if "duplicate key" in str(e):
            raise HTTPException(status_code=409, detail="List name already exists")
        raise
    return {"id": str(result.inserted_id), "name": payload.name}


@router.get("")
async def get_lists(
    list_type: Optional[ListType] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
):
    db = get_db()
    query = {}
    if list_type:
        query["list_type"] = list_type.value

    cursor = db.lists.find(query).skip(skip).limit(limit).sort("created_at", -1)
    lists = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        lists.append(doc)

    total = await db.lists.count_documents(query)
    return {"lists": lists, "total": total}


@router.get("/{list_id}")
async def get_list(list_id: str):
    from bson import ObjectId

    db = get_db()
    doc = await db.lists.find_one({"_id": ObjectId(list_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="List not found")
    doc["_id"] = str(doc["_id"])
    return doc


@router.post("/{list_id}/contacts")
async def add_contacts_to_list(list_id: str, emails: list[str]):
    from bson import ObjectId

    db = get_db()
    lst = await db.lists.find_one({"_id": ObjectId(list_id)})
    if not lst:
        raise HTTPException(status_code=404, detail="List not found")

    result = await db.contacts.update_many(
        {"email": {"$in": emails}},
        {"$addToSet": {"list_ids": list_id}},
    )

    await db.lists.update_one(
        {"_id": ObjectId(list_id)},
        {"$set": {"contact_count": await db.contacts.count_documents({"list_ids": list_id})}},
    )

    return {"matched": result.matched_count, "modified": result.modified_count}


@router.delete("/{list_id}/delete")
async def delete_list(list_id: str):
    from bson import ObjectId

    db = get_db()
    lst = await db.lists.find_one({"_id": ObjectId(list_id)})
    if not lst:
        raise HTTPException(status_code=404, detail="List not found")

    result = await db.contacts.delete_many({"list_ids": list_id})
    await db.lists.delete_one({"_id": ObjectId(list_id)})
    return {"deleted": True, "contacts_deleted": result.deleted_count}
