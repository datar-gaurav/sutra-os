"""Discussion engine — orchestrates multi-agent structured discussions."""

import json
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.agent_manager import agent_manager
from app.core.callbacks import UsageCallbackHandler
from app.core.llm_registry import llm_registry
from app.db.session import async_session_factory
from app.models.discussion import Discussion, DiscussionStatus

logger = logging.getLogger(__name__)


# ─── Discussion Type Prompts ──────────────────────────────────────────────────

_TYPE_PROMPTS: dict[str, dict] = {
    "brainstorm": {
        "intro": (
            "You are participating in a BRAINSTORMING session. Your goal is to generate creative, "
            "diverse ideas about the topic. Build on others' ideas, think laterally, and avoid "
            "criticism. Every contribution is welcome."
        ),
        "round_instruction": "Share your best ideas and build on what others have said.",
        "moderator_intro": (
            "You are the MODERATOR of this brainstorming session. After each round, synthesize "
            "the ideas, identify themes, and encourage deeper exploration."
        ),
    },
    "debate": {
        "intro": (
            "You are participating in a structured DEBATE. Argue your position clearly with "
            "evidence and reasoning. Challenge others' claims respectfully and strengthen your "
            "argument when challenged."
        ),
        "round_instruction": "Present your strongest arguments and counter any points raised.",
        "moderator_intro": (
            "You are the MODERATOR of this debate. Keep the discussion structured, ensure each "
            "side gets equal time, and summarize key points of contention."
        ),
    },
    "review": {
        "intro": (
            "You are participating in a REVIEW session. Provide constructive, specific feedback "
            "on the topic. Be objective, cite concrete examples, and suggest improvements."
        ),
        "round_instruction": "Give your honest assessment and specific feedback.",
        "moderator_intro": (
            "You are the MODERATOR of this review. Guide the reviewers to be constructive, "
            "ensure all aspects are covered, and synthesize feedback themes."
        ),
    },
    "standup": {
        "intro": (
            "You are participating in a STANDUP meeting. Briefly report: (1) what you completed "
            "recently, (2) what you are working on next, (3) any blockers or dependencies. "
            "Be concise — 3-5 sentences."
        ),
        "round_instruction": "Give your standup update: done, doing, blockers.",
        "moderator_intro": (
            "You are the MODERATOR of this standup. After all agents report, summarize key "
            "blockers and coordination points needing attention."
        ),
    },
    "retrospective": {
        "intro": (
            "You are participating in a RETROSPECTIVE. Reflect honestly on recent work: "
            "(1) what went well, (2) what could improve, (3) one concrete action item. "
            "Be candid and constructive."
        ),
        "round_instruction": "Share your retrospective reflections: went well, improve, action.",
        "moderator_intro": (
            "You are the MODERATOR of this retrospective. Synthesize insights, identify "
            "patterns, and help the group commit to concrete improvements."
        ),
    },
}


def _build_discussion_context(
    discussion: Discussion,
    agent_id: str,
    is_moderator: bool,
    current_round: int,
    memory_context: str | None = None,
) -> list:
    """Build LangChain messages list for an agent's turn in a discussion."""
    disc_type = discussion.type
    prompts = _TYPE_PROMPTS.get(disc_type, _TYPE_PROMPTS["brainstorm"])

    role_intro = prompts["moderator_intro"] if is_moderator else prompts["intro"]
    round_instr = prompts["round_instruction"]

    system = (
        f"{role_intro}\n\n"
        f"Discussion topic: {discussion.topic}\n"
        f"Discussion type: {disc_type.upper()}\n"
        f"Round: {current_round} of {discussion.max_rounds}"
    )

    # Inject pre-fetched memories so the agent can draw on personal context
    if memory_context:
        system += (
            f"\n\nRELEVANT MEMORIES (from your long-term memory):\n{memory_context}\n"
            "Use the above memories to inform your contribution where relevant."
        )

    messages = [SystemMessage(content=system)]

    # Add prior messages as context
    for msg in discussion.messages:
        speaker = msg.get("agent_name", "Agent")
        content = msg.get("content", "")
        messages.append(HumanMessage(content=f"[{speaker}]: {content}"))

    # Prompt for this agent's turn
    messages.append(HumanMessage(content=f"Your turn — {round_instr}"))
    return messages


async def _prefetch_agent_memories(agent_id: str, topic: str) -> str | None:
    """Pre-fetch an agent's relevant memories for the discussion topic.

    Returns a formatted string of memory snippets, or None if the agent has
    no memory tool enabled or no relevant memories exist.
    """
    # Only prefetch if the agent has memory tools enabled
    agent_entry = agent_manager._running_agents.get(agent_id)
    if not agent_entry:
        return None
    enabled_tools = agent_entry.get("config", {}).get("enabled_tools", [])
    if "search_memory" not in enabled_tools and "save_memory" not in enabled_tools:
        return None

    try:
        from app.core.memory_service import memory_service
        async with async_session_factory() as db:
            memories = await memory_service.search(
                db=db,
                query=topic,
                agent_id=agent_id,
                limit=5,
                include_shared=True,
            )
        if not memories:
            return None
        lines = [f"- [{m.type}] {m.content}" for m in memories]
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Memory pre-fetch failed for agent {agent_id}: {e}")
        return None


