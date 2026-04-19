"""CLI entrypoint — run the RAG LLM-as-judge eval over a fixtures file.

Usage (inside backend container or local venv):

    python -m app.evals.run_eval                         # uses rag_fixtures.yaml
    python -m app.evals.run_eval --fixtures my.yaml      # custom fixtures
    python -m app.evals.run_eval --celery                # dispatch via Celery instead of in-process

Refuses to run unless settings.rag_eval_enabled is True — this is the only
switch standing between "eval code exists" and "eval calls the judge LLM and
costs money".
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import yaml

from app.config import settings
from app.core.tracing import init_tracing
from app.tasks.rag_eval import _run_eval_async, judge_case

logger = logging.getLogger(__name__)

DEFAULT_FIXTURES = Path(__file__).parent / "rag_fixtures.yaml"


def _load_cases(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text())
    cases = (data or {}).get("cases") or []
    if not cases:
        raise SystemExit(f"No cases found in {path}")
    return cases


def _print_row(case_id: str, retrieved: int, rel: int, gnd: int, note: str) -> None:
    print(f"  {case_id:<14} retrieved={retrieved:<3} rel={rel}/5  gnd={gnd}/5   {note}")


async def _run_inproc(cases: list[dict]) -> list[dict]:
    results = []
    for case in cases:
        try:
            verdict = await _run_eval_async(case)
        except Exception as e:
            logger.exception("case %s failed", case.get("id"))
            verdict = {
                "case_id": case.get("id", "unknown"),
                "retrieved": 0,
                "retrieval_relevance": 0,
                "groundedness": 0,
                "rationale": f"error: {e}",
            }
        results.append(verdict)
        _print_row(
            verdict.get("case_id", "?"),
            verdict.get("retrieved", 0),
            verdict.get("retrieval_relevance", 0),
            verdict.get("groundedness", 0),
            (verdict.get("rationale") or "")[:80],
        )
    return results


def _run_via_celery(cases: list[dict]) -> list[dict]:
    async_results = [judge_case.delay(c) for c in cases]
    results = []
    for ar in async_results:
        try:
            results.append(ar.get(timeout=120))
        except Exception as e:
            results.append({"case_id": "?", "error": str(e)})
    for v in results:
        _print_row(
            v.get("case_id", "?"),
            v.get("retrieved", 0),
            v.get("retrieval_relevance", 0),
            v.get("groundedness", 0),
            (v.get("rationale") or v.get("error") or "")[:80],
        )
    return results


def _summary(results: list[dict]) -> None:
    scored = [r for r in results if r.get("retrieval_relevance")]
    if not scored:
        print("\nNo scored results.")
        return
    avg_rel = sum(r["retrieval_relevance"] for r in scored) / len(scored)
    avg_gnd = sum(r["groundedness"] for r in scored) / len(scored)
    print(
        f"\n== Summary: {len(scored)}/{len(results)} scored — "
        f"avg retrieval_relevance={avg_rel:.2f} / groundedness={avg_gnd:.2f} =="
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", default=str(DEFAULT_FIXTURES))
    parser.add_argument("--celery", action="store_true", help="dispatch via Celery instead of in-process")
    args = parser.parse_args()

    if not settings.rag_eval_enabled:
        print(
            "RAG eval is disabled. Set RAG_EVAL_ENABLED=true in backend/.env "
            "(or the Settings UI) and retry. Enabling this will make judge-LLM "
            "calls against the model configured by RAG_EVAL_JUDGE_PROVIDER/MODEL "
            f"(currently {settings.rag_eval_judge_provider}/{settings.rag_eval_judge_model})."
        )
        return 2

    init_tracing()
    cases = _load_cases(Path(args.fixtures))
    print(f"Running {len(cases)} RAG eval cases (judge={settings.rag_eval_judge_provider}/{settings.rag_eval_judge_model})")
    print(f"  [mode={'celery' if args.celery else 'inproc'}] — see MLflow UI for spans/artifacts\n")

    if args.celery:
        results = _run_via_celery(cases)
    else:
        results = asyncio.run(_run_inproc(cases))

    _summary(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
