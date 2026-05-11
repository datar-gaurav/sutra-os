"""Per-turn skill router.

Picks 0–2 skills to load for a given user turn from the agent's attached set.
Three strategies, switchable via settings:

  - "embedding"  (default): cosine similarity between the user message and each
                            skill's load_trigger embedding. Fast, deterministic.
  - "llm":                  a small LLM reads the skill index and decides.
                            More accurate on negations and ambiguous intent.
  - "hybrid":               embedding prefilter to top-N candidates, LLM picks
                            from that shortlist when the top two are close.

Bypass conditions (no scoring, no LLM call):
  - Pinned skills (always_load=True) load unconditionally.
  - If the unpinned attached set has ≤1 item, load whatever is there.
  - If no embedding model AND no LLM router are available, load everything
    attached. Degraded but always functional.
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Literal

from app.config import settings
from app.core.embeddings import embedding_service

logger = logging.getLogger(__name__)


@dataclass
class AttachedSkill:
    """One row of agent_skills, hydrated with what the router needs."""

    slug: str
    name: str
    description: str
    always_load: bool
    config_overrides: dict
    trigger_embedding: list[float] | None  # parsed from JSON, may be None
    routing_threshold: float | None        # per-skill override; falls back to global


@dataclass
class RoutingDecision:
    load_slugs: list[str]
    scores: dict[str, float] = field(default_factory=dict)
    strategy: str = "embedding"
    fallback_used: bool = False
    latency_ms: int = 0
    reason: str = ""


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ─── Strategies ──────────────────────────────────────────────────────────────


class EmbeddingStrategy:
    """Cosine similarity against pre-computed trigger embeddings."""

    name = "embedding"

    def __init__(self, default_threshold: float, top_k: int):
        self.default_threshold = default_threshold
        self.top_k = top_k

    async def score(self, message: str, candidates: list[AttachedSkill]) -> dict[str, float]:
        msg_emb = await embedding_service.aembed(message)
        if msg_emb is None:
            return {}
        return {
            c.slug: _cosine(msg_emb, c.trigger_embedding)
            for c in candidates
            if c.trigger_embedding
        }

    def pick(
        self, scores: dict[str, float], candidates: list[AttachedSkill]
    ) -> list[str]:
        if not scores:
            return []
        thresholds = {c.slug: (c.routing_threshold or self.default_threshold) for c in candidates}
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        return [slug for slug, s in ranked[: self.top_k] if s >= thresholds.get(slug, self.default_threshold)]


class LLMStrategy:
    """A small LLM reads the index and returns the slugs to load.

    Primary path: Ollama via langchain_ollama (user said they run M4 + Ollama).
    Failure path: fall back to load-all.
    """

    name = "llm"

    def __init__(self, model: str, base_url: str, top_k: int):
        self.model = model
        self.base_url = base_url
        self.top_k = top_k
        self._llm = None  # lazy

    def _get_llm(self):
        if self._llm is not None:
            return self._llm
        try:
            from langchain_ollama import ChatOllama
            self._llm = ChatOllama(
                model=self.model,
                base_url=self.base_url,
                temperature=0.0,
                num_predict=120,
                format="json",
            )
        except Exception as e:
            logger.warning(f"LLMStrategy: Ollama unavailable ({e}); will fall back to load-all")
            self._llm = None
        return self._llm

    async def decide(self, message: str, candidates: list[AttachedSkill]) -> list[str] | None:
        llm = self._get_llm()
        if llm is None:
            return None

        index = "\n".join(f"- {c.slug}: {c.description}" for c in candidates)
        prompt = (
            "You are routing among the user's attached skills. Read the skill "
            "descriptions (each says 'Load when ...') and pick 0 to "
            f"{self.top_k} that apply to the user's message.\n\n"
            f"Skills available:\n{index}\n\n"
            f'User message: "{message}"\n\n'
            'Reply with JSON: {"load": ["slug1", ...], "reason": "<short>"}. '
            'If no skill applies, reply {"load": [], "reason": "..."}.'
        )
        try:
            from langchain_core.messages import HumanMessage
            resp = await llm.ainvoke([HumanMessage(content=prompt)])
            content = resp.content if hasattr(resp, "content") else str(resp)
            parsed = json.loads(content)
            chosen = parsed.get("load") or []
            if not isinstance(chosen, list):
                return None
            valid_slugs = {c.slug for c in candidates}
            return [s for s in chosen if isinstance(s, str) and s in valid_slugs][: self.top_k]
        except Exception as e:
            logger.warning(f"LLMStrategy: routing failed ({e})")
            return None


class HybridStrategy:
    """Embedding prefilter; LLM picks when top results are ambiguous."""

    name = "hybrid"

    def __init__(self, embedding: EmbeddingStrategy, llm: LLMStrategy, ambiguity_delta: float):
        self.embedding = embedding
        self.llm = llm
        self.ambiguity_delta = ambiguity_delta

    async def run(
        self, message: str, candidates: list[AttachedSkill]
    ) -> tuple[list[str], dict[str, float], bool]:
        scores = await self.embedding.score(message, candidates)
        if not scores:
            chosen = await self.llm.decide(message, candidates)
            return (chosen or [], {}, chosen is None)

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        top_score = ranked[0][1]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        is_clear_winner = (top_score - second_score) >= self.ambiguity_delta

        threshold = self.embedding.default_threshold
        candidates_by_slug = {c.slug: c for c in candidates}
        top_threshold = candidates_by_slug[ranked[0][0]].routing_threshold or threshold

        if is_clear_winner and top_score >= top_threshold:
            return ([ranked[0][0]], scores, False)

        # Ambiguous — pass top-N to LLM for the final pick
        shortlist_slugs = {slug for slug, _ in ranked[: max(self.embedding.top_k + 1, 3)]}
        shortlist = [c for c in candidates if c.slug in shortlist_slugs]
        chosen = await self.llm.decide(message, shortlist)
        if chosen is None:
            # LLM failed — fall back to embedding pick
            return (self.embedding.pick(scores, candidates), scores, True)
        return (chosen, scores, False)


# ─── Router (top-level entry point) ──────────────────────────────────────────


class SkillRouter:
    def __init__(self) -> None:
        threshold = float(getattr(settings, "skill_routing_threshold", 0.4))
        top_k = int(getattr(settings, "skill_router_top_k", 2))
        ambiguity_delta = float(getattr(settings, "skill_router_ambiguity_delta", 0.05))
        llm_model = getattr(settings, "skill_router_llm_model", "llama3.1:8b")
        ollama_base = getattr(settings, "ollama_base_url", "http://localhost:11434")

        self._embedding = EmbeddingStrategy(default_threshold=threshold, top_k=top_k)
        self._llm = LLMStrategy(model=llm_model, base_url=ollama_base, top_k=top_k)
        self._hybrid = HybridStrategy(self._embedding, self._llm, ambiguity_delta)

    def _resolve_strategy(self) -> Literal["embedding", "llm", "hybrid"]:
        raw = (getattr(settings, "skill_router_strategy", "embedding") or "embedding").lower()
        if raw not in {"embedding", "llm", "hybrid"}:
            return "embedding"
        return raw  # type: ignore[return-value]

    async def route(
        self,
        message: str,
        attached: list[AttachedSkill],
    ) -> RoutingDecision:
        t0 = time.monotonic()
        pinned = [a.slug for a in attached if a.always_load]
        unpinned = [a for a in attached if not a.always_load]

        # Bypass: nothing to decide
        if not unpinned:
            return RoutingDecision(
                load_slugs=pinned,
                strategy="bypass",
                latency_ms=int((time.monotonic() - t0) * 1000),
                reason="no unpinned skills",
            )
        if len(unpinned) <= 1:
            return RoutingDecision(
                load_slugs=pinned + [unpinned[0].slug],
                strategy="bypass",
                latency_ms=int((time.monotonic() - t0) * 1000),
                reason="only one unpinned skill — no choice to make",
            )

        strategy = self._resolve_strategy()
        scores: dict[str, float] = {}
        fallback_used = False

        if strategy == "embedding":
            scores = await self._embedding.score(message, unpinned)
            if not scores:
                # No embedding model — fall through to load-all
                chosen = [a.slug for a in unpinned]
                fallback_used = True
            else:
                chosen = self._embedding.pick(scores, unpinned)

        elif strategy == "llm":
            chosen = await self._llm.decide(message, unpinned)
            if chosen is None:
                chosen = [a.slug for a in unpinned]
                fallback_used = True

        else:  # hybrid
            chosen, scores, fallback_used = await self._hybrid.run(message, unpinned)

        return RoutingDecision(
            load_slugs=pinned + chosen,
            scores=scores,
            strategy=strategy,
            fallback_used=fallback_used,
            latency_ms=int((time.monotonic() - t0) * 1000),
        )


# Module singleton
skill_router = SkillRouter()


def parse_trigger_embedding(stored: str | None) -> list[float] | None:
    """Decode the JSON-encoded embedding column."""
    if not stored:
        return None
    try:
        v = json.loads(stored)
        if isinstance(v, list) and all(isinstance(x, (int, float)) for x in v):
            return [float(x) for x in v]
    except Exception:
        pass
    return None
