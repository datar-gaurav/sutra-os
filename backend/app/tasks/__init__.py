"""Celery tasks. Modules imported here are auto-registered with the worker."""

from app.tasks import rag_eval  # noqa: F401 — side-effect: task registration

__all__ = ["rag_eval"]
