from datetime import datetime
from bson import ObjectId
from worker.celery_app import celery
from models.sync_db import get_sync_db
import logging

logger = logging.getLogger(__name__)


@celery.task(name="check_scheduled_campaigns")
def check_scheduled_campaigns():
    db = get_sync_db()
    now = datetime.utcnow()

    cursor = db.campaigns.find({
        "status": "scheduled",
        "scheduled_at": {"$lte": now},
    })

    for campaign in cursor:
        campaign_id = str(campaign["_id"])
        logger.info(f"Launching scheduled campaign: {campaign['name']} ({campaign_id})")

        query = {"status": "active"}
        list_ids = campaign.get("target_list_ids", [])
        if list_ids:
            query["list_ids"] = {"$in": list_ids}

        total = db.contacts.count_documents(query)
        if total == 0:
            logger.warning(f"Scheduled campaign {campaign_id} has no matching contacts, skipping")
            continue

        db.campaigns.update_one(
            {"_id": campaign["_id"]},
            {
                "$set": {
                    "status": "sending",
                    "started_at": now,
                    "stats.total_recipients": total,
                }
            },
        )

        from worker.tasks import send_to_recipient

        contacts = db.contacts.find(query, {"_id": 1})
        enqueued = 0
        for contact in contacts:
            send_to_recipient.delay(campaign_id, str(contact["_id"]))
            enqueued += 1

        logger.info(f"Scheduled campaign {campaign_id}: enqueued {enqueued} recipients")
