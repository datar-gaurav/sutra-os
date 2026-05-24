"""Composed Agents — graph-defined agents with guardrails and evals.

This package is the new "advanced" agent kind. The legacy monolithic agent
(create_react_agent in app.agents.factory) is untouched; composed agents live
side by side with their own table, compiler, and orchestrator entrypoint.

Layout:
  schemas.py      — pydantic GraphSpec + NodeSpec discriminated union
  state.py        — AgentState TypedDict, GuardrailResult, ProbeRecord
  guardrails/     — built-in guardrail library + registry
  compiler.py     — GraphSpec -> langgraph.StateGraph
  runner.py       — invocation entrypoint used by the orchestrator
"""
