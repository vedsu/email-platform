from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.config import settings
from core.claude_client import (
    generate_dns_config,
    draft_warmup_plan,
    draft_email_content,
    classify_bounce,
    analyze_deliverability,
)
from models.database import get_db

router = APIRouter(prefix="/ai", tags=["ai"])


def _check_api_key():
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY not configured. Add it to your .env file.",
        )


class DNSConfigRequest(BaseModel):
    domain: str
    streams: dict = {
        "optin": "mail.yourdomain.com",
        "engaged": "eng.yourdomain.com",
        "cold": "out.yourdomain.com",
    }


class WarmupPlanRequest(BaseModel):
    ip_count: int = 5
    streams: list[str] = ["optin", "engaged", "cold"]
    daily_target: int = 100000


class EmailDraftRequest(BaseModel):
    purpose: str
    audience: str
    tone: str = "professional"
    key_points: Optional[list[str]] = None


class BounceClassifyRequest(BaseModel):
    bounce_message: str
    smtp_code: str = ""


@router.post("/dns-config")
async def ai_dns_config(payload: DNSConfigRequest):
    _check_api_key()
    result = generate_dns_config(payload.domain, payload.streams)
    return {"status": "draft", "approval_required": True, "config": result}


@router.post("/warmup-plan")
async def ai_warmup_plan(payload: WarmupPlanRequest):
    _check_api_key()
    result = draft_warmup_plan(payload.ip_count, payload.streams, payload.daily_target)
    return {"status": "draft", "approval_required": True, "plan": result}


@router.post("/draft-email")
async def ai_draft_email(payload: EmailDraftRequest):
    _check_api_key()
    result = draft_email_content(
        payload.purpose, payload.audience, payload.tone, payload.key_points
    )
    return {"status": "draft", "approval_required": True, "content": result}


@router.post("/classify-bounce")
async def ai_classify_bounce(payload: BounceClassifyRequest):
    _check_api_key()
    result = classify_bounce(payload.bounce_message, payload.smtp_code)
    return {"classification": result}


@router.post("/analyze-campaign/{campaign_id}")
async def ai_analyze_campaign(campaign_id: str):
    _check_api_key()
    from bson import ObjectId

    db = get_db()
    campaign = await db.campaigns.find_one({"_id": ObjectId(campaign_id)})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    stats = {
        "name": campaign.get("name", ""),
        "stream": campaign.get("stream", ""),
        "total_recipients": campaign["stats"].get("total_recipients", 0),
        "sent": campaign["stats"].get("sent", 0),
        "delivered": campaign["stats"].get("delivered", 0),
        "opened": campaign["stats"].get("opened", 0),
        "clicked": campaign["stats"].get("clicked", 0),
        "bounced": campaign["stats"].get("bounced", 0),
        "complained": campaign["stats"].get("complained", 0),
        "unsubscribed": campaign["stats"].get("unsubscribed", 0),
    }

    total = stats["sent"] or 1
    stats["open_rate"] = f"{(stats['opened'] / total) * 100:.1f}%"
    stats["click_rate"] = f"{(stats['clicked'] / total) * 100:.1f}%"
    stats["bounce_rate"] = f"{(stats['bounced'] / total) * 100:.1f}%"
    stats["complaint_rate"] = f"{(stats['complained'] / total) * 100:.1f}%"

    result = analyze_deliverability(stats)
    return {"campaign_id": campaign_id, "stats": stats, "analysis": result}