async def _invoke_agent(agent_id: str, messages: list) -> str:
    """Invoke an agent directly via its LLM (no tools) for a discussion turn.

    Calling the full ReAct executor would allow the agent to emit tool
    calls (e.g. search_memory) which many providers reject with a 400 when
    the function-call syntax doesn't match expectations.  Discussions are
    conversational turns — plain-text responses only.
    """
    # Try to get the raw LLM from the agent's stored config so we can call
    # it without any tools bound.
    agent_entry = agent_manager._running_agents.get(agent_id)
    if not agent_entry:
        return f"[Agent {agent_id} is not running]"

    agent_config = agent_entry.get("config", {})
    try:
        llm = llm_registry.get_chat_model(
            provider=agent_config["llm_provider"],
            model=agent_config["llm_model"],
            temperature=agent_config.get("temperature", 0.7),
            max_tokens=agent_config.get("max_tokens", 4096),
            streaming=False,  # SSE is handled at the discussion level
        )
        config = {"callbacks": [UsageCallbackHandler()]}
        response = await llm.ainvoke(messages, config=config)
        content = response.content
        if isinstance(content, list):
            texts = [b.get("text", "") for b in content
                     if isinstance(b, dict) and b.get("type") == "text"]
            content = "\n".join(texts)
        return str(content).strip() or "[No response]"
    except Exception as e:
        logger.error(f"Agent {agent_id} failed in discussion: {e}")
        return f"[Error: {e}]"


async def _generate_summary(discussion: Discussion, moderator_agent_id: str | None) -> tuple[str, list[str]]:
    """Generate a summary and action items for a concluded discussion."""
    transcript = "\n".join(
        f"[Round {m.get('round', '?')}] {m.get('agent_name', 'Agent')}: {m.get('content', '')}"
        for m in discussion.messages
    )

    summary_prompt = (
        f"You are summarizing a {discussion.type} discussion titled '{discussion.title}'.\n\n"
        f"Topic: {discussion.topic}\n\n"
        f"Full transcript:\n{transcript}\n\n"
        "Please provide:\n"
        "1. A concise summary (2-3 paragraphs) of the key points and outcomes\n"
        "2. A bullet list of concrete action items that emerged (prefix each with '- ACTION:')\n\n"
        "Format your response as:\nSUMMARY:\n<summary text>\n\nACTION ITEMS:\n<bullet list>"
    )

    messages = [HumanMessage(content=summary_prompt)]

    # Use moderator if available, else first participant
    agent_id = moderator_agent_id or (discussion.participant_agent_ids[0] if discussion.participant_agent_ids else None)

    if agent_id:
        raw = await _invoke_agent(agent_id, messages)
    else:
        raw = "Discussion concluded without summary (no agents available)."

    # Parse summary and action items
    summary = raw
    action_items = []
    if "ACTION ITEMS:" in raw:
        parts = raw.split("ACTION ITEMS:", 1)
        summary = parts[0].replace("SUMMARY:", "").strip()
        for line in parts[1].strip().splitlines():
            line = line.strip()
            if line.startswith("- ACTION:"):
                action_items.append(line[9:].strip())
            elif line.startswith("-") and line:
                action_items.append(line[1:].strip())
    elif "SUMMARY:" in raw:
        summary = raw.replace("SUMMARY:", "").strip()

    return summary, action_items


