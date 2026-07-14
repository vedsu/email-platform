import logging
from datetime import datetime
from fastapi import APIRouter, Request
from bson import ObjectId

from models.database import get_db

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


def _extract_tag(raw_tag) -> str:
    """Postal sends tag as string or single-item list; normalise to string."""
    if isinstance(raw_tag, list):
        return raw_tag[0] if raw_tag else ""
    return raw_tag or ""


@router.post("/postal")
async def postal_webhook(request: Request):
    payload = await request.json()
    logger.info(f"Postal webhook received: {payload}")

    event_type = payload.get("event")
    mapped_type = EVENT_MAP.get(event_type)
    if not mapped_type:
        return {"status": "ignored", "event": event_type}

    postal_payload = payload.get("payload", {})
    # MessageBounced uses original_message; all other events use message
    if event_type == "MessageBounced":
        message = postal_payload.get("original_message", {})
    else:
        message = postal_payload.get("message", {})
    rcpt_to = (
        message.get("rcpt_to")
        or message.get("to")
        or postal_payload.get("rcpt_to")
        or ""
    ).strip().lower()
    postal_message_id = message.get("id")
    tag = _extract_tag(message.get("tag", ""))

    db = get_db()

    bounce_type = None
    bounce_message = None
    click_url = None

    if mapped_type == "bounced":
        bounce_message = postal_payload.get("details", postal_payload.get("output", ""))
        status = message.get("status", postal_payload.get("status", ""))
        bounce_type = "hard" if status == "HardFail" else "soft"
        logger.info(f"Bounce event: event={event_type} status={status!r} bounce_type={bounce_type} rcpt={rcpt_to}")

    if mapped_type == "clicked":
        click_url = postal_payload.get("url", "")

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
        "sending_ip": None,
        "ip_pool_id": None,
        "ip_pool_name": None,
        "metadata": {"raw_event": event_type},
        "created_at": datetime.utcnow(),
    }

    contact = await db.contacts.find_one({"email": rcpt_to})
    if contact:
        event_doc["contact_id"] = str(contact["_id"])
        event_doc["stream"] = contact.get("stream", "")

    # For bounce events, pull the IP that originally sent the message
    if mapped_type == "bounced" and postal_message_id:
        sent_event = await db.events.find_one(
            {"postal_message_id": postal_message_id, "event_type": "sent"},
            {"sending_ip": 1, "ip_pool_id": 1, "ip_pool_name": 1},
        )
        if sent_event:
            event_doc["sending_ip"] = sent_event.get("sending_ip")
            event_doc["ip_pool_id"] = sent_event.get("ip_pool_id")
            event_doc["ip_pool_name"] = sent_event.get("ip_pool_name")

    await db.events.insert_one(event_doc)

    # Update campaign stats
    if tag:
        try:
            stat_field = "stats.bounced" if mapped_type == "bounced" and bounce_type == "hard" else f"stats.{mapped_type}"
            if mapped_type == "bounced" and bounce_type == "soft":
                stat_field = "stats.soft_bounced"
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

    if mapped_type == "bounced":
        campaign_doc = None
        if tag:
            try:
                campaign_doc = await db.campaigns.find_one({"_id": ObjectId(tag)})
            except Exception:
                pass
        should_suppress = (campaign_doc or {}).get("auto_suppress", True)

        if should_suppress:
            if bounce_type == "hard":
                try:
                    await db.suppressions.insert_one({
                        "email": rcpt_to,
                        "reason": "hard_bounce",
                        "source": "postal_webhook",
                        "campaign_id": tag or None,
                        "created_at": datetime.utcnow(),
                    })
                    logger.info(f"Hard bounce suppressed: {rcpt_to}")
                except Exception as e:
                    if "duplicate key" not in str(e):
                        logger.error(f"Suppression insert failed for {rcpt_to}: {e}")
                    else:
                        logger.info(f"Hard bounce {rcpt_to} already suppressed")
                await db.contacts.update_one(
                    {"email": rcpt_to},
                    {"$set": {"status": "suppressed", "updated_at": datetime.utcnow()}},
                )
            elif bounce_type == "soft":
                from core.suppression_rules import check_auto_suppress_soft_bounce
                if check_auto_suppress_soft_bounce(rcpt_to, campaign_id=tag):
                    logger.info(f"Soft bounce auto-suppressed: {rcpt_to} (exceeded threshold)")
        else:
            logger.info(f"Bounce for {rcpt_to} — auto-suppress disabled for campaign {tag}")

    logger.info(f"Webhook: {event_type} → {mapped_type} for {rcpt_to}")
    return {"status": "processed", "event": mapped_type, "email": rcpt_to}
