import logging
from datetime import datetime
from fastapi import APIRouter, Request
from bson import ObjectId

from models.database import get_db
from core.suppression import add_suppression

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

EVENT_MAP = {
    "MessageSent": "delivered",
    "MessageDelivered": "delivered",
    "MessageBounced": "bounced",
    "MessageHeld": "bounced",
    "MessageDeliveryFailed": "bounced",
    "MessageLinkClicked": "clicked",
    "MessageLoaded": "opened",
}


@router.post("/postal")
async def postal_webhook(request: Request):
    payload = await request.json()
    logger.info(f"Postal webhook received: {payload}")

    event_type = payload.get("event")
    mapped_type = EVENT_MAP.get(event_type)
    if not mapped_type:
        return {"status": "ignored", "event": event_type}

    message = payload.get("payload", {}).get("message", {})
    rcpt_to = message.get("rcpt_to", payload.get("payload", {}).get("rcpt_to", ""))
    postal_message_id = str(message.get("id", ""))
    tag = message.get("tag", "")

    db = get_db()

    bounce_type = None
    bounce_message = None
    click_url = None

    if mapped_type == "bounced":
        bounce_info = payload.get("payload", {})
        bounce_message = bounce_info.get("details", bounce_info.get("output", ""))
        status = bounce_info.get("status", message.get("status", ""))
        bounce_type = "hard" if status in ("HardFail", "MessageDeliveryFailed") else "soft"

    if mapped_type == "clicked":
        click_url = payload.get("payload", {}).get("url", "")

    event_doc = {
        "campaign_id": tag,
        "contact_id": "",
        "email": rcpt_to,
        "event_type": mapped_type,
        "stream": "",
        "bounce_type": bounce_type,
        "bounce_message": bounce_message,
        "click_url": click_url,
        "postal_message_id": postal_message_id,
        "metadata": {"raw_event": event_type},
        "created_at": datetime.utcnow(),
    }

    contact = await db.contacts.find_one({"email": rcpt_to})
    if contact:
        event_doc["contact_id"] = str(contact["_id"])
        event_doc["stream"] = contact.get("stream", "")

    await db.events.insert_one(event_doc)

    if tag:
        try:
            stat_field = f"stats.{mapped_type}"
            await db.campaigns.update_one(
                {"_id": ObjectId(tag)},
                {"$inc": {stat_field: 1}},
            )
        except Exception as e:
            logger.warning(f"Could not update campaign stats for tag={tag!r}: {e}")

    if mapped_type == "opened" and contact:
        await db.contacts.update_one(
            {"_id": contact["_id"]},
            {
                "$set": {"engagement.last_opened_at": datetime.utcnow()},
                "$inc": {"engagement.total_opened": 1},
            },
        )

    if mapped_type == "clicked" and contact:
        await db.contacts.update_one(
            {"_id": contact["_id"]},
            {
                "$set": {"engagement.last_clicked_at": datetime.utcnow()},
                "$inc": {"engagement.total_clicked": 1},
            },
        )

    if mapped_type == "bounced" and bounce_type == "hard":
        add_suppression(rcpt_to, "hard_bounce", source="postal_webhook", campaign_id=tag)
        logger.info(f"Hard bounce: {rcpt_to} suppressed")
    elif mapped_type == "bounced" and bounce_type == "soft":
        from core.suppression_rules import check_auto_suppress_soft_bounce
        if check_auto_suppress_soft_bounce(rcpt_to, campaign_id=tag):
            logger.info(f"Soft bounce auto-suppressed: {rcpt_to} (exceeded threshold)")

    logger.info(f"Webhook: {event_type} → {mapped_type} for {rcpt_to}")
    return {"status": "processed", "event": mapped_type, "email": rcpt_to}
