"""SkillRouter — three strategies + bypass paths."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.skills.router import (
    AttachedSkill,
    EmbeddingStrategy,
    HybridStrategy,
    LLMStrategy,
    SkillRouter,
    _cosine,
    parse_trigger_embedding,
)


def _att(slug: str, emb: list[float] | None = None, *, pinned: bool = False, threshold: float | None = None):
    return AttachedSkill(
        slug=slug,
        name=slug,
        description=f"Load when user wants {slug}.",
        always_load=pinned,
        config_overrides={},
        trigger_embedding=emb,
        routing_threshold=threshold,
    )


# ─── Utilities ───────────────────────────────────────────────────────────────


def test_cosine_known_values():
    assert _cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert _cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert _cosine([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_cosine_handles_zero_vectors():
    assert _cosine([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert _cosine([], []) == 0.0
    assert _cosine([1.0], [1.0, 0.0]) == 0.0  # mismatched lengths


def test_parse_trigger_embedding_handles_garbage():
    assert parse_trigger_embedding(None) is None
    assert parse_trigger_embedding("not json") is None
    assert parse_trigger_embedding("[1, 2, 'x']") is None
    assert parse_trigger_embedding("[0.1, 0.2, 0.3]") == [0.1, 0.2, 0.3]


# ─── Bypass conditions ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_router_bypasses_with_no_unpinned_skills():
    router = SkillRouter()
    decision = await router.route("anything", [_att("a", pinned=True), _att("b", pinned=True)])
    assert decision.strategy == "bypass"
    assert sorted(decision.load_slugs) == ["a", "b"]


@pytest.mark.asyncio
async def test_router_bypasses_with_single_unpinned_skill():
    router = SkillRouter()
    decision = await router.route("write a query", [_att("sql-query")])
    assert decision.strategy == "bypass"
    assert decision.load_slugs == ["sql-query"]


@pytest.mark.asyncio
async def test_router_empty_input():
    router = SkillRouter()
    decision = await router.route("anything", [])
    assert decision.load_slugs == []


# ─── EmbeddingStrategy ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_embedding_strategy_picks_top_above_threshold():
    candidates = [
        _att("sql-query",       emb=[1.0, 0.0]),
        _att("code-review",     emb=[0.0, 1.0]),
    ]
    strat = EmbeddingStrategy(default_threshold=0.5, top_k=2)
    with patch("app.skills.router.embedding_service.aembed", new=AsyncMock(return_value=[1.0, 0.0])):
        scores = await strat.score("write a sql query", candidates)
    assert scores["sql-query"] == pytest.approx(1.0)
    assert scores["code-review"] == pytest.approx(0.0)
    picked = strat.pick(scores, candidates)
    assert picked == ["sql-query"]


@pytest.mark.asyncio
async def test_embedding_strategy_falls_through_when_no_model():
    candidates = [_att("sql-query", emb=[1.0]), _att("code-review", emb=[0.0])]
    strat = EmbeddingStrategy(default_threshold=0.4, top_k=2)
    with patch("app.skills.router.embedding_service.aembed", new=AsyncMock(return_value=None)):
        scores = await strat.score("anything", candidates)
    assert scores == {}


@pytest.mark.asyncio
async def test_router_embedding_full_loop():
    router = SkillRouter()
    candidates = [
        _att("sql-query",       emb=[1.0, 0.0]),
        _att("code-review",     emb=[0.0, 1.0]),
        _att("email-drafting",  emb=[0.3, 0.7]),   # cosine≈0.39 vs [1,0], below 0.5 threshold
    ]
    with patch("app.skills.router.embedding_service.aembed", new=AsyncMock(return_value=[1.0, 0.0])):
        decision = await router.route("write a sql query", candidates)
    assert decision.strategy == "embedding"
    assert decision.load_slugs == ["sql-query"]
    assert not decision.fallback_used


@pytest.mark.asyncio
async def test_router_embedding_falls_back_to_load_all_when_no_model():
    router = SkillRouter()
    candidates = [_att("a", emb=[1.0]), _att("b", emb=[0.0])]
    with patch("app.skills.router.embedding_service.aembed", new=AsyncMock(return_value=None)):
        decision = await router.route("anything", candidates)
    assert decision.fallback_used
    assert set(decision.load_slugs) == {"a", "b"}


# ─── LLMStrategy ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_strategy_returns_none_when_ollama_unavailable():
    strat = LLMStrategy(model="llama3.1:8b", base_url="http://nope:99999", top_k=2)
    strat._llm = None  # simulate failed init below
    with patch.object(strat, "_get_llm", return_value=None):
        result = await strat.decide("anything", [_att("a"), _att("b")])
    assert result is None


@pytest.mark.asyncio
async def test_llm_strategy_parses_json_and_filters_invalid_slugs():
    class _FakeResp:
        content = '{"load": ["sql-query", "ghost-skill"], "reason": "user wants sql"}'

    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(return_value=_FakeResp())

    strat = LLMStrategy(model="m", base_url="x", top_k=2)
    with patch.object(strat, "_get_llm", return_value=fake_llm):
        result = await strat.decide("write a query", [_att("sql-query"), _att("code-review")])
    assert result == ["sql-query"]  # ghost-skill was filtered (not in candidates)


# ─── HybridStrategy ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hybrid_uses_embedding_when_clear_winner():
    emb = EmbeddingStrategy(default_threshold=0.3, top_k=2)
    llm = LLMStrategy(model="m", base_url="x", top_k=2)
    hybrid = HybridStrategy(emb, llm, ambiguity_delta=0.05)

    candidates = [_att("a", emb=[1.0, 0.0]), _att("b", emb=[0.0, 1.0])]
    with patch("app.skills.router.embedding_service.aembed", new=AsyncMock(return_value=[1.0, 0.0])):
        chosen, scores, fallback = await hybrid.run("anything", candidates)
    assert chosen == ["a"]
    assert not fallback


@pytest.mark.asyncio
async def test_hybrid_defers_to_llm_when_ambiguous():
    emb = EmbeddingStrategy(default_threshold=0.3, top_k=2)
    llm = LLMStrategy(model="m", base_url="x", top_k=2)
    hybrid = HybridStrategy(emb, llm, ambiguity_delta=0.05)

    # Two skills very close in similarity
    candidates = [_att("a", emb=[1.0, 0.0]), _att("b", emb=[0.99, 0.14])]

    class _FakeResp:
        content = '{"load": ["b"], "reason": "test"}'

    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(return_value=_FakeResp())

    with patch("app.skills.router.embedding_service.aembed", new=AsyncMock(return_value=[1.0, 0.0])), \
         patch.object(llm, "_get_llm", return_value=fake_llm):
        chosen, scores, fallback = await hybrid.run("anything", candidates)
    assert chosen == ["b"]
    assert not fallback
