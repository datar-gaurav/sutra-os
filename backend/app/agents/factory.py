"""LangChain agent factory — builds an AgentShell once per agent, then a fresh
React executor per turn with whichever skills the router selected.

The split:

  - AgentShell        (built once at agent_manager.start_agent)
      LLM (with fallbacks) + base system prompt + base tool IDs + max context.
      Cheap to keep in memory; expensive parts (LLM client init, fallback
      config) happen here.

  - build_executor_for_turn(shell, loaded_skills)   (called per turn)
      Composes the per-turn system prompt (base + skill bodies), binds the
      union of base tools + skill-required tools, and wires them into a
      create_react_agent graph. Cheap — just graph wiring.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from app.core.llm_registry import llm_registry
from app.core.token_guard import get_context_limit, trim_messages_to_fit
from app.skills.loader import LoadedSkill
from app.tools.registry import get_tools_by_ids

logger = logging.getLogger(__name__)


@dataclass
class AgentShell:
    """Static parts of an agent — built once, reused for every turn.

    Skill overlays (body + tools) are applied per turn via
    build_executor_for_turn() because the router may pick different skills
    each time.
    """

    agent_id: str
    agent_config: dict[str, Any]
    base_prompt: str
    base_tool_ids: list[str]
    llm: Any | None = None              # None for purpose-only agents
    effective_provider: str = ""
    max_context: int = 4096
    is_placeholder: bool = False         # True when no static LLM (purpose-based)
    supports_tools: bool = True


@dataclass
class _PurposeOnlyPlaceholder:
    """Sentinel for purpose-based agents that have no static LLM at start.

    The orchestrator's _resolve_executor_for_request will build the real
    executor per-request via smart routing. Direct invocation is an error.
    """

    agent_config: dict[str, Any]
    shell: AgentShell | None = None

    async def ainvoke(self, *_a, **_kw):
        raise RuntimeError(
            "Purpose-only agent has no static executor; use orchestrator."
        )

    def astream_events(self, *_a, **_kw):
        raise RuntimeError(
            "Purpose-only agent has no static executor; use orchestrator."
        )


def _make_trimming_prompt(system_prompt: str, max_tokens: int):
    """Return a LangGraph prompt callable that prepends the system message and trims to fit."""
    sys_msg = SystemMessage(content=system_prompt)

    def _prompt(state) -> list:
        messages = state["messages"] if isinstance(state, dict) else state.messages
        all_msgs = [sys_msg] + list(messages)
        return trim_messages_to_fit(all_msgs, max_tokens)

    return _prompt


def _build_simple_chain(llm, system_prompt: str):
    """A no-tools chain for providers that don't support tool calling."""

    async def _run(inputs: dict) -> dict:
        messages = list(inputs.get("messages", []))
        full_messages = [SystemMessage(content=system_prompt)] + messages
        response = await llm.ainvoke(full_messages)
        return {"messages": messages + [response]}

    return RunnableLambda(_run)


def _resolve_llm(agent_config: dict[str, Any]) -> tuple[Any | None, str]:
    """Resolve primary LLM + fallbacks from config. Returns (llm_or_None, effective_provider)."""
    effective_provider = agent_config.get("llm_provider", "") or ""
    has_purpose = bool(agent_config.get("purpose_id"))

    try:
        llm = llm_registry.get_chat_model(
            provider=agent_config["llm_provider"],
            model=agent_config["llm_model"],
            temperature=agent_config.get("temperature", 0.7),
            max_tokens=agent_config.get("max_tokens", 4096),
            streaming=True,
        )
    except Exception as e:
        if not has_purpose:
            raise
        logger.info(
            f"Static provider unavailable ({e}); purpose-based agent will "
            f"resolve a model per-request."
        )
        return None, effective_provider

    fallbacks = []
    for prov_key, mod_key in (("secondary_provider", "secondary_model"),
                              ("fallback_provider", "fallback_model")):
        prov, model = agent_config.get(prov_key), agent_config.get(mod_key)
        if prov and model:
            try:
                fb = llm_registry.get_chat_model(
                    provider=prov,
                    model=model,
                    temperature=agent_config.get("temperature", 0.7),
                    max_tokens=agent_config.get("max_tokens", 4096),
                    streaming=True,
                )
                fallbacks.append(fb)
            except Exception as e:
                logger.warning(f"Failed to initialize {prov_key} LLM: {e}")
    if fallbacks:
        llm = llm.with_fallbacks(fallbacks)
    return llm, effective_provider


