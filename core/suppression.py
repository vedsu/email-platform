from models.sync_db import get_sync_db


def is_suppressed(email: str) -> bool:
    db = get_sync_db()
    return db.suppressions.find_one({"email": email}) is not None


def add_suppression(email: str, reason: str, source: str = None, campaign_id: str = None):
    from datetime import datetime

    db = get_sync_db()
    try:
        db.suppressions.insert_one({
            "email": email,
            "reason": reason,
            "source": source,
            "campaign_id": campaign_id,
            "created_at": datetime.utcnow(),
        })
    except Exception as e:
        if "duplicate key" not in str(e):
            raise

    db.contacts.update_one(
        {"email": email},
        {"$set": {"status": "suppressed", "updated_at": datetime.utcnow()}},
    )
