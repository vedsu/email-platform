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

import worker.scheduler  # noqa: F401 — registers beat schedule
