from worker.celery_app import celery
from models.sync_db import get_sync_db
from core.engagement import calculate_engagement_score
import logging

logger = logging.getLogger(__name__)


@celery.task(name="recalculate_engagement_scores")
def recalculate_engagement_scores():
    db = get_sync_db()
    updated = 0

    for contact in db.contacts.find({"status": "active"}, {"engagement": 1}):
        score = calculate_engagement_score(contact.get("engagement", {}))
        db.contacts.update_one(
            {"_id": contact["_id"]},
            {"$set": {"engagement_score": score}},
        )
        updated += 1

    logger.info(f"Recalculated engagement scores for {updated} contacts")
    return {"updated": updated}
