"""Celery worker configuration."""

from celery import Celery
from celery.signals import worker_process_init

from app.config import settings

celery_app = Celery(
    "sutra",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)

# Register task modules so workers see them.
celery_app.autodiscover_tasks(["app.tasks"])


@worker_process_init.connect
def _init_worker_tracing(**_kwargs) -> None:
    """Initialize MLflow tracing per worker process.

    Workers fork from the master, so module-level state isn't shared — tracing
    must be (re-)initialized in each child process for auto-memory-extraction
    and other Celery-side LLM work to land in MLflow.
    """
    try:
        from app.core.tracing import init_tracing
        init_tracing()
    except Exception:
        # Tracing init is failure-isolated internally; this catch is belt-and-suspenders.
        pass
