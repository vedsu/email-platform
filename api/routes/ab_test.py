from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from bson import ObjectId

from models.database import get_db
from core.auth import get_current_user

router = APIRouter(prefix="/ab-test", tags=["ab-test"])


class ABTestCreate(BaseModel):
    campaign_id: str
    subject_a: str
    subject_b: str
    test_percent: int = 20
    winner_metric: str = "opened"


@router.post("")
async def create_ab_test(payload: ABTestCreate, user: dict = Depends(get_current_user)):
    db = get_db()
    campaign = await db.campaigns.find_one({"_id": ObjectId(payload.campaign_id)})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign["status"] != "draft":
        raise HTTPException(status_code=400, detail="Campaign must be in draft status")

    doc = {
        "campaign_id": payload.campaign_id,
        "subject_a": payload.subject_a,
        "subject_b": payload.subject_b,
        "test_percent": payload.test_percent,
        "winner_metric": payload.winner_metric,
        "status": "pending",
        "stats_a": {"sent": 0, "opened": 0, "clicked": 0},
        "stats_b": {"sent": 0, "opened": 0, "clicked": 0},
        "winner": None,
        "created_by": user["sub"],
        "created_at": datetime.utcnow(),
    }
    result = await db.ab_tests.insert_one(doc)

    await db.campaigns.update_one(
        {"_id": ObjectId(payload.campaign_id)},
        {"$set": {"ab_test_id": str(result.inserted_id)}},
    )

    return {"id": str(result.inserted_id), "status": "pending"}


@router.get("/{test_id}")
async def get_ab_test(test_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    doc = await db.ab_tests.find_one({"_id": ObjectId(test_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="A/B test not found")
    doc["_id"] = str(doc["_id"])
    return doc


@router.post("/{test_id}/pick-winner")
async def pick_winner(test_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    test = await db.ab_tests.find_one({"_id": ObjectId(test_id)})
    if not test:
        raise HTTPException(status_code=404, detail="A/B test not found")

    metric = test["winner_metric"]
    a_score = test["stats_a"].get(metric, 0)
    b_score = test["stats_b"].get(metric, 0)

    winner = "a" if a_score >= b_score else "b"
    winning_subject = test["subject_a"] if winner == "a" else test["subject_b"]

    await db.ab_tests.update_one(
        {"_id": ObjectId(test_id)},
        {"$set": {"winner": winner, "status": "completed"}},
    )

    await db.campaigns.update_one(
        {"_id": ObjectId(test["campaign_id"])},
        {"$set": {"subject": winning_subject}},
    )

    return {
        "winner": winner,
        "winning_subject": winning_subject,
        "stats": {"a": test["stats_a"], "b": test["stats_b"]},
    }


@router.get("/campaign/{campaign_id}")
async def get_test_for_campaign(campaign_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    doc = await db.ab_tests.find_one({"campaign_id": campaign_id})
    if not doc:
        raise HTTPException(status_code=404, detail="No A/B test for this campaign")
    doc["_id"] = str(doc["_id"])
    return doc
