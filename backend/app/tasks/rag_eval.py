"""RAG LLM-as-judge evaluation task.

Given a fixture (query + optional kb_ids + top_k), runs rag_service.search, then
asks a judge LLM to score retrieval relevance and groundedness on a 1-5 scale.
Scores land as attributes on the `rag_eval.judge` span so you can trend them in
MLflow over time.

Gated by settings.rag_eval_enabled — the task is a hard no-op if disabled, so
wiring this up does not cost anything until you flip the flag.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
from app.core.tracing import log_text, set_attrs, span
from app.worker import celery_app

logger = logging.getLogger(__name__)


JUDGE_SYSTEM_PROMPT = """You are an impartial retrieval-evaluation judge.

Given a user query and the chunks retrieved from a RAG system, score the retrieval on two axes:

1. retrieval_relevance (1-5)
   5 = every retrieved chunk is highly relevant to the query
   3 = at least one chunk is directly on-topic; others are tangential
   1 = none of the chunks are relevant

2. groundedness (1-5)
   5 = the chunks collectively contain enough information to fully answer the query
   3 = partial coverage — some parts of the query are answerable, others not
   1 = the chunks do not provide information to answer the query

Return ONLY a JSON object of the form:
{"retrieval_relevance": <int>, "groundedness": <int>, "rationale": "<one-sentence>"}

Do not include any other text, markdown, or code fences.
"""


def _fmt_chunks_for_judge(chunks: list[dict]) -> str:
    if not chunks:
        return "(no chunks retrieved)"
    lines = []
    for i, c in enumerate(chunks, 1):
        title = c.get("document_title") or "Unknown"
        body = (c.get("content") or "").strip()
        if len(body) > 1200:
            body = body[:1200] + "…"
        lines.append(f"[Chunk {i}] (doc: {title}, score={c.get('score')})\n{body}")
    return "\n\n".join(lines)


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_judge_output(raw: str) -> dict:
    """Extract the JSON verdict from the judge reply, tolerating stray prose."""
    if not raw:
        return {"retrieval_relevance": 0, "groundedness": 0, "rationale": "empty"}
    match = _JSON_RE.search(raw)
    if not match:
        return {"retrieval_relevance": 0, "groundedness": 0, "rationale": f"unparseable: {raw[:120]}"}
    try:
        obj = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"retrieval_relevance": 0, "groundedness": 0, "rationale": f"invalid json: {raw[:120]}"}

    def _clamp(v, lo=1, hi=5):
        try:
            v = int(v)
        except (TypeError, ValueError):
            return 0
        return max(lo, min(hi, v))

    return {
        "retrieval_relevance": _clamp(obj.get("retrieval_relevance")),
        "groundedness": _clamp(obj.get("groundedness")),
        "rationale": str(obj.get("rationale", ""))[:500],
    }


async def _run_eval_async(case: dict) -> dict:
    """Run one eval case. Returns the verdict dict + retrieval stats."""
    from app.core.llm_registry import llm_registry
    from app.core.rag_service import search
    from app.db.session import async_session_factory

    case_id = case.get("id", "unknown")
    query = case["query"]
    kb_ids = case.get("kb_ids") or None
    top_k = int(case.get("top_k") or 5)

    with span(
        "rag_eval.judge",
        case_id=case_id,
        query_len=len(query),
        top_k=top_k,
        judge_provider=settings.rag_eval_judge_provider,
        judge_model=settings.rag_eval_judge_model,
    ) as s:
        log_text("query.txt", query)

        # Retrieval — nested rag.retrieve span comes for free
        async with async_session_factory() as db:
            chunks = await search(db, query=query, kb_ids=kb_ids, top_k=top_k)

        log_text("retrieved_chunks.json", json.dumps(chunks, indent=2, default=str))

        if not chunks:
            verdict = {"retrieval_relevance": 1, "groundedness": 1, "rationale": "no chunks retrieved"}
            set_attrs(
                s,
                retrieved=0,
                retrieval_relevance=verdict["retrieval_relevance"],
                groundedness=verdict["groundedness"],
                skipped_judge=True,
            )
            return {"case_id": case_id, "retrieved": 0, **verdict}

        # Build judge prompt
        judge_user = (
            f"User query:\n{query}\n\n"
            f"Retrieved chunks:\n{_fmt_chunks_for_judge(chunks)}\n\n"
            f"Return the JSON verdict now."
        )
        log_text("judge_prompt.txt", judge_user)

        # Invoke judge LLM
        judge = llm_registry.get_chat_model(
            provider=settings.rag_eval_judge_provider,
            model=settings.rag_eval_judge_model,
            temperature=0.0,
            max_tokens=300,
            streaming=False,
        )
        t0 = time.perf_counter()
        try:
            resp = await judge.ainvoke([
                SystemMessage(content=JUDGE_SYSTEM_PROMPT),
                HumanMessage(content=judge_user),
            ])
            raw = resp.content if isinstance(resp.content, str) else str(resp.content)
        except Exception as e:
            logger.error(f"Judge LLM call failed for case {case_id}: {e}")
            set_attrs(s, judge_error=str(e)[:500], retrieved=len(chunks))
            return {
                "case_id": case_id,
                "retrieved": len(chunks),
                "retrieval_relevance": 0,
                "groundedness": 0,
                "rationale": f"judge failed: {e}",
            }

        judge_ms = int((time.perf_counter() - t0) * 1000)
        log_text("judge_response.txt", raw)
        verdict = _parse_judge_output(raw)

        set_attrs(
            s,
            retrieved=len(chunks),
            retrieval_relevance=verdict["retrieval_relevance"],
            groundedness=verdict["groundedness"],
            judge_latency_ms=judge_ms,
        )
        return {"case_id": case_id, "retrieved": len(chunks), **verdict}


@celery_app.task(name="app.tasks.rag_eval.judge_case")
def judge_case(case: dict) -> dict:
    """Celery entrypoint — runs one fixture case and returns the verdict.

    Hard no-op if settings.rag_eval_enabled is False so this task is safe to
    ship enabled-in-code but off-at-runtime.
    """
    if not settings.rag_eval_enabled:
        logger.warning("rag_eval disabled by config — skipping case %s", case.get("id"))
        return {
            "case_id": case.get("id", "unknown"),
            "skipped": True,
            "reason": "rag_eval_enabled=false",
        }

    return asyncio.run(_run_eval_async(case))
