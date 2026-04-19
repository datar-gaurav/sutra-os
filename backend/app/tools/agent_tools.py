"""Tools specifically for agent-to-agent collaboration and routing."""

import logging
from langchain_core.tools import tool

from app.core.tracing import set_attrs, span

logger = logging.getLogger(__name__)

@tool
def ask_agent(agent_name: str, message: str) -> str:
    """Ask another running agent a question or delegate a task to them.
    
    Args:
        agent_name: The name of the agent to send the message to (e.g., "James", "CoderAgent").
        message: The task, question, or context to provide to the other agent.
    
    Returns:
        The text response from the requested agent.
    """
    # Import inside the function to avoid circular imports during startup
    from app.core.agent_manager import agent_manager
    from app.core.orchestrator import orchestrator
    import asyncio
    
    logger.info(f"Agent requested to ask '{agent_name}': {message[:50]}...")
    
    # 1. Find the target agent by name
    agent_id = None
    for aid in agent_manager.get_running_agents():
        entry = agent_manager._running_agents.get(aid, {})
        config = entry.get("config", {})
        if config.get("name", "").lower() == agent_name.lower():
            agent_id = aid
            break
            
    if not agent_id:
        return f"Error: Agent '{agent_name}' is not currently running. Please verify the name or start them from the dashboard."
        
    # 2. Route the message to the target agent using the orchestrator
    try:
        # Since tools in LangChain run synchronously by default (unless defined as async),
        # but the orchestrator is async, we need to run it in the event loop.
        # However, we are likely already inside an event loop (the parent agent's invocation).
        
        loop = asyncio.get_event_loop()
        if loop.is_running():
             # We are in an async context, but Langchain called this sync tool
             # The safest way is to create a task, but since we need the result blocking,
             # and we might be in a threadpool (Langchain usually runs sync tools in threads),
             # we can try asyncio.run_coroutine_threadsafe if we have a loop, or just
             # define the tool as async.
             pass
    except RuntimeError:
        pass
        
    # Let's actually define it as an async tool! See below.
    return "This sync version should not be called."
    
    
from pydantic import BaseModel, Field

class AskAgentInput(BaseModel):
    agent_name: str = Field(description="The exact name of the target agent (e.g., 'James', 'CoderAgent').")
    message: str = Field(description="The task, question, or context to provide to the other agent.")

@tool("ask_agent", args_schema=AskAgentInput)
async def ask_agent_async(agent_name: str, message: str) -> str:
    """Ask another running agent a question or delegate a task to them.
    
    Args:
        agent_name: The exact name of the target agent (e.g., "James", "CoderAgent").
        message: The task, question, or context to provide to the other agent.
    
    Returns:
        The text response from the requested agent.
    """
    from app.core.agent_manager import agent_manager
    from app.core.orchestrator import orchestrator
    
    logger.info(f"Agent requested to ask '{agent_name}': {message[:50]}...")
    
    # 1. Find the target agent by name
    agent_id = None
    for aid in agent_manager.get_running_agents():
        entry = agent_manager._running_agents.get(aid, {})
        config = entry.get("config", {})
        if config.get("name", "").lower() == agent_name.lower():
            agent_id = aid
            break
            
    if not agent_id:
        v_agents = [agent_manager._running_agents[a].get("config", {}).get("name") for a in agent_manager.get_running_agents()]
        return f"Error: Agent '{agent_name}' is not running. Available running agents: {', '.join(filter(None, v_agents))}."
        
    # 2. Route the message to the target agent
    with span(
        "ask_agent.delegate",
        child_agent=agent_name,
        child_agent_id=str(agent_id),
        prompt_len=len(message),
    ) as s:
        try:
            response = await orchestrator.route_message(
                agent_id=agent_id,
                message=message,
            )
            output = response.get("output", "Error: The agent did not return a response.")
            set_attrs(s, response_len=len(output), ok=True)
            return output
        except Exception as e:
            logger.error(f"Error during agent handoff to {agent_name}: {e}")
            set_attrs(s, ok=False, error=str(e)[:500])
            return f"Error communicating with agent '{agent_name}': {str(e)}"

class DiscussWithAgentInput(BaseModel):
    agent_name: str = Field(description="The exact name of the target agent.")
    initial_message: str = Field(description="The opening message or task to discuss.")
    max_turns: int = Field(default=3, description="Maximum back-and-forth turns (1-5). Each turn = one message from each side.")
    goal: str = Field(default="", description="What the discussion should achieve. The conversation ends early if the goal is met.")

