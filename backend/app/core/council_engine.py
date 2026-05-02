"""Council engine — runs a structured multi-round debate, then arbitration.

Mirrors ``discussion_engine`` but with strict per-round prompts (v3.3) and a
final non-participating arbitrator pass (v3.4).

Important: messages are NEVER truncated by this engine.  Per-round peer outputs
and the full transcript fed to the arbitrator are passed in their entirety,
regardless of context-window heuristics.  We bypass token-guard auto-trim and
set a high ``max_tokens`` ceiling per call so completions are not cut short.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.agent_manager import agent_manager
from app.core.callbacks import UsageCallbackHandler
from app.core.council_prompts import (
    build_advisor_system_prompt,
    build_arbitrator_prompt,
    build_round_instruction,
    format_full_transcript,
    format_peer_outputs,
    phase_for_round,
)
from app.core.llm_registry import llm_registry
from app.db.session import async_session_factory
from app.models.council import Council, CouncilStatus

logger = logging.getLogger(__name__)


# Generous output ceilings — provider-side caps still apply, but we never
# proactively truncate.  Advisors get 8k, the arbitrator's report can run long.
ADVISOR_MAX_TOKENS = 8192
ARBITRATOR_MAX_TOKENS = 16384


# ─── Low-level LLM invocation (no tools, no streaming) ────────────────────────

async def _invoke_agent_full(agent_id: str, messages: list, max_tokens: int) -> str:
    """Invoke an agent's underlying LLM directly (no tool binding).

    Mirrors ``discussion_engine._invoke_agent`` but lets the caller override
    ``max_tokens`` so council responses are not truncated.
    """
    agent_entry = agent_manager._running_agents.get(agent_id)
    if not agent_entry:
        return f"[Agent {agent_id} is not running]"

    agent_config = agent_entry.get("config", {})
    try:
        # Use the agent's configured max_tokens if it's larger than our floor;
        # otherwise force the council ceiling.
        configured = int(agent_config.get("max_tokens") or 0)
        effective_max_tokens = max(configured, max_tokens)

        llm = llm_registry.get_chat_model(
            provider=agent_config["llm_provider"],
            model=agent_config["llm_model"],
            temperature=agent_config.get("temperature", 0.7),
            max_tokens=effective_max_tokens,
            streaming=False,
        )
        config = {"callbacks": [UsageCallbackHandler()]}
        response = await llm.ainvoke(messages, config=config)
        content = response.content
        if isinstance(content, list):
            texts = [
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            content = "\n".join(texts)
        return str(content).strip() or "[No response]"
    except Exception as e:
        logger.error(f"Council: agent {agent_id} failed: {e}")
        return f"[Error invoking agent: {e}]"


# ─── Engine ───────────────────────────────────────────────────────────────────

class CouncilEngine:
    """Runs a council debate end-to-end, yielding SSE-compatible events."""

    async def run(self, council_id: str) -> AsyncGenerator[dict, None]:
        """Drive a council session.

        Event types:
          - meta:               {council_id, title, question, num_rounds, advisor_count}
          - round_start:        {round, phase}
          - advisor_thinking:   {agent_id, agent_name, role, round, phase}
          - advisor_message:    {agent_id, agent_name, role, content, round, phase, timestamp}
          - arbitrator_thinking:{agent_id, agent_name}
          - final_report:       {content, agent_id, agent_name}
          - done:               {}
          - error:              {message}
        """
        # ─── Load + mark active ───────────────────────────────────────────
        async with async_session_factory() as db:
            council = await db.get(Council, council_id)
            if not council:
                yield {"type": "error", "message": f"Council {council_id} not found"}
                return
            if council.status not in (
                CouncilStatus.pending.value,
                CouncilStatus.active.value,
            ):
                yield {
                    "type": "error",
                    "message": f"Council is already {council.status}",
                }
                return

            # Per the spec, /run restarts: clear prior transcript & report.
            council.status = CouncilStatus.active.value
            council.messages = []
            council.final_report = None
            council.concluded_at = None
            await db.commit()

            # Snapshot config locally so we don't hold the session open.
            advisor_ids: list[str] = list(council.advisor_agent_ids)
            arbitrator_id: str = council.arbitrator_agent_id
            num_rounds: int = council.num_rounds
            debate_mode: str = council.debate_mode
            role_assignments: dict = dict(council.role_assignments or {})
            question: str = council.question
            context: dict = dict(council.context or {})
            title: str = council.title

        # ─── Resolve agent display names ──────────────────────────────────
        agent_names: dict[str, str] = {}
        async with async_session_factory() as db:
            from app.models.agent import Agent

            for aid in [*advisor_ids, arbitrator_id]:
                agent = await db.get(Agent, aid)
                agent_names[aid] = agent.name if agent else f"Agent-{aid[:6]}"

        def role_for(agent_id: str) -> str:
            if debate_mode == "role_based":
                return role_assignments.get(agent_id) or "(unassigned role)"
            return "model-native"

        yield {
            "type": "meta",
            "council_id": council_id,
            "title": title,
            "question": question,
            "num_rounds": num_rounds,
            "advisor_count": len(advisor_ids),
            "debate_mode": debate_mode,
        }

        all_messages: list[dict] = []

        try:
            # ─── Debate rounds ────────────────────────────────────────────
            for round_num in range(1, num_rounds + 1):
                phase = phase_for_round(round_num, num_rounds)
                yield {"type": "round_start", "round": round_num, "phase": phase}

                # Each advisor takes a turn.  Round 1 has no peer context.
                # Later rounds receive ALL peer outputs from the prior round.
                for advisor_id in advisor_ids:
                    self_role = role_for(advisor_id)
                    self_name = agent_names.get(advisor_id, "Advisor")
                    peer_names = [
                        agent_names.get(aid, "Peer")
                        for aid in advisor_ids
                        if aid != advisor_id
                    ]

                    yield {
                        "type": "advisor_thinking",
                        "agent_id": advisor_id,
                        "agent_name": self_name,
                        "role": self_role,
                        "round": round_num,
                        "phase": phase,
                    }

                    # Build round-specific user instruction.  Peer outputs come
                    # from the PREVIOUS round, untruncated.
                    if round_num == 1:
                        peer_block = ""
                    else:
                        peer_block = format_peer_outputs(
                            all_messages,
                            round_num=round_num - 1,
                            exclude_agent_id=advisor_id,
                        )

                    system_prompt = build_advisor_system_prompt(
                        num_rounds=num_rounds,
                        self_name=self_name,
                        self_role=self_role,
                        peer_names=peer_names,
                        debate_mode=debate_mode,
                        question=question,
                        context=context,
                    )
                    round_instruction = build_round_instruction(
                        round_num=round_num,
                        num_rounds=num_rounds,
                        peer_outputs_block=peer_block,
                    )

                    messages = [
                        SystemMessage(content=system_prompt),
                        HumanMessage(content=round_instruction),
                    ]

                    content = await _invoke_agent_full(
                        advisor_id, messages, ADVISOR_MAX_TOKENS
                    )

                    msg_entry = {
                        "agent_id": advisor_id,
                        "agent_name": self_name,
                        "role": self_role,
                        "content": content,
                        "round": round_num,
                        "phase": phase,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    all_messages.append(msg_entry)

                    yield {"type": "advisor_message", **msg_entry}

                    # Persist incrementally so partial transcripts are
                    # retrievable if the run crashes mid-debate.
                    async with async_session_factory() as db:
                        c = await db.get(Council, council_id)
                        if c:
                            c.messages = list(all_messages)
                            await db.commit()

            # ─── Arbitrator pass ──────────────────────────────────────────
            arb_name = agent_names.get(arbitrator_id, "Arbitrator")
            yield {
                "type": "arbitrator_thinking",
                "agent_id": arbitrator_id,
                "agent_name": arb_name,
            }

            advisors_meta = [
                {
                    "name": agent_names.get(aid, f"Advisor-{aid[:6]}"),
                    "role": role_for(aid),
                }
                for aid in advisor_ids
            ]

            arbitrator_prompt = build_arbitrator_prompt(
                question=question,
                context=context,
                debate_mode=debate_mode,
                advisors=advisors_meta,
                num_rounds=num_rounds,
                transcript=format_full_transcript(all_messages),
            )

            arb_messages = [
                SystemMessage(content=arbitrator_prompt),
                HumanMessage(content="Produce the Consolidated Council Report now."),
            ]

            report = await _invoke_agent_full(
                arbitrator_id, arb_messages, ARBITRATOR_MAX_TOKENS
            )

            yield {
                "type": "final_report",
                "content": report,
                "agent_id": arbitrator_id,
                "agent_name": arb_name,
            }

            # ─── Finalize ─────────────────────────────────────────────────
            async with async_session_factory() as db:
                c = await db.get(Council, council_id)
                if c:
                    c.status = CouncilStatus.concluded.value
                    c.messages = list(all_messages)
                    c.final_report = report
                    c.concluded_at = datetime.now(timezone.utc)
                    await db.commit()

            yield {"type": "done"}

        except Exception as e:
            logger.error(f"Council {council_id} failed: {e}", exc_info=True)
            async with async_session_factory() as db:
                c = await db.get(Council, council_id)
                if c:
                    c.status = CouncilStatus.failed.value
                    c.messages = list(all_messages)
                    await db.commit()
            yield {"type": "error", "message": str(e)}


council_engine = CouncilEngine()
