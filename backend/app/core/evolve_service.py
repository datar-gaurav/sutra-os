"""Evolve service — core engine for daily analysis and competitor monitoring."""

import json
import logging
from datetime import datetime, timedelta, timezone


def _utcnow() -> datetime:
    """Return current UTC time as a naive datetime (for TIMESTAMP WITHOUT TIME ZONE columns)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.models.evolve import (
    EvolveRun,
    EvolveRunStatus,
    EvolveSuggestion,
    SuggestionSource,
    SuggestionStatus,
)

logger = logging.getLogger(__name__)


async def run_daily_analysis() -> EvolveRun:
    """Analyze platform health, errors, and performance. Generate suggestions."""
    async with async_session_factory() as db:
        run = EvolveRun(
            run_type="daily_analysis",
            started_at=_utcnow(),
            status=EvolveRunStatus.running.value,
        )
        db.add(run)
        await db.flush()
        await db.refresh(run)
        run_id = run.id
        await db.commit()

    analysis_data = {}
    errors = []
    suggestion_count = 0

    # Step 1: Gather platform stats
    try:
        from app.tools.evolve_tools import _get_platform_stats
        stats_json = await _get_platform_stats(hours=24)
        analysis_data["platform_stats"] = json.loads(stats_json)
    except Exception as e:
        errors.append(f"platform_stats: {e}")
        logger.warning(f"[Evolve] Platform stats failed: {e}")

    # Step 2: Gather error patterns
    try:
        from app.tools.evolve_tools import _get_error_patterns
        patterns_json = await _get_error_patterns(hours=24, limit=10)
        analysis_data["error_patterns"] = json.loads(patterns_json)
    except Exception as e:
        errors.append(f"error_patterns: {e}")
        logger.warning(f"[Evolve] Error patterns failed: {e}")

    # Step 3: Get agent performance data
    try:
        from app.models.agent import Agent
        from app.models.trace import ExecutionTrace
        from sqlalchemy import Integer, case, cast

        async with async_session_factory() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            result = await db.execute(
                select(
                    ExecutionTrace.agent_id,
                    func.count(ExecutionTrace.id).label("total"),
                    func.sum(
                        case((ExecutionTrace.had_error == True, 1), else_=0)
                    ).label("errors"),
                    func.avg(ExecutionTrace.latency_ms).label("avg_lat"),
                ).where(ExecutionTrace.created_at >= cutoff)
                .group_by(ExecutionTrace.agent_id)
                .order_by(func.count(ExecutionTrace.id).desc())
                .limit(20)
            )
            agent_perfs = []
            for row in result.all():
                agent = await db.get(Agent, row.agent_id) if row.agent_id else None
                agent_perfs.append({
                    "agent_id": row.agent_id,
                    "agent_name": agent.name if agent else "unknown",
                    "total_invocations": row.total,
                    "errors": row.errors or 0,
                    "avg_latency_ms": round(float(row.avg_lat or 0), 1),
                })
            analysis_data["agent_performance"] = agent_perfs
    except Exception as e:
        errors.append(f"agent_performance: {e}")
        logger.warning(f"[Evolve] Agent performance failed: {e}")

    # Step 4: Invoke Evolve agent LLM for analysis
    try:
        suggestions = await _generate_suggestions_via_llm(analysis_data, "daily_analysis", run_id)
        suggestion_count = len(suggestions)
    except Exception as e:
        errors.append(f"llm_analysis: {e}")
        logger.warning(f"[Evolve] LLM analysis failed: {e}")

    # Finalize run
    status = EvolveRunStatus.completed.value
    if errors and suggestion_count == 0:
        status = EvolveRunStatus.failed.value
    elif errors:
        status = EvolveRunStatus.partial.value

    async with async_session_factory() as db:
        run = await db.get(EvolveRun, run_id)
        if run:
            run.completed_at = _utcnow()
            run.status = status
            run.stats = analysis_data.get("platform_stats", {})
            run.error_log = "\n".join(errors) if errors else None
            run.suggestions_generated = suggestion_count
            await db.commit()
            await db.refresh(run)

    logger.info(f"[Evolve] Daily analysis complete: {suggestion_count} suggestions, status={status}")
    return run


async def run_competitor_monitor() -> EvolveRun:
    """Monitor competitor repos for new releases and generate gap analysis."""
    async with async_session_factory() as db:
        run = EvolveRun(
            run_type="competitor_monitor",
            started_at=_utcnow(),
            status=EvolveRunStatus.running.value,
        )
        db.add(run)
        await db.flush()
        await db.refresh(run)
        run_id = run.id
        await db.commit()

    errors = []
    competitor_data = {}
    suggestion_count = 0

    from app.core.system_settings import sys_settings
    raw = sys_settings.get("evolve_competitor_repos")
    if not raw:
        from app.config import settings
        raw = settings.evolve_competitor_repos
    repos = [r.strip() for r in raw.split(",") if r.strip()]

    for repo in repos:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"https://api.github.com/repos/{repo}/releases",
                    params={"per_page": 3},
                    headers={"Accept": "application/vnd.github+json"},
                )
                if resp.status_code == 200:
                    releases = resp.json()
                    competitor_data[repo] = [
                        {
                            "tag": r.get("tag_name"),
                            "name": r.get("name"),
                            "published_at": r.get("published_at"),
                            "body": (r.get("body") or "")[:500],
                        }
                        for r in releases
                    ]
                else:
                    competitor_data[repo] = {"error": f"HTTP {resp.status_code}"}
        except Exception as e:
            errors.append(f"repo {repo}: {e}")
            competitor_data[repo] = {"error": str(e)}

    # Invoke LLM for gap analysis
    try:
        analysis_data = {"competitor_releases": competitor_data}
        suggestions = await _generate_suggestions_via_llm(analysis_data, "competitor_monitor", run_id)
        suggestion_count = len(suggestions)
    except Exception as e:
        errors.append(f"llm_gap_analysis: {e}")

    status = EvolveRunStatus.completed.value
    if errors and suggestion_count == 0:
        status = EvolveRunStatus.failed.value
    elif errors:
        status = EvolveRunStatus.partial.value

    async with async_session_factory() as db:
        run = await db.get(EvolveRun, run_id)
        if run:
            run.completed_at = _utcnow()
            run.status = status
            run.stats = {"repos_checked": len(repos), "competitor_data": competitor_data}
            run.error_log = "\n".join(errors) if errors else None
            run.suggestions_generated = suggestion_count
            await db.commit()
            await db.refresh(run)

    logger.info(f"[Evolve] Competitor monitor complete: {suggestion_count} suggestions, status={status}")
    return run


async def _generate_suggestions_via_llm(
    analysis_data: dict, source: str, run_id: str
) -> list[EvolveSuggestion]:
    """Use the Evolve agent's LLM to generate structured suggestions from analysis data."""
    from app.core.llm_registry import llm_registry

    prompt = f"""You are the Evolve agent for the Sutra multi-agent orchestration platform.

Analyze the following platform data and generate improvement suggestions.

DATA:
{json.dumps(analysis_data, indent=2, default=str)}

For each suggestion, output a JSON object with:
- title: short descriptive title
- description: detailed description of the improvement
- category: one of platform_health, error_pattern, performance, competitor_gap, feature_idea
- priority: low, medium, high, or critical
- action_type: forge_request (code change), task (manual work), or goal (strategic objective)
- action_config: relevant config for the action (e.g. repo_url for forge, assignee for task)

Output ONLY a JSON array of suggestions. Do NOT include any thinking, reasoning, or explanation.
If no suggestions, output an empty array [].
Be specific and actionable. Focus on real issues found in the data."""

    try:
        llm = llm_registry.get_chat_model(provider="groq", model="qwen/qwen3-32b", temperature=0.3)
        response = await llm.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)

        # Strip Qwen3 <think>...</think> blocks before parsing JSON
        import re
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()

        # Extract JSON array from the response
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if json_match:
            suggestions_data = json.loads(json_match.group())
        else:
            logger.warning(f"[Evolve] No JSON array found in LLM response: {content[:200]}")
            suggestions_data = []

    except Exception as e:
        logger.warning(f"[Evolve] LLM suggestion generation failed: {e}")
        return []

    created = []
    async with async_session_factory() as db:
        from app.models.agent import Agent
        from app.models.approval_request import ApprovalRequest

        result = await db.execute(select(Agent).where(Agent.name == "Evolve"))
        evolve_agent = result.scalars().first()
        evolve_agent_id = evolve_agent.id if evolve_agent else None

        for s in suggestions_data[:10]:  # Cap at 10 suggestions per run
            try:
                suggestion = EvolveSuggestion(
                    evolve_agent_id=evolve_agent_id,
                    category=s.get("category", "feature_idea"),
                    source=source,
                    title=s.get("title", "Untitled suggestion"),
                    description=s.get("description", ""),
                    evidence=analysis_data,
                    priority=s.get("priority", "medium"),
                    status=SuggestionStatus.pending_approval.value,
                    action_type=s.get("action_type", "task"),
                    action_config=s.get("action_config", {}),
                    run_id=run_id,
                )
                db.add(suggestion)
                await db.flush()
                await db.refresh(suggestion)

                approval = ApprovalRequest(
                    title=f"[Evolve] {suggestion.title}",
                    description=suggestion.description,
                    category="evolve",
                    risk_level="medium" if suggestion.priority in ("low", "medium") else "high",
                    context={"suggestion_id": suggestion.id},
                    action_payload={
                        "type": "evolve_action",
                        "suggestion_id": suggestion.id,
                        "action_type": suggestion.action_type,
                        "action_config": suggestion.action_config,
                    },
                    requester_agent_id=evolve_agent_id,
                )
                db.add(approval)
                await db.flush()
                await db.refresh(approval)

                suggestion.approval_request_id = approval.id
                created.append(suggestion)
            except Exception as e:
                logger.warning(f"[Evolve] Failed to create suggestion: {e}")
                continue

        await db.commit()

    return created