@tool("discuss_with_agent", args_schema=DiscussWithAgentInput)
async def discuss_with_agent_async(
    agent_name: str,
    initial_message: str,
    max_turns: int = 3,
    goal: str = "",
) -> str:
    """Have a multi-turn conversation with another agent to collaboratively solve a problem.

    Unlike ask_agent (single question/answer), this tool maintains a back-and-forth dialogue
    where each agent can build on the other's responses. Use this for complex tasks that
    require negotiation, iterative refinement, or collaborative problem-solving.

    Args:
        agent_name: The exact name of the target agent.
        initial_message: The opening message or task to discuss.
        max_turns: Maximum back-and-forth turns (1-5). Each turn = one message from each side.
        goal: What the discussion should achieve. The conversation ends early if the goal is met.

    Returns:
        A formatted transcript of the entire conversation with a final summary.
    """
    from app.core.agent_manager import agent_manager
    from app.core.orchestrator import orchestrator

    max_turns = max(1, min(max_turns, 5))

    logger.info(f"Starting multi-turn discussion with '{agent_name}' ({max_turns} turns)")

    # Find the target agent
    target_id = None
    for aid in agent_manager.get_running_agents():
        entry = agent_manager._running_agents.get(aid, {})
        config = entry.get("config", {})
        if config.get("name", "").lower() == agent_name.lower():
            target_id = aid
            break

    if not target_id:
        available = [
            agent_manager._running_agents[a].get("config", {}).get("name")
            for a in agent_manager.get_running_agents()
        ]
        return f"Error: Agent '{agent_name}' is not running. Available: {', '.join(filter(None, available))}."

    transcript: list[str] = []
    # The target agent's conversation history for context continuity
    target_history: list[dict] = []
    last_response = ""

    for turn in range(max_turns):
        # Build the message for this turn
        if turn == 0:
            outgoing = initial_message
        else:
            # The calling agent's response becomes the next message to the target
            # We wrap it with context so the target knows this is a continuing conversation
            outgoing = (
                f"[Continuing our discussion — turn {turn + 1}/{max_turns}]\n\n"
                f"Your previous response was:\n{last_response}\n\n"
                f"My follow-up:\n{initial_message}"
                if turn == 1
                else f"[Turn {turn + 1}/{max_turns}]\n\n{last_response}"
            )

        # Send to target agent with conversation history
        try:
            response = await orchestrator.route_message(
                agent_id=target_id,
                message=outgoing,
                chat_history=target_history,
            )
            reply = response.get("output", "[No response]")
        except Exception as e:
            logger.error(f"Discussion turn {turn + 1} failed: {e}")
            transcript.append(f"--- Turn {turn + 1} ERROR ---\n{e}")
            break

        # Record in transcript
        transcript.append(f"--- Turn {turn + 1} ---")
        transcript.append(f"[You → {agent_name}]: {outgoing[:500]}")
        transcript.append(f"[{agent_name}]: {reply[:1000]}")

        # Update conversation history for continuity
        target_history.append({"role": "user", "content": outgoing})
        target_history.append({"role": "assistant", "content": reply})

        last_response = reply

        # Check if the goal seems met (simple heuristic: look for conclusion signals)
        if goal and any(
            signal in reply.lower()
            for signal in ["final answer", "in conclusion", "here is the result", "agreed", "consensus"]
        ):
            transcript.append(f"\n[Discussion ended early — goal appears met at turn {turn + 1}]")
            break

    # Format the full transcript
    header = f"=== Multi-turn discussion with {agent_name} ({len(transcript)} entries) ==="
    if goal:
        header += f"\nGoal: {goal}"
    return header + "\n\n" + "\n".join(transcript) + f"\n\n=== Final response from {agent_name} ===\n{last_response}"


@tool
async def control_agent_async(agent_name: str, action: str) -> str:
    """Start or stop an agent by its name.
    
    Args:
        agent_name: The exact name of the target agent (e.g., "James", "CoderAgent").
        action: The action to perform, either "start" or "stop".
        
    Returns:
        The result of the start or stop action.
    """
    if action not in ("start", "stop"):
        return f"Error: Invalid action '{action}'. Must be 'start' or 'stop'."
        
    from app.core.agent_manager import agent_manager
    from app.db.session import async_session_factory
    from app.models.agent import Agent
    from sqlalchemy import select
    
    logger.info(f"Agent requested to {action} '{agent_name}'")
    
    async with async_session_factory() as db:
        # Case-insensitive search for agent by name
        result = await db.execute(select(Agent).where(Agent.name.ilike(agent_name)))
        agent = result.scalars().first()
        
        if not agent:
            return f"Error: Could not find an agent named '{agent_name}' in the database."
            
        agent_id = agent.id
        
        if action == "start":
            config = {
                "id": agent.id,
                "name": agent.name,
                "system_prompt": agent.system_prompt,
                "llm_provider": agent.llm_provider,
                "llm_model": agent.llm_model,
                "temperature": agent.temperature,
                "max_tokens": agent.max_tokens,
                "enabled_tools": agent.enabled_tools or [],
            }
            res = await agent_manager.start_agent(config)
            
            if res["status"] == "error":
                return f"Error starting agent '{agent_name}': {res.get('error', 'Unknown error')}"
                
            agent.status = res["status"]
            agent.is_active = res["status"] == "running"
            await db.commit()
            
            return f"Successfully started agent '{agent_name}'"
            
        elif action == "stop":
            res = await agent_manager.stop_agent(agent_id)
            
            agent.status = "stopped"
            agent.is_active = False
            await db.commit()
            
            if res["status"] == "not_running":
                return f"Agent '{agent_name}' was already stopped."
                
            return f"Successfully stopped agent '{agent_name}'"
