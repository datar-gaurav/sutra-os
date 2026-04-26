"""Orchestration engine — coordinates routing and agent-to-agent delegation."""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_manager import agent_manager
from app.core.callbacks import UsageCallbackHandler
from app.core.circuit_breaker import CircuitOpenError, get_breaker
from app.core.prompt_cache import prompt_cache
from app.core.retry import RetryConfig, retry_with_backoff
from app.core.token_guard import (
    emergency_trim,
    estimate_messages_tokens,
    get_context_limit,
    trim_messages_to_fit,
)
from app.core.tracing import log_text, set_attrs, span
from app.core.watchdog import watchdog
from app.middleware.correlation import get_request_id

logger = logging.getLogger(__name__)


def _extract_text(content) -> str:
    """Normalize LangChain chunk content to a plain string.

    Some providers (e.g. Anthropic) emit content as a list of typed blocks
    rather than a bare string.  Concatenating a list to a str raises a
    TypeError, so we extract the text portions here.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content
        )
    return str(content) if content else ""


# Error patterns that should trigger automatic fallback to the next priority model
_RETRIABLE_PATTERNS = [
    "429",
    "rate limit",
    "rate_limit",
    "quota",
    "resource_exhausted",
    "too many requests",
    "model_not_found",
    "model not found",
    "model_decommissioned",
    "deprecated",
    "does not exist",
    "not available",
    "insufficient_quota",
    "billing",
    "overloaded",
    "503",
    "capacity",
]


def _is_retriable_llm_error(error: Exception) -> bool:
    """Check if an LLM error should trigger fallback to the next priority model."""
    error_str = str(error).lower()
    return any(p in error_str for p in _RETRIABLE_PATTERNS)


def _get_llm_retry() -> RetryConfig:
    """Build retry config from runtime settings."""
    from app.core.system_settings import sys_settings
    return RetryConfig(
        max_retries=sys_settings.get("llm_retry_max_retries"),
        base_delay=sys_settings.get("llm_retry_base_delay"),
        max_delay=sys_settings.get("llm_retry_max_delay"),
    )


async def _fetch_memory_context(agent_id: str, query: str, db: AsyncSession) -> str:
    """Return a formatted string of core memories + recall search results + project context."""
    try:
        from app.core.memory_service import memory_service

        # Run core memory fetch + recall search sequentially (same db session — no concurrent ops)
        core_memories = await memory_service.get_core_memories(db, agent_id)
        memories = await memory_service.search(db, query=query, agent_id=agent_id, limit=5, include_shared=True)

        sections: list[str] = []

        # Check for active project and fetch project context
        try:
            from app.core.project_memory_service import get_active_project, get_project_context
            active_project_id = await get_active_project(db, agent_id)
            if active_project_id:
                project_ctx = await get_project_context(db, active_project_id, query)
                if project_ctx:
                    sections.append(project_ctx)
        except Exception as e:
            logger.debug(f"Project context fetch failed: {e}")

        if core_memories:
            core_lines = [f"- {m.content}" for m in core_memories]
            sections.append("Core identity & knowledge:\n" + "\n".join(core_lines))
        if memories:
            recall_lines = [f"- [{m.type}] {m.content}" for m in memories]
            sections.append("Relevant memories from past interactions:\n" + "\n".join(recall_lines))

        return "\n\n".join(sections)
    except Exception as e:
        logger.debug(f"Memory fetch failed: {e}")
        return ""


async def _fetch_skill_fragments(skill_ids: list[str], db: AsyncSession) -> list[str]:
    """Fetch prompt_fragment strings for the given skill IDs."""
    try:
        from app.models.skill import Skill
        from sqlalchemy import select
        result = await db.execute(
            select(Skill.prompt_fragment).where(
                Skill.id.in_(skill_ids),
                Skill.is_active == True,  # noqa: E712
            )
        )
        return [row for row in result.scalars().all() if row]
    except Exception as e:
        logger.debug(f"Skill fragment fetch failed: {e}")
        return []


class Orchestrator:
    """Main orchestration engine that routes messages to agents and manages delegation."""

    def _guard_token_limit(self, messages: list, agent_id: str) -> tuple[list, int]:
        """Estimate token count and trim messages if they exceed the model's context window.

        Returns (trimmed_messages, estimated_input_tokens).
        """
        info = agent_manager.get_info(agent_id)
        provider = info.get("llm_provider", "") if info else ""
        model = info.get("llm_model", "") if info else ""
        max_input_tokens = get_context_limit(provider, model)

        est = estimate_messages_tokens(messages)
        if est > max_input_tokens:
            logger.warning(
                f"Request ~{est} tokens exceeds limit {max_input_tokens} "
                f"for {provider}/{model}, trimming"
            )
            messages = trim_messages_to_fit(messages, max_input_tokens)
            est = estimate_messages_tokens(messages)
        return messages, est

    async def _resolve_executor_for_request(
        self,
        agent_id: str,
        estimated_tokens: int,
        db: AsyncSession | None,
        exclude: set[tuple[str, str]] | None = None,
        purpose_override_id: str | None = None,
    ) -> tuple[Any, str | None, str | None, int]:
        """Resolve executor, optionally using smart routing for purpose-based agents.

        Returns: (executor, provider, model, refresh_interval_hours)
        For legacy agents: (pre-built executor, None, None, 24)
        For purpose-based: (new executor, provider, model, refresh_hours)
        """
        info = agent_manager.get_info(agent_id)
        purpose_id = purpose_override_id or (info.get("purpose_id") if info else None)

        if purpose_id and db:
            # Smart routing: resolve model per-request
            from app.core.llm_queue import acquire_model
            from app.core.llm_registry import llm_registry
            from app.agents.factory import build_agent

            try:
                provider, model, refresh_hours = await acquire_model(
                    purpose_id, estimated_tokens, db, exclude=exclude
                )
            except Exception as e:
                raise RuntimeError(f"Smart routing failed: {e}")

            # Build a fresh LLM + executor for this specific request
            llm = llm_registry.get_chat_model(
                provider=provider,
                model=model,
                temperature=info.get("temperature", 0.7),
                max_tokens=info.get("max_tokens", 4096),
                streaming=True,
            )
            executor = build_agent(info, llm=llm, actual_provider=provider)
            return executor, provider, model, refresh_hours

        # Legacy path: use pre-built executor
        executor = agent_manager.get_executor(agent_id)
        return executor, None, None, 24

    async def route_message(
        self,
        agent_id: str,
        message: str,
        chat_history: list[dict] | None = None,
        db: AsyncSession | None = None,
        extra_skill_ids: list[str] | None = None,
        purpose_override_id: str | None = None,
    ) -> dict[str, Any]:
        """Route a message to a specific agent and return the response."""
        info = agent_manager.get_info(agent_id)
        purpose_id = purpose_override_id or (info.get("purpose_id") if info else None)

        # For legacy agents, check executor is running
        if not purpose_id:
            executor = agent_manager.get_executor(agent_id)
            if not executor:
                return {
                    "output": f"Agent {agent_id} is not running. Please start it first.",
                    "error": True,
                }
        elif not info:
            return {
                "output": f"Agent {agent_id} is not running. Please start it first.",
                "error": True,
            }

        # Run budget check + memory fetch sequentially (same db session — no concurrent ops)
        memory_context = ""
        extra_skill_fragments: list[str] = []
        if db:
            budget_error = await self._check_daily_token_budget(agent_id, db)
            if budget_error:
                return {"output": budget_error, "error": True}
            memory_context = await _fetch_memory_context(agent_id, message, db)
            if extra_skill_ids:
                extra_skill_fragments = await _fetch_skill_fragments(extra_skill_ids, db)

        messages = self._build_messages(message, chat_history, memory_context, extra_skill_fragments)

        # Pre-request token guard
        messages, estimated_input_tokens = self._guard_token_limit(messages, agent_id)

        # Resolve executor (smart routing or legacy) with automatic fallback
        routed_provider = None
        routed_model = None
        refresh_hours = 24
        excluded_models: set[tuple[str, str]] = set()
        last_runtime_error: Exception | None = None
        max_fallback_attempts = 5

        for attempt in range(max_fallback_attempts):
            try:
                executor, routed_provider, routed_model, refresh_hours = (
                    await self._resolve_executor_for_request(
                        agent_id, estimated_input_tokens, db,
                        exclude=excluded_models or None,
                        purpose_override_id=purpose_override_id,
                    )
                )
            except RuntimeError as e:
                # If a downstream call failed earlier, surface the real cause
                # instead of the router's generic "skipped (failed at runtime)".
                if last_runtime_error is not None:
                    return {
                        "output": f"{e} — underlying error: {last_runtime_error}",
                        "error": True,
                    }
                return {"output": str(e), "error": True}

            if not executor:
                return {
                    "output": f"Agent {agent_id} is not running. Please start it first.",
                    "error": True,
                }

            cb = UsageCallbackHandler()
            config = {"callbacks": [cb], "recursion_limit": self._get_recursion_limit(agent_id)}

            # Check prompt cache for non-streaming requests
            msg_dicts = [{"role": "user" if isinstance(m, HumanMessage) else
                           "assistant" if isinstance(m, AIMessage) else "system",
                           "content": m.content} for m in messages]
            model_name = (
                f"{routed_provider}/{routed_model}" if routed_provider
                else self._get_model_name(agent_id)
            )
            if prompt_cache.should_cache(msg_dicts):
                cached = await prompt_cache.get(model_name, msg_dicts)
                if cached:
                    if db:
                        await self._save_trace(
                            db, agent_id=agent_id, input_message=message,
                            output_message=cached, latency_ms=0,
                            input_tokens=estimated_input_tokens,
                        )
                    watchdog.heartbeat(agent_id)
                    return {"output": cached, "intermediate_steps": []}

            # Get the circuit breaker for this agent's LLM provider
            from app.core.system_settings import sys_settings
            breaker = get_breaker(
                f"llm:{model_name}",
                failure_threshold=sys_settings.get("circuit_breaker_failure_threshold"),
                window_seconds=sys_settings.get("circuit_breaker_window_seconds"),
                cooldown_seconds=sys_settings.get("circuit_breaker_cooldown_seconds"),
            )

            start_ms = time.monotonic()
            try:
                async def _invoke():
                    return await executor.ainvoke({"messages": messages}, config=config)

                result = await breaker.call(retry_with_backoff, _invoke, _get_llm_retry())

                output_messages = result.get("messages", [])
                ai_content = ""
                for msg in reversed(output_messages):
                    if isinstance(msg, AIMessage) and msg.content:
                        if isinstance(msg.content, list):
                            texts = [
                                b.get("text", "")
                                for b in msg.content
                                if isinstance(b, dict) and b.get("type") == "text"
                            ]
                            ai_content = "\n".join(texts)
                        else:
                            ai_content = str(msg.content)
                        if ai_content.strip():
                            break

                latency_ms = int((time.monotonic() - start_ms) * 1000)

                # Finalize usage tracking
                if routed_provider and routed_model:
                    from app.core.llm_queue import finalize_usage
                    await finalize_usage(
                        routed_provider, routed_model,
                        estimated_input_tokens, cb.tokens_used or estimated_input_tokens,
                        refresh_hours,
                    )
                elif info:
                    # Legacy agent: record usage directly (no pre-reserve was done)
                    legacy_provider = info.get("llm_provider")
                    legacy_model = info.get("llm_model")
                    if legacy_provider and legacy_model:
                        from app.core.usage_tracker import record_usage
                        await record_usage(
                            legacy_provider, legacy_model,
                            cb.tokens_used or 0,
                        )

                if db:
                    await self._save_trace(
                        db, agent_id=agent_id, input_message=message,
                        output_message=ai_content, latency_ms=latency_ms,
                        total_tokens=cb.tokens_used or None,
                        input_tokens=estimated_input_tokens,
                    )

                # Cache the response (if appropriate)
                if prompt_cache.should_cache(msg_dicts) and ai_content:
                    await prompt_cache.set(model_name, msg_dicts, ai_content)

                # Record heartbeat for watchdog
                watchdog.heartbeat(agent_id)

                return {"output": ai_content, "intermediate_steps": []}

            except CircuitOpenError as e:
                # Circuit open — try fallback if purpose-based
                if routed_provider and routed_model:
                    logger.warning(
                        f"Circuit open for {routed_provider}/{routed_model}, "
                        f"falling back to next model (attempt {attempt + 1})"
                    )
                    excluded_models.add((routed_provider, routed_model))
                    last_runtime_error = e
                    continue

                latency_ms = int((time.monotonic() - start_ms) * 1000)
                logger.warning(f"Circuit breaker open for agent {agent_id}: {e}")
                if db:
                    await self._save_trace(
                        db, agent_id=agent_id, input_message=message,
                        latency_ms=latency_ms, had_error=True,
                        error_message=f"Service temporarily unavailable: {e}",
                    )
                return {
                    "output": "I'm temporarily unable to respond — the AI service is experiencing issues. "
                              "Please try again in a moment.",
                    "error": True,
                }
            except Exception as e:
                # Recursion limit hit — agent kept calling tools without stopping.
                from langgraph.errors import GraphRecursionError
                if isinstance(e, GraphRecursionError):
                    latency_ms = int((time.monotonic() - start_ms) * 1000)
                    logger.warning(f"Agent {agent_id} hit recursion limit after {latency_ms}ms")
                    watchdog.heartbeat(agent_id)
                    return {
                        "output": (
                            "I reached my tool-use limit before completing this task. "
                            "I may have been looping. Please try rephrasing the request or "
                            "check whether the required tools are functioning correctly."
                        ),
                        "error": False,
                    }

                error_str = str(e).lower()

                # Auto-fallback for retriable LLM errors (rate limit, model not found, etc.)
                if routed_provider and routed_model and _is_retriable_llm_error(e):
                    logger.warning(
                        f"Retriable error on {routed_provider}/{routed_model}: {e} — "
                        f"falling back to next model (attempt {attempt + 1})"
                    )
                    excluded_models.add((routed_provider, routed_model))
                    last_runtime_error = e
                    continue

                # Catch 413 / context-too-large and retry with aggressively trimmed context
                if "413" in error_str or "too large" in error_str or "context_length" in error_str:
                    logger.warning(f"Payload too large for agent {agent_id}, retrying with emergency trim")
                    try:
                        trimmed = emergency_trim(messages)
                        cb2 = UsageCallbackHandler()
                        result = await executor.ainvoke({"messages": trimmed}, config={"callbacks": [cb2]})
                        output_messages = result.get("messages", [])
                        ai_content = ""
                        for msg in reversed(output_messages):
                            if isinstance(msg, AIMessage) and msg.content:
                                ai_content = str(msg.content) if isinstance(msg.content, str) else "\n".join(
                                    b.get("text", "") for b in msg.content if isinstance(b, dict) and b.get("type") == "text"
                                )
                                if ai_content.strip():
                                    break
                        latency_ms = int((time.monotonic() - start_ms) * 1000)
                        if db:
                            await self._save_trace(
                                db, agent_id=agent_id, input_message=message,
                                output_message=ai_content, latency_ms=latency_ms,
                                total_tokens=cb2.tokens_used or None,
                                input_tokens=estimate_messages_tokens(trimmed),
                            )
                        watchdog.heartbeat(agent_id)
                        return {"output": ai_content, "intermediate_steps": []}
                    except Exception as retry_err:
                        logger.error(f"Emergency retry also failed for agent {agent_id}: {retry_err}")
                        latency_ms = int((time.monotonic() - start_ms) * 1000)
                        if db:
                            await self._save_trace(
                                db, agent_id=agent_id, input_message=message,
                                latency_ms=latency_ms, had_error=True,
                                error_message=f"Payload too large even after trimming: {retry_err}",
                            )
                        return {"output": f"Error: message too large for model context window", "error": True}

                latency_ms = int((time.monotonic() - start_ms) * 1000)
                logger.error(f"Error routing message to agent {agent_id}: {e}")
                if db:
                    await self._save_trace(
                        db, agent_id=agent_id, input_message=message,
                        latency_ms=latency_ms, had_error=True, error_message=str(e),
                    )
                return {"output": f"Error: {str(e)}", "error": True}

        # Exhausted all fallback attempts
        return {
            "output": "All available models have been exhausted after runtime errors. Please try again later.",
            "error": True,
        }

    async def stream_message(
        self,
        agent_id: str,
        message: str,
        chat_history: list[dict] | None = None,
        db: AsyncSession | None = None,
        extra_skill_ids: list[str] | None = None,
        purpose_override_id: str | None = None,
    ):
        """Stream a response from an agent, yielding chunks.

        Opens a root MLflow span for the entire chat turn so that LangChain
        autolog spans (per-LLM-call) and LangGraph node spans nest underneath
        a single trace. The actual streaming logic lives in
        ``_stream_message_impl`` to keep the span context manager scope
        readable; ``_impl`` may set additional attributes on ``root_span``.
        """
        with span(
            "orchestrator.chat_turn",
            agent_id=str(agent_id),
            request_id=get_request_id(),
            user_message_len=len(message),
        ) as root_span:
            log_text("user_message.txt", message)
            async for chunk in self._stream_message_impl(
                agent_id, message, chat_history, db, root_span,
                extra_skill_ids=extra_skill_ids,
                purpose_override_id=purpose_override_id,
            ):
                yield chunk

    async def _stream_message_impl(
        self,
        agent_id: str,
        message: str,
        chat_history: list[dict] | None = None,
        db: AsyncSession | None = None,
        root_span: Any = None,
        extra_skill_ids: list[str] | None = None,
        purpose_override_id: str | None = None,
    ):
        """Inner streaming logic. Wrapped by ``stream_message`` for tracing."""
        info = agent_manager.get_info(agent_id)
        purpose_id = purpose_override_id or (info.get("purpose_id") if info else None)

        if not purpose_id:
            executor = agent_manager.get_executor(agent_id)
            if not executor:
                yield {"type": "error", "content": f"Agent {agent_id} is not running."}
                return
        elif not info:
            yield {"type": "error", "content": f"Agent {agent_id} is not running."}
            return

        # Run budget check + memory fetch sequentially (same db session — no concurrent ops)
        memory_context = ""
        extra_skill_fragments: list[str] = []
        if db:
            budget_error = await self._check_daily_token_budget(agent_id, db)
            if budget_error:
                yield {"type": "error", "content": budget_error}
                return
            memory_context = await _fetch_memory_context(agent_id, message, db)
            if extra_skill_ids:
                extra_skill_fragments = await _fetch_skill_fragments(extra_skill_ids, db)

        messages = self._build_messages(message, chat_history, memory_context, extra_skill_fragments)

        # Pre-request token guard
        messages, estimated_input_tokens = self._guard_token_limit(messages, agent_id)

        # Resolve executor (smart routing or legacy) with automatic fallback
        routed_provider = None
        routed_model = None
        refresh_hours = 24
        excluded_models: set[tuple[str, str]] = set()
        last_runtime_error: Exception | None = None
        max_fallback_attempts = 5

        for attempt in range(max_fallback_attempts):
            try:
                executor, routed_provider, routed_model, refresh_hours = (
                    await self._resolve_executor_for_request(
                        agent_id, estimated_input_tokens, db,
                        exclude=excluded_models or None,
                        purpose_override_id=purpose_override_id,
                    )
                )
            except RuntimeError as e:
                if last_runtime_error is not None:
                    yield {
                        "type": "error",
                        "content": f"{e} — underlying error: {last_runtime_error}",
                    }
                else:
                    yield {"type": "error", "content": str(e)}
                return

            if not executor:
                yield {"type": "error", "content": f"Agent {agent_id} is not running."}
                return

            cb = UsageCallbackHandler()
            config = {"callbacks": [cb], "recursion_limit": self._get_recursion_limit(agent_id)}

            start_ms = time.monotonic()
            full_output = ""
            tool_calls: list[dict] = []
            # Track last complete AI message per LLM call as a fallback
            _last_ai_text: str = ""
            _event_gen = executor.astream_events({"messages": messages}, config=config, version="v2")
            try:
                async for event in _event_gen:
                    kind = event["event"]
                    if kind == "on_chat_model_stream":
                        content = _extract_text(event["data"]["chunk"].content)
                        if content:
                            full_output += content
                            yield {"type": "token", "content": content}
                    elif kind == "on_chat_model_end":
                        # Capture the complete assembled message as a fallback in case
                        # streaming chunks produced empty text (e.g. thinking-model blocks)
                        output_msg = event.get("data", {}).get("output")
                        if output_msg is not None:
                            _last_ai_text = _extract_text(getattr(output_msg, "content", "") or "")
                    elif kind == "on_tool_start":
                        tool_calls.append({
                            "name": event["name"],
                            "input": str(event.get("data", {}).get("input", "")),
                        })
                        # Reset fallback text when a new tool call starts
                        _last_ai_text = ""
                        yield {
                            "type": "tool_start",
                            "content": event["name"],
                            "input": str(event.get("data", {}).get("input", "")),
                        }
                    elif kind == "on_tool_end":
                        # Attach output to the last matching tool call entry
                        for tc in reversed(tool_calls):
                            if tc["name"] == event["name"] and "output" not in tc:
                                tc["output"] = str(event.get("data", {}).get("output", ""))
                                break
                        yield {
                            "type": "tool_end",
                            "content": event["name"],
                            "output": str(event.get("data", {}).get("output", "")),
                        }

                # If streaming produced nothing but the final LLM call had text, emit it now
                if not full_output and _last_ai_text:
                    full_output = _last_ai_text
                    yield {"type": "token", "content": full_output}

                latency_ms = int((time.monotonic() - start_ms) * 1000)

                # Finalize usage tracking
                if routed_provider and routed_model:
                    from app.core.llm_queue import finalize_usage
                    await finalize_usage(
                        routed_provider, routed_model,
                        estimated_input_tokens, cb.tokens_used or estimated_input_tokens,
                        refresh_hours,
                    )
                elif info:
                    # Legacy agent: record usage directly (no pre-reserve was done)
                    legacy_provider = info.get("llm_provider")
                    legacy_model = info.get("llm_model")
                    if legacy_provider and legacy_model:
                        from app.core.usage_tracker import record_usage
                        await record_usage(
                            legacy_provider, legacy_model,
                            cb.tokens_used or 0,
                        )

                if db:
                    await self._save_trace(
                        db, agent_id=agent_id, input_message=message,
                        output_message=full_output, tool_calls=tool_calls,
                        latency_ms=latency_ms, total_tokens=cb.tokens_used or None,
                        input_tokens=estimated_input_tokens,
                    )
                # MLflow trace: final response payload + summary attrs
                log_text("agent_response.txt", full_output)
                set_attrs(
                    root_span,
                    provider=routed_provider,
                    model=routed_model,
                    latency_ms=latency_ms,
                    input_tokens=estimated_input_tokens,
                    total_tokens=cb.tokens_used or None,
                    tool_calls=len(tool_calls),
                    response_len=len(full_output),
                )
                # Record heartbeat for watchdog
                watchdog.heartbeat(agent_id)
                yield {"type": "done", "content": ""}
                return  # Success — exit the fallback loop

            except CircuitOpenError as e:
                try:
                    await _event_gen.aclose()
                except Exception:
                    pass
                # Circuit open — try fallback if purpose-based
                if routed_provider and routed_model:
                    logger.warning(
                        f"Circuit open for {routed_provider}/{routed_model}, "
                        f"falling back to next model (attempt {attempt + 1})"
                    )
                    excluded_models.add((routed_provider, routed_model))
                    last_runtime_error = e
                    continue

                latency_ms = int((time.monotonic() - start_ms) * 1000)
                logger.warning(f"Circuit breaker open for agent {agent_id}: {e}")
                if db:
                    await self._save_trace(
                        db, agent_id=agent_id, input_message=message,
                        latency_ms=latency_ms, had_error=True,
                        error_message=f"Service temporarily unavailable: {e}",
                    )
                yield {
                    "type": "error",
                    "content": "AI service temporarily unavailable. Please try again in a moment.",
                }
                return

            except Exception as e:
                try:
                    await _event_gen.aclose()
                except Exception:
                    pass
                error_str = str(e).lower()

                # Auto-fallback for retriable LLM errors (rate limit, model not found, etc.)
                if routed_provider and routed_model and _is_retriable_llm_error(e):
                    logger.warning(
                        f"Retriable error on {routed_provider}/{routed_model}: {e} — "
                        f"falling back to next model (attempt {attempt + 1})"
                    )
                    excluded_models.add((routed_provider, routed_model))
                    last_runtime_error = e
                    # Reset any partial output already streamed
                    if full_output:
                        yield {"type": "fallback", "content": f"Switching to backup model..."}
                    continue

                # Catch 413 / context-too-large and retry with aggressively trimmed context
                if "413" in error_str or "too large" in error_str or "context_length" in error_str:
                    logger.warning(f"Payload too large for agent {agent_id} (stream), retrying with emergency trim")
                    try:
                        trimmed = emergency_trim(messages)
                        cb2 = UsageCallbackHandler()
                        _retry_last_ai_text = ""
                        _retry_gen = executor.astream_events(
                            {"messages": trimmed}, config={"callbacks": [cb2]}, version="v2",
                        )
                        try:
                            async for event in _retry_gen:
                                kind = event["event"]
                                if kind == "on_chat_model_stream":
                                    content = _extract_text(event["data"]["chunk"].content)
                                    if content:
                                        full_output += content
                                        yield {"type": "token", "content": content}
                                elif kind == "on_chat_model_end":
                                    output_msg = event.get("data", {}).get("output")
                                    if output_msg is not None:
                                        _retry_last_ai_text = _extract_text(getattr(output_msg, "content", "") or "")
                        except Exception:
                            try:
                                await _retry_gen.aclose()
                            except Exception:
                                pass
                            raise
                        if not full_output and _retry_last_ai_text:
                            full_output = _retry_last_ai_text
                            yield {"type": "token", "content": full_output}
                        latency_ms = int((time.monotonic() - start_ms) * 1000)
                        if db:
                            await self._save_trace(
                                db, agent_id=agent_id, input_message=message,
                                output_message=full_output, latency_ms=latency_ms,
                                total_tokens=cb2.tokens_used or None,
                                input_tokens=estimate_messages_tokens(trimmed),
                            )
                        watchdog.heartbeat(agent_id)
                        yield {"type": "done", "content": ""}
                        return
                    except Exception as retry_err:
                        logger.error(f"Emergency retry also failed for agent {agent_id}: {retry_err}")
                        if db:
                            latency_ms = int((time.monotonic() - start_ms) * 1000)
                            await self._save_trace(
                                db, agent_id=agent_id, input_message=message,
                                latency_ms=latency_ms, had_error=True,
                                error_message=f"Payload too large even after trimming: {retry_err}",
                            )
                        yield {"type": "error", "content": "Message too large for model context window"}
                        return

                latency_ms = int((time.monotonic() - start_ms) * 1000)
                logger.error(f"Error streaming from agent {agent_id}: {e}")
                if db:
                    await self._save_trace(
                        db, agent_id=agent_id, input_message=message,
                        latency_ms=latency_ms, had_error=True, error_message=str(e),
                    )
                yield {"type": "error", "content": str(e)}
                return

        # Exhausted all fallback attempts
        yield {
            "type": "error",
            "content": "All available models have been exhausted after runtime errors. Please try again later.",
        }

    def _get_model_name(self, agent_id: str) -> str:
        """Get the LLM model name for cache/breaker keys."""
        info = agent_manager.get_info(agent_id)
        if info:
            return f"{info.get('llm_provider', 'unknown')}/{info.get('llm_model', 'unknown')}"
        return "unknown"

    def _build_messages(
        self,
        message: str,
        chat_history: list[dict] | None = None,
        memory_context: str = "",
        extra_skill_fragments: list[str] | None = None,
    ):
        """Convert chat history + current message to LangChain messages."""
        import re
        messages = []

        if memory_context:
            messages.append(SystemMessage(content=memory_context))

        if extra_skill_fragments:
            fragments_text = "\n\n".join(extra_skill_fragments)
            messages.append(SystemMessage(content=f"[Active skills for this conversation]\n\n{fragments_text}"))

        # Time context injection
        now = datetime.now(timezone.utc)
        # We provide UTC and the user's requested Pacific Time
        # Since the server is likely in the same TZ or we just want to be explicit:
        import pytz
        pacific = pytz.timezone("America/Los_Angeles")
        now_pacific = datetime.now(pacific)
        
        time_hint = (
            f"Current UTC Time: {now.strftime('%Y-%m-%d %H:%M:%S')} UTC.\n"
            f"User's Local Time (Pacific): {now_pacific.strftime('%Y-%m-%d %H:%M:%S')} (America/Los_Angeles).\n"
            f"Today is {now_pacific.strftime('%A, %B %d, %Y')}."
        )
        messages.append(SystemMessage(content=time_hint))

        # @Mention Detection
        mentions = re.findall(r"@(\w+)", message)
        if mentions:
            agent_list = ", ".join(f'"{m}"' for m in mentions)
            hint = (
                f"IMPORTANT — The user has explicitly tagged the following agent(s) by name: {agent_list}. "
                "You MUST use the 'ask_agent' tool to delegate the relevant sub-task(s) to each tagged agent. "
                "Do NOT attempt to handle a tagged agent's portion of the task yourself. "
                "Extract the specific task intended for each tagged agent from the user's message, "
                "call ask_agent for each one, and incorporate their responses into your final answer."
            )
            messages.append(SystemMessage(content=hint))

        if chat_history:
            for msg in chat_history:
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    messages.append(AIMessage(content=msg["content"]))

        messages.append(HumanMessage(content=message))
        return messages

    async def _check_daily_token_budget(self, agent_id: str, db: AsyncSession) -> str | None:
        """Return an error message if the agent has exceeded its daily token budget, else None."""
        try:
            from app.models.agent import Agent
            agent = await db.get(Agent, agent_id)
            if not agent or not agent.max_tokens_per_day:
                return None

            from sqlalchemy import func, select
            from app.models.trace import ExecutionTrace

            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            result = await db.execute(
                select(func.coalesce(func.sum(ExecutionTrace.total_tokens), 0)).where(
                    ExecutionTrace.agent_id == agent_id,
                    ExecutionTrace.created_at >= today_start,
                )
            )
            used_today = result.scalar() or 0

            if used_today >= agent.max_tokens_per_day:
                return (
                    f"Daily token budget exhausted ({used_today:,}/{agent.max_tokens_per_day:,} tokens). "
                    f"This agent will resume tomorrow or when the budget is increased."
                )
            return None
        except Exception as e:
            logger.warning(f"Token budget check failed for agent {agent_id}: {e}")
            return None

    def _get_recursion_limit(self, agent_id: str) -> int:
        """Return recursion limit for the agent's LangGraph run.

        LangGraph counts all node visits (LLM call + tool execution = 2 steps per cycle).
        Default cap: 15 tool-call cycles + 1 final response = 31 steps.
        """
        try:
            info = agent_manager.get_info(agent_id)
            if info and info.get("max_tool_calls_per_run"):
                return info["max_tool_calls_per_run"] * 2 + 5
        except Exception:
            pass
        return 31  # hard default: up to ~15 tool cycles

    async def _save_trace(
        self,
        db: AsyncSession,
        *,
        agent_id: str,
        input_message: str,
        output_message: str | None = None,
        tool_calls: list[dict] | None = None,
        latency_ms: int | None = None,
        had_error: bool = False,
        error_message: str | None = None,
        total_tokens: int | None = None,
        input_tokens: int | None = None,
    ) -> None:
        """Persist an ExecutionTrace record. Silently swallows errors."""
        try:
            from app.models.trace import ExecutionTrace

            trace = ExecutionTrace(
                agent_id=agent_id,
                request_id=get_request_id() or None,
                input_message=input_message,
                output_message=output_message,
                tool_calls=json.dumps(tool_calls) if tool_calls else None,
                total_tokens=total_tokens,
                input_tokens=input_tokens,
                latency_ms=latency_ms,
                had_error=had_error,
                error_message=error_message,
                created_at=datetime.now(timezone.utc),
            )
            db.add(trace)
            await db.flush()

            # Immediate alert check for errors (fire-and-forget)
            if had_error:
                from app.core.alert_evaluator import check_trace_for_immediate_alert
                asyncio.create_task(check_trace_for_immediate_alert(agent_id, had_error))
        except Exception as exc:
            logger.warning(f"Failed to save execution trace: {exc}")


# Global singleton
orchestrator = Orchestrator()
