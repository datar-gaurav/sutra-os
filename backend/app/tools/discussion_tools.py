"""LangChain tool for agents to start multi-agent discussions."""

import json
import logging

from langchain_core.tools import tool

from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


def create_discussion_tools(agent_id: str):
    """Create discussion tools bound to a specific agent as the creator."""

    @tool
    async def start_discussion(
        title: str,
        topic: str,
        participant_agent_names: str,
        discussion_type: str = "brainstorm",
        max_rounds: int = 2,
        auto_run: bool = False,
    ) -> str:
        """Start a multi-agent group discussion.

        Args:
            title: Short name for the discussion.
            topic: The question or subject to discuss.
            participant_agent_names: Comma-separated agent names to invite.
            discussion_type: One of brainstorm, debate, review, standup, retrospective.
            max_rounds: Number of rounds each agent gets to speak (1-5).
            auto_run: If True, run the discussion immediately and return the
                      summary and action items. If False (default), create the
                      discussion in pending state for the UI to trigger.

        Returns a JSON object with discussion_id and results (if auto_run).
        """
        from sqlalchemy import select
        from app.models.agent import Agent
        from app.models.discussion import Discussion, DiscussionType

        valid_types = [t.value for t in DiscussionType]
        if discussion_type not in valid_types:
            discussion_type = "brainstorm"
        max_rounds = max(1, min(5, max_rounds))

        names = [n.strip() for n in participant_agent_names.split(",") if n.strip()]
        if not names:
            return json.dumps({"error": "No participant names provided"})

        async with async_session_factory() as db:
            # Resolve names to IDs
            participant_ids = []
            not_found = []
            for name in names:
                result = await db.execute(
                    select(Agent).where(Agent.name.ilike(name))
                )
                agent = result.scalars().first()
                if agent:
                    participant_ids.append(agent.id)
                else:
                    not_found.append(name)

            if not participant_ids:
                return json.dumps({"error": f"None of the agents found: {names}"})

            discussion = Discussion(
                title=title,
                topic=topic,
                type=discussion_type,
                participant_agent_ids=participant_ids,
                max_rounds=max_rounds,
                created_by_agent_id=agent_id,
                messages=[],
            )
            db.add(discussion)
            await db.commit()
            await db.refresh(discussion)
            discussion_id = discussion.id

            logger.info(f"Agent {agent_id} started discussion {discussion_id}: {title!r}")

        # ── Auto-run: execute the discussion inline and return summary ──────
        if auto_run:
            try:
                from app.core.discussion_engine import discussion_engine

                summary = ""
                action_items = []
                async for event in discussion_engine.run(discussion_id):
                    if event.get("type") == "summary":
                        summary = event.get("summary", "")
                        action_items = event.get("action_items", [])
                    elif event.get("type") == "error":
                        return json.dumps({
                            "discussion_id": discussion_id,
                            "error": event.get("message", "Discussion failed"),
                        })

                return json.dumps({
                    "discussion_id": discussion_id,
                    "title": title,
                    "type": discussion_type,
                    "status": "concluded",
                    "participants_found": len(participant_ids),
                    "participants_not_found": not_found,
                    "summary": summary,
                    "action_items": action_items,
                    "view_url": f"/discussions/{discussion_id}",
                })
            except Exception as e:
                logger.error(f"Auto-run discussion {discussion_id} failed: {e}")
                return json.dumps({
                    "discussion_id": discussion_id,
                    "error": f"Auto-run failed: {e}",
                })

        # ── Default: return pending discussion for manual trigger ───────────
        result_data = {
            "discussion_id": discussion_id,
            "title": title,
            "type": discussion_type,
            "participants_found": len(participant_ids),
            "participants_not_found": not_found,
            "status": "pending",
            "view_url": f"/discussions/{discussion_id}",
            "note": "Discussion created. It will run when triggered via the UI or API, or set auto_run=True to execute immediately.",
        }
        return json.dumps(result_data)

    return [start_discussion]


DISCUSSION_TOOL_IDS = {"start_discussion"}
