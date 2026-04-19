"""Resume build → critic → revise loop.

Flow per job application:
  1. Resume Builder (Opus) produces v1 tailored resume + analysis.md.
  2. A Resume Critic is picked based on JD signals:
       - research/systems/reasoning JDs → Gemini critic
       - code/infra/pragmatic eng JDs   → DeepSeek critic
  3. Critic returns structured JSON feedback.
  4. Builder revises (REVISION MODE). Steps 3–4 repeat up to `review_rounds`.
  5. Loop stops early if critic returns {"status": "approved"}.

The loop reuses the Builder's tool-enabled ReAct executor (for Drive I/O)
and calls the critic via the raw LLM (no tools) — same pattern as
discussion_engine._invoke_agent.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select

from app.core.agent_manager import agent_manager
from app.core.callbacks import UsageCallbackHandler
from app.core.llm_registry import llm_registry
from app.db.session import async_session_factory
from app.models.agent import Agent
from app.models.job_application import JobApplication

logger = logging.getLogger(__name__)

BUILDER_NAME = "Resume Builder"
CRITIC_GEMINI = "Resume Critic (Gemini)"
CRITIC_DEEPSEEK = "Resume Critic (DeepSeek)"

# Heuristics: keywords pushing toward one critic or the other.
_DEEPSEEK_SIGNALS = re.compile(
    r"\b(backend|infra|devops|kubernetes|golang|rust|c\+\+|systems?|"
    r"distributed|sre|platform|compiler|embedded|firmware|kernel|"
    r"low[- ]level|performance|latency|throughput)\b",
    re.IGNORECASE,
)
_GEMINI_SIGNALS = re.compile(
    r"\b(research|scientist|ml|machine learning|nlp|llm|product|"
    r"strategy|analytics|data scientist|growth|pm\b|research engineer|"
    r"applied scientist|quant)\b",
    re.IGNORECASE,
)


def _pick_critic_name(jd: str) -> str:
    jd = jd or ""
    ds = len(_DEEPSEEK_SIGNALS.findall(jd))
    gm = len(_GEMINI_SIGNALS.findall(jd))
    if ds > gm:
        return CRITIC_DEEPSEEK
    if gm > ds:
        return CRITIC_GEMINI
    # Tie → DeepSeek (cheaper, faster) for code-heavy defaults.
    return CRITIC_DEEPSEEK


async def _get_agent_by_name(name: str) -> Agent | None:
    async with async_session_factory() as db:
        result = await db.execute(select(Agent).where(Agent.name == name))
        return result.scalar_one_or_none()


async def _ensure_running(agent: Agent) -> None:
    if agent_manager.is_running(agent.id):
        return
    await agent_manager.start_agent({
        "id": agent.id,
        "name": agent.name,
        "system_prompt": agent.system_prompt,
        "purpose_id": agent.purpose_id,
        "llm_provider": agent.llm_provider,
        "llm_model": agent.llm_model,
        "temperature": agent.temperature,
        "max_tokens": agent.max_tokens,
        "enabled_tools": agent.enabled_tools or [],
        "secondary_provider": agent.secondary_provider,
        "secondary_model": agent.secondary_model,
        "fallback_provider": agent.fallback_provider,
        "fallback_model": agent.fallback_model,
    })


async def _invoke_critic(critic: Agent, prompt: str) -> dict:
    """Call critic LLM directly (no tools) and parse JSON reply.

    If the critic has a `purpose_id`, resolve the provider/model through the
    smart router (same routing agents use at runtime — honors rate limits
    and fallback slots). Otherwise use the agent's static provider/model.
    """
    provider, model = critic.llm_provider, critic.llm_model
    if critic.purpose_id:
        try:
            from app.core.smart_router import resolve_model
            # Rough token estimate: prompt length / 4 + system prompt
            est_tokens = (len(prompt) + len(critic.system_prompt or "")) // 4
            async with async_session_factory() as db:
                provider, model = await resolve_model(
                    critic.purpose_id, est_tokens, db,
                )
            logger.info(
                f"Critic {critic.name}: routed via purpose → {provider}/{model}"
            )
        except Exception as e:
            logger.warning(
                f"Critic {critic.name}: purpose resolution failed ({e}); "
                f"falling back to static {provider}/{model}"
            )

    llm = llm_registry.get_chat_model(
        provider=provider,
        model=model,
        temperature=critic.temperature or 0.2,
        max_tokens=critic.max_tokens or 8192,
        streaming=False,
    )
    messages = [
        SystemMessage(content=critic.system_prompt),
        HumanMessage(content=prompt),
    ]
    response = await llm.ainvoke(messages, config={"callbacks": [UsageCallbackHandler()]})
    content = response.content
    if isinstance(content, list):
        content = "\n".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    text = str(content).strip()

    # Strip markdown fences if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning(f"Critic {critic.name} returned non-JSON; wrapping raw text")
        return {
            "status": "needs_revision",
            "overall_assessment": text[:2000],
            "fabrication_flags": [],
            "ai_tone_flags": [],
            "alignment_issues": [],
            "missing_keywords": [],
            "latex_issues": [],
            "priority_fixes": [],
        }


def _format_feedback_for_builder(feedback: dict, round_num: int, max_rounds: int) -> str:
    return (
        f"Reviewer feedback (round {round_num} of {max_rounds})\n"
        f"Reviewer status: {feedback.get('status', 'needs_revision')}\n\n"
        f"{json.dumps(feedback, indent=2)}\n\n"
        "Follow REVISION MODE. Decide ACCEPT / PARTIAL / REJECT per item, "
        "revise resume.md in place on Drive, and append a revision log to "
        "analysis.md. Then reply with a short round summary."
    )


def _build_initial_prompt(payload: dict) -> str:
    app_id = payload.get("application_id", "")
    return (
        f"New job opportunity received.\n\n"
        f"Job Details:\n{json.dumps(payload, indent=2)}\n\n"
        f"application_id: {app_id}\n\n"
        f"Please tailor my resume for this role following your instructions. "
        f"Use the job_title and company fields to create the folder path on "
        f"Google Drive. When done, call update_job_application with the "
        f"application_id and the resume/analysis Drive URLs and fit_score."
    )


def _build_review_prompt(jd: str, master_resume: str, draft: str, prior_rounds: list[dict]) -> str:
    prior = ""
    if prior_rounds:
        prior = "\n\nPrior review rounds (for context):\n" + json.dumps(prior_rounds, indent=2)
    return (
        "Review this tailored resume against the JD and the candidate's "
        "master resume. Return ONLY the JSON structure specified in your "
        "system prompt.\n\n"
        f"=== JOB DESCRIPTION ===\n{jd}\n\n"
        f"=== MASTER RESUME (ground truth) ===\n{master_resume}\n\n"
        f"=== TAILORED DRAFT ===\n{draft}"
        f"{prior}"
    )


_TEX_RE = re.compile(
    r"<<<RESUME_(?:MD|TEX)_BEGIN>>>(.*?)<<<RESUME_(?:MD|TEX)_END>>>", re.DOTALL
)
_MASTER_RE = re.compile(
    r"<<<MASTER_(?:MD|TEX)_BEGIN>>>(.*?)<<<MASTER_(?:MD|TEX)_END>>>", re.DOTALL
)


def _extract_tailored_tex(builder_output: str) -> str:
    m = _TEX_RE.search(builder_output or "")
    return m.group(1).strip() if m else ""


def _extract_master_tex(builder_output: str) -> str:
    m = _MASTER_RE.search(builder_output or "")
    return m.group(1).strip() if m else ""


async def run_resume_review_loop(application_id: str, payload: dict) -> dict:
    """Run the full build → review → revise loop for one application."""
    from app.core.orchestrator import orchestrator

    async with async_session_factory() as db:
        app_row = await db.get(JobApplication, application_id)
        if not app_row:
            return {"error": f"application {application_id} not found"}
        max_rounds = int(app_row.review_rounds or 0)
        company = app_row.company or "Unknown"
        role = app_row.job_title or "Untitled"
        jd = app_row.job_description or ""
        review_log: list[dict] = list(app_row.review_log or [])

    # Resolve agents
    builder = await _get_agent_by_name(BUILDER_NAME)
    if not builder:
        return {"error": f"'{BUILDER_NAME}' agent not seeded"}
    await _ensure_running(builder)

    critic = None
    if max_rounds > 0:
        critic_name = _pick_critic_name(jd)
        critic = await _get_agent_by_name(critic_name)
        if not critic:
            logger.warning(f"Critic {critic_name} not seeded — skipping review loop")
            max_rounds = 0

    # Step 1: initial build
    initial_prompt = _build_initial_prompt({**payload, "application_id": application_id})
    result = await orchestrator.route_message(
        agent_id=builder.id,
        message=initial_prompt,
        chat_history=[],
    )
    review_log.append({
        "round": 0,
        "role": "builder",
        "agent": builder.name,
        "content": result.get("output", ""),
        "ts": datetime.now(timezone.utc).isoformat(),
    })

    # Persist the initial build log
    async with async_session_factory() as db:
        row = await db.get(JobApplication, application_id)
        if row:
            row.review_log = list(review_log)
            await db.commit()

    builder_output = result.get("output", "")
    if max_rounds == 0 or not critic:
        return {"rounds": 0, "final_output": builder_output}

    master_resume = _extract_master_tex(builder_output)
    current_draft = _extract_tailored_tex(builder_output)
    if not current_draft:
        logger.warning("Builder did not include tailored tex sentinels — skipping review")
        return {"rounds": 0, "final_output": builder_output}

    # Step 2-N: critique → revise loop
    final_output = builder_output
    for round_num in range(1, max_rounds + 1):
        draft = current_draft
        if not draft:
            logger.warning("Skipping review round — no draft available")
            break

        await _ensure_running(critic)
        review_prompt = _build_review_prompt(
            jd, master_resume, draft,
            [r for r in review_log if r.get("role") == "critic"],
        )
        feedback = await _invoke_critic(critic, review_prompt)
        review_log.append({
            "round": round_num,
            "role": "critic",
            "agent": critic.name,
            "content": feedback,
            "ts": datetime.now(timezone.utc).isoformat(),
        })

        if feedback.get("status") == "approved":
            logger.info(f"Critic approved resume at round {round_num}; stopping early")
            async with async_session_factory() as db:
                row = await db.get(JobApplication, application_id)
                if row:
                    row.review_log = list(review_log)
                    await db.commit()
            break

        # Builder revises
        revision_prompt = _format_feedback_for_builder(feedback, round_num, max_rounds)
        revision_result = await orchestrator.route_message(
            agent_id=builder.id,
            message=revision_prompt,
            chat_history=[],
        )
        final_output = revision_result.get("output", "")
        revised_draft = _extract_tailored_tex(final_output)
        if revised_draft:
            current_draft = revised_draft
        review_log.append({
            "round": round_num,
            "role": "builder",
            "agent": builder.name,
            "content": final_output,
            "ts": datetime.now(timezone.utc).isoformat(),
        })

        async with async_session_factory() as db:
            row = await db.get(JobApplication, application_id)
            if row:
                row.review_log = list(review_log)
                await db.commit()

    return {"rounds": max_rounds, "final_output": final_output}
