"""MLflow tracing — single entry point for all LLMOps observability.

Every public function in this module is failure-isolated: if MLflow is
disabled, unreachable, or raises, calls degrade silently to no-ops so that
tracing can never break a request path.

Wire-up:
- FastAPI lifespan calls init_tracing() once at startup.
- Celery worker_process_init signal calls init_tracing() per worker process.
- Everything else imports `span` / `log_text` / `set_attrs` from here.
"""

import contextlib
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_ENABLED: bool = False
_mlflow = None  # lazy import; populated by init_tracing()


def init_tracing() -> None:
    """Initialize MLflow + LangChain autolog. Idempotent and failure-isolated."""
    global _ENABLED, _mlflow

    if _ENABLED:
        return
    if not settings.mlflow_enabled:
        logger.info("MLflow tracing disabled (MLFLOW_ENABLED=false)")
        return

    try:
        import mlflow
        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        mlflow.set_experiment(settings.mlflow_experiment)
        # LangChain autolog covers ChatOpenAI/ChatAnthropic/ChatGoogle/etc.
        # plus LangGraph node spans — gives us provider-agnostic traces for free.
        # MLflow 3 autolog signature is minimal; `log_traces=True` is the default but kept explicit.
        mlflow.langchain.autolog(log_traces=True, silent=True)
        _mlflow = mlflow
        _ENABLED = True
        logger.info(
            f"✅ MLflow tracing enabled (uri={settings.mlflow_tracking_uri}, "
            f"experiment={settings.mlflow_experiment})"
        )
    except Exception as e:
        logger.warning(f"MLflow init failed, tracing disabled: {e}")


def is_enabled() -> bool:
    return _ENABLED


@contextlib.contextmanager
def span(name: str, **attributes: Any):
    """Open an MLflow span. Silent no-op when disabled or on failure.

    Usage:
        with span("orchestrator.chat_turn", agent_id=..., request_id=...) as s:
            ...
            if s: s.set_attribute("cost_usd", cost)
    """
    if not _ENABLED or _mlflow is None:
        yield None
        return
    try:
        with _mlflow.start_span(name=name, attributes=_clean(attributes)) as s:
            yield s
    except Exception as e:
        logger.debug(f"span({name}) failed: {e}")
        yield None


def set_attrs(span_obj: Any, **attributes: Any) -> None:
    """Set multiple attributes on a span. Tolerant of None and exceptions."""
    if span_obj is None:
        return
    try:
        span_obj.set_attributes(_clean(attributes))
    except Exception as e:
        logger.debug(f"set_attrs failed: {e}")


def log_text(artifact_name: str, content: str) -> None:
    """Log a string as an MLflow artifact on the active run/trace.

    Used for prompt and response payloads — the rich UI bits.
    No-op when tracing disabled or content is empty.
    """
    if not _ENABLED or _mlflow is None or not content:
        return
    try:
        _mlflow.log_text(content, artifact_name)
    except Exception as e:
        logger.debug(f"log_text({artifact_name}) failed: {e}")


def _clean(attrs: dict[str, Any]) -> dict[str, Any]:
    """Drop None values; coerce non-primitives to str so MLflow doesn't reject them."""
    out: dict[str, Any] = {}
    for k, v in attrs.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
        elif isinstance(v, (list, tuple)) and all(isinstance(x, (str, int, float, bool)) for x in v):
            out[k] = list(v)
        else:
            out[k] = str(v)
    return out