async def execute_evolve_action(suggestion_id: str) -> None:
    """Execute the action for an approved suggestion."""
    async with async_session_factory() as db:
        suggestion = await db.get(EvolveSuggestion, suggestion_id)
        if not suggestion:
            logger.warning(f"[Evolve] Suggestion {suggestion_id} not found")
            return

        suggestion.status = SuggestionStatus.in_progress.value
        await db.commit()

        try:
            if suggestion.action_type == "forge_request":
                from app.models.forge import ForgeRequest
                config = suggestion.action_config or {}
                forge = ForgeRequest(
                    title=suggestion.title,
                    description=suggestion.description,
                    repo_url=config.get("repo_url", ""),
                    llm_provider=config.get("llm_provider", "groq"),
                    llm_model=config.get("llm_model", "qwen/qwen3-32b"),
                )
                db.add(forge)
                await db.flush()
                await db.refresh(forge)
                suggestion.result_id = forge.id
                suggestion.result_type = "forge_request"

            elif suggestion.action_type == "task":
                from app.models.task import Task
                config = suggestion.action_config or {}
                task = Task(
                    title=suggestion.title,
                    description=suggestion.description,
                    priority=config.get("priority", "medium"),
                    assignee_agent_id=config.get("assignee_agent_id"),
                )
                db.add(task)
                await db.flush()
                await db.refresh(task)
                suggestion.result_id = task.id
                suggestion.result_type = "task"

            elif suggestion.action_type == "goal":
                from app.models.goal import AgentGoal
                config = suggestion.action_config or {}
                goal = AgentGoal(
                    agent_id=config.get("agent_id", suggestion.evolve_agent_id),
                    title=suggestion.title,
                    description=suggestion.description,
                    success_criteria=config.get("success_criteria", []),
                )
                db.add(goal)
                await db.flush()
                await db.refresh(goal)
                suggestion.result_id = goal.id
                suggestion.result_type = "goal"

            suggestion.status = SuggestionStatus.completed.value
            await db.commit()
            logger.info(f"[Evolve] Action executed for suggestion {suggestion_id}: {suggestion.action_type}")

        except Exception as e:
            suggestion.status = SuggestionStatus.approved.value  # Revert to approved on failure
            await db.commit()
            logger.error(f"[Evolve] Failed to execute action for {suggestion_id}: {e}")
            raise
