import logging
from datetime import datetime
from bson import ObjectId

from worker.celery_app import celery
from models.sync_db import get_sync_db
from core.suppression import is_suppressed
from core.warmup import check_warmup_quota, increment_send_count
from core.render import render_template
from core.postal_client import send_message
from core.rate_limiter import check_domain_rate_limit, increment_domain_count

logger = logging.getLogger(__name__)


def _check_campaign_completion(db, campaign_id: str):
    campaign = db.campaigns.find_one({"_id": ObjectId(campaign_id)})
    if not campaign or campaign["status"] != "sending":
        return

    total = campaign["stats"].get("total_recipients", 0)

    # Count unique contacts with any event (sent, bounced, skipped) — no double-counting
    processed = len(db.events.distinct("contact_id", {"campaign_id": campaign_id}))
    logger.info(f"Campaign {campaign_id} completion check: processed={processed} total={total}")

    if processed >= total:
        db.campaigns.update_one(
            {"_id": ObjectId(campaign_id), "status": "sending"},
            {"$set": {"status": "completed", "completed_at": datetime.utcnow()}},
        )
        logger.info(f"Campaign {campaign_id} marked completed")


MAX_SEND_ATTEMPTS = 3


@celery.task(name="send_to_recipient", bind=True, max_retries=3, default_retry_delay=60)
def send_to_recipient(self, campaign_id: str, contact_id: str, attempt: int = 1):
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

    STREAM_POOL = {"optin": 2, "engaged": 3, "cold": 4}
    ip_pool_id = STREAM_POOL.get(stream)

    # 1. Suppression check
    if is_suppressed(email):
        logger.info(f"Skipping {email} — suppressed")
        inserted = db.events.update_one(
            {"campaign_id": campaign_id, "contact_id": contact_id, "event_type": "skipped"},
            {"$setOnInsert": {"email": email, "event_type": "skipped", "reason": "suppressed",
                              "campaign_id": campaign_id, "contact_id": contact_id,
                              "created_at": datetime.utcnow()}},
            upsert=True,
        )
        if inserted.upserted_id:
            db.campaigns.update_one(
                {"_id": ObjectId(campaign_id)},
                {"$inc": {"stats.skipped": 1}},
            )
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

    from_addr = campaign["from_email"]

    # 4. Render template
    html_body = render_template(campaign["html_body"], contact)
    text_body = render_template(campaign.get("text_body") or "", contact) or None
    subject = render_template(campaign["subject"], contact)

    logger.info(f"Sending to {email} from {from_addr} ({campaign['from_name']})")

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
            ip_pool_id=ip_pool_id,
        )
    except Exception as exc:
        logger.error(f"Postal send failed for {email}: {exc}")
        raise self.retry(exc=exc)

    now = datetime.utcnow()

    # If Postal returned an application-level error, retry back-of-queue (up to MAX_SEND_ATTEMPTS)
    if result.get("status") != "success":
        error_data = result.get("data", {})
        error_code = error_data.get("code", "UnknownError")
        error_msg = error_data.get("message", str(result))
        bounce_message = f"{error_code}: {error_msg}"
        logger.error(f"Postal rejected {email} (attempt {attempt}/{MAX_SEND_ATTEMPTS}): {bounce_message}")

        if attempt < MAX_SEND_ATTEMPTS:
            # Re-queue at back of queue (countdown=0 puts it after currently-queued tasks)
            send_to_recipient.apply_async(
                args=[campaign_id, contact_id],
                kwargs={"attempt": attempt + 1},
                countdown=0,
            )
            return {"status": "retrying", "email": email, "attempt": attempt, "reason": bounce_message}

        # Final attempt failed — record permanent bounce
        db.events.insert_one({
            "campaign_id": campaign_id,
            "contact_id": contact_id,
            "email": email,
            "event_type": "bounced",
            "stream": stream,
            "postal_message_id": None,
            "bounce_type": "hard",
            "bounce_message": bounce_message,
            "metadata": {"attempts": attempt},
            "created_at": now,
        })
        db.campaigns.update_one(
            {"_id": ObjectId(campaign_id)},
            {"$inc": {"stats.bounced": 1}},
        )
        _check_campaign_completion(db, campaign_id)
        return {"status": "bounced", "email": email, "reason": bounce_message}

    postal_message_id = result.get("data", {}).get("messages", {}).get(email, {}).get("id")

    # Capture sending IP while queued_message still exists (Postal worker polls every 5s)
    sending_ip = None
    if postal_message_id:
        try:
            from core.postal_mariadb import get_sending_ip_for_message
            sending_ip = get_sending_ip_for_message(postal_message_id)
        except Exception as e:
            logger.debug(f"Could not fetch sending IP for msg {postal_message_id}: {e}")

    # 6. Increment counters
    increment_send_count(stream)
    increment_domain_count(email)

    # 7. Record sent event
    db.events.insert_one({
        "campaign_id": campaign_id,
        "contact_id": contact_id,
        "email": email,
        "event_type": "sent",
        "stream": stream,
        "postal_message_id": postal_message_id,
        "ip_pool_id": ip_pool_id,
        "ip_pool_name": stream,
        "sending_ip": sending_ip,
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
