import logging
from datetime import datetime
from bson import ObjectId

from worker.celery_app import celery
from models.sync_db import get_sync_db
from core.suppression import is_suppressed
from core.warmup import check_warmup_quota, increment_send_count
from core.routing import route_from_address
from core.render import render_template
from core.postal_client import send_message
from core.rate_limiter import check_domain_rate_limit, increment_domain_count

logger = logging.getLogger(__name__)


def _check_campaign_completion(db, campaign_id: str):
    campaign = db.campaigns.find_one({"_id": ObjectId(campaign_id)})
    if not campaign or campaign["status"] != "sending":
        return

    sent = campaign["stats"].get("sent", 0)
    total = campaign["stats"].get("total_recipients", 0)
    events_count = db.events.count_documents({"campaign_id": campaign_id, "event_type": "sent"})
    skipped = db.suppressions.count_documents({
        "email": {"$in": [
            c["email"] for c in db.contacts.find(
                {"list_ids": campaign.get("target_list_id"), "status": "suppressed"},
                {"email": 1}
            )
        ]}
    }) if campaign.get("target_list_id") else 0

    if (sent + skipped) >= total or events_count >= total:
        db.campaigns.update_one(
            {"_id": ObjectId(campaign_id), "status": "sending"},
            {"$set": {"status": "completed", "completed_at": datetime.utcnow()}},
        )
        logger.info(f"Campaign {campaign_id} completed (sent={sent}, skipped={skipped}, total={total})")


@celery.task(name="send_to_recipient", bind=True, max_retries=3, default_retry_delay=60)
def send_to_recipient(self, campaign_id: str, contact_id: str):
    db = get_sync_db()

    campaign = db.campaigns.find_one({"_id": ObjectId(campaign_id)})
    if not campaign:
        logger.error(f"Campaign {campaign_id} not found")
        return {"status": "error", "reason": "campaign_not_found"}

    if campaign["status"] != "sending":
        return {"status": "skipped", "reason": "campaign_not_sending"}

    contact = db.contacts.find_one({"_id": ObjectId(contact_id)})
    if not contact:
        logger.error(f"Contact {contact_id} not found")
        return {"status": "error", "reason": "contact_not_found"}

    email = contact["email"]
    stream = campaign.get("stream", contact.get("stream", "cold"))

    # 1. Suppression check
    if is_suppressed(email):
        logger.info(f"Skipping {email} — suppressed")
        _check_campaign_completion(db, campaign_id)
        return {"status": "skipped", "reason": "suppressed", "email": email}

    # 2. Warmup quota check
    if not check_warmup_quota(stream):
        logger.info(f"Warmup cap reached for stream '{stream}', requeueing {email}")
        raise self.retry(exc=Exception(f"Warmup cap reached for {stream}"))

    # 3. Domain rate limit check
    if not check_domain_rate_limit(email):
        logger.info(f"Domain rate limit reached for {email}, requeueing")
        raise self.retry(exc=Exception(f"Domain rate limit reached for {email.split('@')[1]}"))

    # 4. Stream routing
    from_addr = route_from_address(campaign["from_email"], stream)

    # 4. Render template
    html_body = render_template(campaign["html_body"], contact)
    text_body = render_template(campaign.get("text_body") or "", contact) or None
    subject = render_template(campaign["subject"], contact)

    # 5. Send via Postal
    try:
        result = send_message(
            to=email,
            from_addr=from_addr,
            from_name=campaign["from_name"],
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            tag=campaign_id,
        )
        postal_message_id = result.get("data", {}).get("messages", {}).get(email, {}).get("id")
    except Exception as exc:
        logger.error(f"Postal send failed for {email}: {exc}")
        raise self.retry(exc=exc)

    # 6. Increment counters
    increment_send_count(stream)
    increment_domain_count(email)

    # 7. Record sent event
    now = datetime.utcnow()
    db.events.insert_one({
        "campaign_id": campaign_id,
        "contact_id": contact_id,
        "email": email,
        "event_type": "sent",
        "stream": stream,
        "postal_message_id": postal_message_id,
        "metadata": {},
        "created_at": now,
    })

    # 8. Update contact engagement
    db.contacts.update_one(
        {"_id": ObjectId(contact_id)},
        {
            "$set": {"engagement.last_sent_at": now, "updated_at": now},
            "$inc": {"engagement.total_sent": 1},
        },
    )

    # 9. Update campaign stats + check completion
    db.campaigns.update_one(
        {"_id": ObjectId(campaign_id)},
        {"$inc": {"stats.sent": 1}},
    )

    _check_campaign_completion(db, campaign_id)

    logger.info(f"Sent to {email} via stream '{stream}' (postal_id: {postal_message_id})")
    return {"status": "sent", "email": email, "postal_message_id": postal_message_id}