def build_agent_shell(agent_config: dict[str, Any]) -> AgentShell:
    """Build the static, per-agent shell — done once at start_agent."""
    agent_id = agent_config["id"]
    base_prompt = agent_config.get("system_prompt") or "You are a helpful AI assistant."
    base_tool_ids = list(agent_config.get("enabled_tools") or [])

    llm, effective_provider = _resolve_llm(agent_config)
    supports_tools = bool(effective_provider) and llm_registry.provider_supports_tools(effective_provider)
    max_context = get_context_limit(effective_provider, agent_config.get("llm_model", ""))

    return AgentShell(
        agent_id=agent_id,
        agent_config=agent_config,
        base_prompt=base_prompt,
        base_tool_ids=base_tool_ids,
        llm=llm,
        effective_provider=effective_provider,
        max_context=max_context,
        is_placeholder=(llm is None),
        supports_tools=supports_tools,
    )


def build_executor_for_turn(
    shell: AgentShell,
    loaded_skills: list[LoadedSkill] | None = None,
    llm_override: Any | None = None,
    provider_override: str | None = None,
):
    """Compose a fresh per-turn React graph with the selected skill overlay.

    Args:
        shell: The agent's cached AgentShell.
        loaded_skills: Skills the router picked for this turn (0+). Their bodies
            are appended to the system prompt; their tool IDs are union-merged
            into the agent's tool list. None or empty = no overlay.
        llm_override: For purpose-based agents, the orchestrator passes the
            per-request LLM here (resolved via smart routing).
        provider_override: Provider name for the override LLM — used to check
            tool-calling support and pick the trimming context limit.

    Returns:
        A LangGraph React agent (or a simple chain for non-tool-calling providers).
    """
    llm = llm_override or shell.llm
    if llm is None:
        # Still a placeholder — fall through to the runtime resolver
        return _PurposeOnlyPlaceholder(agent_config=shell.agent_config, shell=shell)

    provider = provider_override or shell.effective_provider
    supports_tools = (
        llm_registry.provider_supports_tools(provider) if provider else shell.supports_tools
    )

    # Compose system prompt: base + skill bodies in attachment order
    if loaded_skills:
        skill_blocks = "\n\n".join(s.body for s in loaded_skills if s.body)
        final_prompt = shell.base_prompt + ("\n\n" + skill_blocks if skill_blocks else "")
    else:
        final_prompt = shell.base_prompt

    # Tools = base ∪ skill tools ∪ ask_agent (always available for delegation)
    tool_ids: list[str] = list(shell.base_tool_ids)
    if loaded_skills:
        for s in loaded_skills:
            tool_ids.extend(s.tools)
        # If any loaded skill ships accessory files, expose read_skill_file
        if any(s.has_files for s in loaded_skills):
            tool_ids.append("read_skill_file")
    tool_ids.append("ask_agent")
    tool_ids = list(dict.fromkeys(tool_ids))

    if not supports_tools:
        return _build_simple_chain(llm, final_prompt)

    tools: list[BaseTool] = get_tools_by_ids(tool_ids, agent_id=shell.agent_id)
    max_context = (
        get_context_limit(provider, shell.agent_config.get("llm_model", "")) or shell.max_context
    )
    trimming_prompt = _make_trimming_prompt(final_prompt, max_context)

    return create_react_agent(
        model=llm,
        tools=tools if tools else [],
        prompt=trimming_prompt,
    )


# ─── Backwards-compatible thin wrapper ────────────────────────────────────────


def build_agent(agent_config: dict[str, Any], llm=None, actual_provider: str | None = None):
    """Compatibility wrapper — returns a baked executor with NO skills overlay.

    Existing callers that want a one-shot executor (no router) keep working.
    New code should call build_agent_shell + build_executor_for_turn.
    """
    if llm is not None:
        # Caller pre-resolved the LLM (orchestrator's purpose-based path).
        shell = AgentShell(
            agent_id=agent_config["id"],
            agent_config=agent_config,
            base_prompt=agent_config.get("system_prompt") or "You are a helpful AI assistant.",
            base_tool_ids=list(agent_config.get("enabled_tools") or []),
            llm=llm,
            effective_provider=actual_provider or agent_config.get("llm_provider", ""),
            max_context=get_context_limit(
                actual_provider or agent_config.get("llm_provider", ""),
                agent_config.get("llm_model", ""),
            ),
            supports_tools=(
                llm_registry.provider_supports_tools(
                    actual_provider or agent_config.get("llm_provider", "")
                )
                if (actual_provider or agent_config.get("llm_provider"))
                else True
            ),
        )
        return build_executor_for_turn(shell, loaded_skills=None)

    shell = build_agent_shell(agent_config)
    if shell.is_placeholder:
        return _PurposeOnlyPlaceholder(agent_config=agent_config, shell=shell)
    return build_executor_for_turn(shell, loaded_skills=None)