class DiscussionEngine:
    """Runs multi-agent discussions turn by turn, streaming events."""

    async def run(
        self,
        discussion_id: str,
    ) -> AsyncGenerator[dict, None]:
        """
        Run a discussion and yield SSE-compatible event dicts.

        Event types:
          - meta: {discussion_id, title, topic, type, participant_count}
          - round_start: {round}
          - agent_thinking: {agent_id, agent_name, round}
          - agent_message: {agent_id, agent_name, content, round}
          - moderator_message: {agent_id, agent_name, content, round}
          - summary: {summary, action_items}
          - done: {}
          - error: {message}
        """
        async with async_session_factory() as db:
            discussion = await db.get(Discussion, discussion_id)
            if not discussion:
                yield {"type": "error", "message": f"Discussion {discussion_id} not found"}
                return

            if discussion.status not in (DiscussionStatus.pending.value, DiscussionStatus.active.value):
                yield {"type": "error", "message": f"Discussion is already {discussion.status}"}
                return

            # Mark active
            discussion.status = DiscussionStatus.active.value
            await db.commit()

        yield {
            "type": "meta",
            "discussion_id": discussion_id,
            "title": discussion.title,
            "topic": discussion.topic,
            "discussion_type": discussion.type,
            "participant_count": len(discussion.participant_agent_ids),
            "max_rounds": discussion.max_rounds,
        }

        # Resolve agent names
        async with async_session_factory() as db:
            from app.models.agent import Agent
            agent_names: dict[str, str] = {}
            for aid in discussion.participant_agent_ids:
                agent = await db.get(Agent, aid)
                agent_names[aid] = agent.name if agent else f"Agent-{aid[:6]}"
            if discussion.moderator_agent_id:
                mod = await db.get(Agent, discussion.moderator_agent_id)
                agent_names[discussion.moderator_agent_id] = (
                    mod.name if mod else f"Moderator-{discussion.moderator_agent_id[:6]}"
                )

        all_messages: list[dict] = list(discussion.messages or [])

        try:
            for round_num in range(1, discussion.max_rounds + 1):
                yield {"type": "round_start", "round": round_num}

                # Each participant takes a turn
                for agent_id in discussion.participant_agent_ids:
                    agent_name = agent_names.get(agent_id, "Agent")
                    yield {"type": "agent_thinking", "agent_id": agent_id, "agent_name": agent_name, "round": round_num}

                    # Build context with all messages so far
                    tmp_discussion = Discussion(
                        id=discussion.id,
                        title=discussion.title,
                        topic=discussion.topic,
                        type=discussion.type,
                        status=discussion.status,
                        participant_agent_ids=discussion.participant_agent_ids,
                        moderator_agent_id=discussion.moderator_agent_id,
                        messages=all_messages,
                        max_rounds=discussion.max_rounds,
                    )

                    # Pre-fetch memories relevant to the discussion topic
                    memory_ctx = await _prefetch_agent_memories(agent_id, discussion.topic)

                    messages = _build_discussion_context(
                        tmp_discussion, agent_id,
                        is_moderator=False,
                        current_round=round_num,
                        memory_context=memory_ctx,
                    )
                    content = await _invoke_agent(agent_id, messages)

                    msg_entry = {
                        "agent_id": agent_id,
                        "agent_name": agent_name,
                        "content": content,
                        "round": round_num,
                        "is_moderator": False,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    all_messages.append(msg_entry)

                    yield {"type": "agent_message", **msg_entry}

                    # Persist incrementally
                    async with async_session_factory() as db:
                        disc = await db.get(Discussion, discussion_id)
                        if disc:
                            disc.messages = list(all_messages)
                            await db.commit()

                # Moderator synthesizes after each round (if present)
                if discussion.moderator_agent_id and round_num < discussion.max_rounds:
                    mod_id = discussion.moderator_agent_id
                    mod_name = agent_names.get(mod_id, "Moderator")
                    yield {"type": "agent_thinking", "agent_id": mod_id, "agent_name": mod_name, "round": round_num}

                    tmp_discussion.messages = all_messages
                    mod_memory_ctx = await _prefetch_agent_memories(mod_id, discussion.topic)
                    messages = _build_discussion_context(
                        tmp_discussion, mod_id,
                        is_moderator=True,
                        current_round=round_num,
                        memory_context=mod_memory_ctx,
                    )
                    content = await _invoke_agent(mod_id, messages)

                    msg_entry = {
                        "agent_id": mod_id,
                        "agent_name": mod_name,
                        "content": content,
                        "round": round_num,
                        "is_moderator": True,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    all_messages.append(msg_entry)
                    yield {"type": "moderator_message", **msg_entry}

                    async with async_session_factory() as db:
                        disc = await db.get(Discussion, discussion_id)
                        if disc:
                            disc.messages = list(all_messages)
                            await db.commit()

            # Generate summary
            yield {"type": "agent_thinking", "agent_id": "system", "agent_name": "System", "round": 0}
            discussion.messages = all_messages
            summary, action_items = await _generate_summary(discussion, discussion.moderator_agent_id)
            yield {"type": "summary", "summary": summary, "action_items": action_items}

            # Finalize discussion
            async with async_session_factory() as db:
                disc = await db.get(Discussion, discussion_id)
                if disc:
                    disc.status = DiscussionStatus.concluded.value
                    disc.messages = all_messages
                    disc.summary = summary
                    disc.action_items = action_items
                    disc.concluded_at = datetime.now(timezone.utc)
                    await db.commit()

            yield {"type": "done"}

        except Exception as e:
            logger.error(f"Discussion {discussion_id} failed: {e}")
            async with async_session_factory() as db:
                disc = await db.get(Discussion, discussion_id)
                if disc:
                    disc.status = DiscussionStatus.failed.value
                    disc.messages = all_messages
                    await db.commit()
            yield {"type": "error", "message": str(e)}


discussion_engine = DiscussionEngine()
