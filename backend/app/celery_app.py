"""Redis-backed Celery application; no connections are opened on import."""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "insurance_agent", broker=settings.redis_url,
    backend=settings.celery_result_backend or settings.redis_url,
    include=["app.tasks.claims"],
)
celery_app.conf.update(
    task_serializer="json", result_serializer="json", accept_content=["json"],
    task_track_started=True, task_acks_late=True, task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1, worker_concurrency=1,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": settings.claim_task_timeout_seconds + 300},
    result_expires=3600, timezone="UTC", enable_utc=True,
    task_time_limit=settings.claim_task_timeout_seconds,
)
