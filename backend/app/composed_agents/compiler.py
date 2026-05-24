"""Compile a GraphSpec into a runnable langgraph.StateGraph.

The compiler walks the GraphSpec, attaches an async executor per node, and
wires edges (including conditional ones based on state["branch"]). Guardrails
are not graph nodes themselves — they run inside the executor for the node
they're attached to (input rail on the InputNode, output rail on the
OutputNode, pre/post on LLMNodes).

Compiled graphs are cached by (composed_agent_id, version) in the runner.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

# Guardrails package — imports register all built-ins as a side effect.
from app.composed_agents import guardrails as guardrails_pkg
from app.composed_agents.schemas import (
    EdgeSpec,
    GraphSpec,
    GuardrailAttachment,
    InputNode,
    LLMNode,
    NodeSpec,
    OutputNode,
)
from app.composed_agents.state import AgentState, GuardrailResult
from app.core.llm_registry import llm_registry

logger = logging.getLogger(__name__)


# ─── Guardrail chain runner ──────────────────────────────────────────────────


async def _run_guardrails(
    attachments: list[GuardrailAttachment],
    state: AgentState,
    default_stage: str,
) -> tuple[list[GuardrailResult], AgentState, GuardrailResult | None]:
    """Run a guardrail chain in order. Returns (results, possibly_mutated_state, fatal).

    Stops at the first guardrail that returns action="reject" — that one is
    the `fatal` return value and the caller short-circuits to the END node.
    """
    results: list[GuardrailResult] = []
    cur_state = state

    for att in attachments:
        try:
            g = guardrails_pkg.get(att.type)
        except KeyError as e:
            logger.warning("Unknown guardrail '%s' in attachment '%s': %s", att.type, att.id, e)
            continue

        try:
            res = await g.check(cur_state, att.config or {})
        except Exception as e:
            logger.exception("guardrail %s crashed", att.id)
            res = GuardrailResult(
                guardrail_id=att.id,
                stage=default_stage,  # type: ignore[arg-type]
                passed=True,  # fail-open on crash; surfaced in trace
                action="warn",
                reason=f"Guardrail crashed: {e}",
            )

        # Re-tag to the attachment id so the trace points at the user-configured
        # instance, not the built-in type. (Helpful when multiple instances of
        # the same type are attached.)
        res.guardrail_id = att.id
        res.stage = default_stage  # type: ignore[assignment]

        results.append(res)

        # Apply mutation (e.g. PII redactor in redact mode).
        if res.action == "mutate" and res.mutated_text is not None:
            cur_state = _replace_head_text(cur_state, res.mutated_text)

        if res.action == "reject" and not res.passed:
            return results, cur_state, res

    return results, cur_state, None


def _replace_head_text(state: AgentState, new_text: str) -> AgentState:
    """Return a new state with the LAST message's content replaced.

    Uses LangGraph's add_messages-aware shape: emit a message with the same
    id as the head so the reducer overwrites it instead of appending.
    """
    messages = state.get("messages") or []
    if not messages:
        return state
    head = messages[-1]
    cls = type(head)
    # Preserve message id if present so add_messages dedupes.
    kwargs = {"content": new_text}
    msg_id = getattr(head, "id", None)
    if msg_id:
        kwargs["id"] = msg_id
    replacement = cls(**kwargs)
    new_messages = list(messages[:-1]) + [replacement]
    return {**state, "messages": new_messages}


# ─── Node executors ──────────────────────────────────────────────────────────


def _make_input_executor(node: InputNode):
    """Runs the input-rail guardrails on entry."""
    async def _run(state: AgentState) -> dict[str, Any]:
        results, mutated, fatal = await _run_guardrails(node.guardrails, state, "input")
        updates: dict[str, Any] = {
            "guardrail_results": (state.get("guardrail_results") or []) + results,
        }
        if mutated is not state:
            updates["messages"] = mutated["messages"]
        if fatal is not None:
            updates["rejection_message"] = (
                f"Request blocked by guardrail '{fatal.guardrail_id}': {fatal.reason}"
            )
        return updates

    return _run


def _make_llm_executor(node: LLMNode):
    """One scoped LLM call. Pre-guardrails run before, post-guardrails after."""
    async def _run(state: AgentState) -> dict[str, Any]:
        # Skip everything if a prior node already set a rejection.
        if state.get("rejection_message"):
            return {}

        accumulated_results: list[GuardrailResult] = []

        # Pre-guardrails — scoped to this node.
        pre_results, state_after_pre, fatal = await _run_guardrails(
            node.pre_guardrails, state, "input"
        )
        accumulated_results.extend(pre_results)
        if fatal is not None:
            return {
                "guardrail_results": (state.get("guardrail_results") or []) + accumulated_results,
                "rejection_message": (
                    f"Blocked by node '{node.id}' guardrail '{fatal.guardrail_id}': {fatal.reason}"
                ),
                "messages": state_after_pre["messages"],
            }

        # Resolve LLM. Provider/model on the node win; otherwise fall back to a
        # sensible default. The orchestrator may pass overrides via state in a
        # future iteration.
        provider = node.llm_provider or "openai"
        model = node.llm_model or "gpt-4o-mini"

        t0 = time.monotonic()
        try:
            llm = llm_registry.get_chat_model(
                provider=provider,
                model=model,
                temperature=node.temperature,
                max_tokens=node.max_tokens,
                streaming=False,
            )
            sys_msg = SystemMessage(content=node.system_prompt or "")
            history = list(state_after_pre.get("messages") or [])
            response = await llm.ainvoke([sys_msg, *history])
        except Exception as e:
            logger.exception("LLM node %s failed", node.id)
            err = AIMessage(content=f"[LLM error in node '{node.id}': {e}]")
            return {
                "messages": [err],
                "guardrail_results": (state.get("guardrail_results") or []) + accumulated_results,
                "rejection_message": f"LLM call failed in node '{node.id}': {e}",
            }
        llm_latency_ms = int((time.monotonic() - t0) * 1000)

        # Append assistant response so post-guardrails inspect it.
        appended_state: AgentState = {
            **state_after_pre,
            "messages": list(state_after_pre.get("messages") or []) + [response],
        }

        # Post-guardrails — same chain semantics, but stage="output".
        post_results, state_after_post, post_fatal = await _run_guardrails(
            node.post_guardrails, appended_state, "output"
        )
        accumulated_results.extend(post_results)

        updates: dict[str, Any] = {
            "messages": [response] if state_after_post is appended_state else (
                # mutation rewrote the response — emit replacement with same id
                state_after_post["messages"][-1:]
            ),
            "guardrail_results": (state.get("guardrail_results") or []) + accumulated_results,
            "scratchpad": {
                **(state.get("scratchpad") or {}),
                f"{node.id}.latency_ms": llm_latency_ms,
            },
        }
        if post_fatal is not None:
            updates["rejection_message"] = (
                f"Response blocked by node '{node.id}' guardrail "
                f"'{post_fatal.guardrail_id}': {post_fatal.reason}"
            )
        return updates

    return _run


def _make_output_executor(node: OutputNode):
    """Final stop. Runs output-rail guardrails on the assistant message."""
    async def _run(state: AgentState) -> dict[str, Any]:
        if state.get("rejection_message"):
            # If we got here despite a prior rejection, emit a clean refusal
            # message as the final assistant output.
            refusal = AIMessage(content=state["rejection_message"])
            return {"messages": [refusal]}

        results, mutated, fatal = await _run_guardrails(node.guardrails, state, "output")
        updates: dict[str, Any] = {
            "guardrail_results": (state.get("guardrail_results") or []) + results,
        }
        if fatal is not None:
            refusal = AIMessage(
                content=(
                    f"Response blocked by guardrail '{fatal.guardrail_id}': {fatal.reason}"
                )
            )
            updates["messages"] = [refusal]
            updates["rejection_message"] = fatal.reason
        elif mutated is not state:
            # A redact-style mutation rewrote the response — surface that.
            updates["messages"] = mutated["messages"][-1:]
        return updates

    return _run


# ─── Top-level compile ───────────────────────────────────────────────────────


def compile_graph(spec_dict: dict[str, Any]) -> Any:
    """Validate the spec, build a StateGraph, and return the compiled graph.

    Raises pydantic.ValidationError on a malformed spec.
    """
    spec = GraphSpec.model_validate(spec_dict)

    g = StateGraph(AgentState)

    # Add nodes.
    for node in spec.nodes:
        executor = _executor_for(node)
        g.add_node(node.id, executor)

    # Find the output node id so unconditional edges from terminal nodes go to END.
    output_id = next(n.id for n in spec.nodes if n.kind == "output")

    # Set entry.
    g.set_entry_point(spec.entry)

    # Group edges by source so we can detect routers (multiple outgoing with
    # conditions). Phase 1: no router nodes shipped — every node has at most
    # one outgoing edge — but the conditional path is wired so adding a
    # RouterNode later only needs a new executor.
    by_source: dict[str, list[EdgeSpec]] = {}
    for e in spec.edges:
        by_source.setdefault(e.source, []).append(e)

    for source_id, edges in by_source.items():
        if len(edges) == 1 and edges[0].condition is None:
            target = edges[0].target
            g.add_edge(source_id, target)
        else:
            # Conditional fan-out keyed by state["branch"].
            mapping = {e.condition: e.target for e in edges if e.condition is not None}
            default_target = next(
                (e.target for e in edges if e.condition is None), output_id
            )

            def _selector(state: AgentState, _mapping=mapping, _default=default_target):
                if state.get("rejection_message"):
                    return _default
                branch = state.get("branch")
                return _mapping.get(branch, _default)

            g.add_conditional_edges(source_id, _selector)

    # The output node always terminates the graph.
    g.add_edge(output_id, END)

    return g.compile()


def _executor_for(node: NodeSpec):
    if isinstance(node, InputNode):
        return _make_input_executor(node)
    if isinstance(node, LLMNode):
        return _make_llm_executor(node)
    if isinstance(node, OutputNode):
        return _make_output_executor(node)
    raise ValueError(f"No executor for node kind '{node.kind}'")
