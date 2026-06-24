import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from celery import Celery
from core.config import settings

celery = Celery(
    "email_platform",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

celery.autodiscover_tasks(["worker"])

celery.conf.beat_schedule = {
    "check-scheduled-campaigns": {
        "task": "check_scheduled_campaigns",
        "schedule": 60.0,
    },
    "recalculate-engagement-scores": {
        "task": "recalculate_engagement_scores",
        "schedule": 3600.0,
    },
}
