"""LangChain agent factory — creates configured agents from database models."""

import logging
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableLambda
from langgraph.prebuilt import create_react_agent

from app.core.llm_registry import llm_registry
from app.tools.registry import get_tools_by_ids

logger = logging.getLogger(__name__)


def _build_simple_chain(llm, system_prompt: str):
    """Build a no-tools chain for providers that don't support tool calling.

    Returns a Runnable with the same interface as create_react_agent:
      ainvoke({"messages": [...]}) → {"messages": [..., AIMessage]}
      astream_events({"messages": [...]}, version="v2") → LangChain event stream
    """

    async def _run(inputs: dict) -> dict:
        messages = list(inputs.get("messages", []))
        full_messages = [SystemMessage(content=system_prompt)] + messages
        response = await llm.ainvoke(full_messages)
        return {"messages": messages + [response]}

    return RunnableLambda(_run)


def build_agent(agent_config: dict[str, Any], llm=None, actual_provider: str | None = None):
    """Build a LangChain agent graph from an agent config dict.

    Args:
        agent_config: Dict with keys: system_prompt, llm_provider, llm_model,
                      temperature, max_tokens, enabled_tools, and optionally
                      secondary/fallback provider/model.
        llm: Optional pre-resolved LLM instance (for purpose-based routing).
             If provided, skips LLM creation from agent_config.

    Returns:
        A compiled LangGraph agent (CompiledStateGraph) ready to invoke.
    """
    # Determine the effective provider so we know whether tool calling is supported
    effective_provider = actual_provider or agent_config.get("llm_provider", "")

    if llm is None:
        # Legacy path: build LLM from agent config (no purpose-based routing)
        llm = llm_registry.get_chat_model(
            provider=agent_config["llm_provider"],
            model=agent_config["llm_model"],
            temperature=agent_config.get("temperature", 0.7),
            max_tokens=agent_config.get("max_tokens", 4096),
            streaming=True,
        )

        # Configure fallbacks if present
        fallbacks = []

        sec_prov = agent_config.get("secondary_provider")
        sec_model = agent_config.get("secondary_model")
        if sec_prov and sec_model:
            try:
                sec_llm = llm_registry.get_chat_model(
                    provider=sec_prov,
                    model=sec_model,
                    temperature=agent_config.get("temperature", 0.7),
                    max_tokens=agent_config.get("max_tokens", 4096),
                    streaming=True,
                )
                fallbacks.append(sec_llm)
            except Exception as e:
                logger.warning(f"Failed to initialize secondary LLM: {e}")

        fb_prov = agent_config.get("fallback_provider")
        fb_model = agent_config.get("fallback_model")
        if fb_prov and fb_model:
            try:
                fb_llm = llm_registry.get_chat_model(
                    provider=fb_prov,
                    model=fb_model,
                    temperature=agent_config.get("temperature", 0.7),
                    max_tokens=agent_config.get("max_tokens", 4096),
                    streaming=True,
                )
                fallbacks.append(fb_llm)
            except Exception as e:
                logger.warning(f"Failed to initialize fallback LLM: {e}")

        if fallbacks:
            logger.info(f"Applying {len(fallbacks)} fallbacks to primary LLM.")
            llm = llm.with_fallbacks(fallbacks)

    # 3. Compose system prompt — append active skill fragments in priority order
    base_prompt = agent_config.get("system_prompt") or "You are a helpful AI assistant."
    skill_fragments = agent_config.get("skill_fragments") or []
    if skill_fragments:
        interpolated = []
        for fragment in skill_fragments:
            try:
                overrides = agent_config.get("skill_config_overrides", {})
                interpolated.append(fragment.format_map(overrides))
            except (KeyError, ValueError):
                interpolated.append(fragment)
        final_prompt = base_prompt + "\n\n" + "\n\n".join(interpolated)
    else:
        final_prompt = base_prompt

    # If the provider doesn't support tool calling, use a simple chain that skips bind_tools
    if not llm_registry.provider_supports_tools(effective_provider):
        logger.info(
            f"Provider '{effective_provider}' does not support tool calling — "
            "building simple chain without tools."
        )
        return _build_simple_chain(llm, final_prompt)

    # 2. Get enabled tools — merge base tools with any skill-required tools
    base_tool_ids = agent_config.get("enabled_tools") or []
    skill_tool_ids = agent_config.get("skill_tool_ids") or []

    # Always include ask_agent for @mention delegation
    all_tool_ids = list(dict.fromkeys(base_tool_ids + skill_tool_ids + ["ask_agent"]))
    tools = get_tools_by_ids(all_tool_ids, agent_id=agent_config.get("id"))

    # 4. Create the agent using LangGraph
    agent = create_react_agent(
        model=llm,
        tools=tools if tools else [],
        prompt=final_prompt,
    )

    logger.info(
        f"Built agent with provider={agent_config.get('llm_provider', 'smart-router')}, "
        f"model={agent_config.get('llm_model', 'dynamic')}, tools={len(tools)}, "
        f"skills={len(skill_fragments)}"
    )

    return agent
