from models.sync_db import get_sync_db
from core.suppression import add_suppression

SOFT_BOUNCE_THRESHOLD = 3
SOFT_BOUNCE_WINDOW_HOURS = 72


def check_auto_suppress_soft_bounce(email: str, campaign_id: str = None):
    db = get_sync_db()
    from datetime import datetime, timedelta

    since = datetime.utcnow() - timedelta(hours=SOFT_BOUNCE_WINDOW_HOURS)
    count = db.events.count_documents({
        "email": email,
        "event_type": "bounced",
        "bounce_type": "soft",
        "created_at": {"$gte": since},
    })

    if count >= SOFT_BOUNCE_THRESHOLD:
        add_suppression(email, "hard_bounce", source="auto_soft_bounce_rule", campaign_id=campaign_id)
        return True
    return False
