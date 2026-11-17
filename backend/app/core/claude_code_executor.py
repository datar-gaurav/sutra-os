"""Claude Code executor — runs a chat turn on the user's Claude subscription.

A purpose slot with provider ``claude_code`` routes the whole turn here instead
of to a LangChain chat model. Claude Code is an agent, not a model: it runs its
own tool loop (files, shell, skills), so it cannot sit inside LangGraph's ReAct
graph. This class mimics the two methods the orchestrator calls on an executor
(``ainvoke`` and ``astream_events``) so routing, fallback, circuit breakers,
traces and usage tracking all keep working unchanged.

Each turn is sent to the host Fleet worker (``POST {fleet_worker_url}/exec/claude``),
which runs the ``claude`` CLI logged in with the user's subscription. The CLI's
login never leaves the host. The worker streams Claude Code's stream-json
events back as NDJSON; we translate them into LangChain-style stream events.

Each call is stateless: the agent's system prompt, memory context and recent
chat history are rendered into the prompt every turn. Files persist between
turns because each agent gets its own working folder on the host.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage

from app.config import settings

logger = logging.getLogger(__name__)

PROVIDER = "claude_code"

# Aliases the CLI accepts; full model ids (claude-sonnet-…) also work.
CLAUDE_CODE_MODELS = ["sonnet", "opus", "haiku", "opusplan"]

_USAGE_LIMIT_RE = re.compile(r"usage limit|limit reached|hit your limit|rate.?limit|out of (extra )?usage", re.I)


class ClaudeCodeError(RuntimeError):
    """A Claude Code turn failed. The message is phrased so the orchestrator's
    retriable-error check (``rate limit`` / ``not available`` / ``capacity``)
    sends the turn to the next purpose slot when that makes sense."""


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content
        ).strip()
    return str(content or "")


def render_prompt(messages: list[BaseMessage]) -> tuple[str, str]:
    """Split orchestrator messages into (extra system context, user prompt).

    System messages (memory, time, mention hints) become appended system
    context. Earlier turns are rendered as a transcript ahead of the latest
    user message so Claude Code sees the conversation.
    """
    system_parts: list[str] = []
    history: list[str] = []
    last_user = ""
    convo = [m for m in messages if not isinstance(m, SystemMessage)]
    for m in messages:
        if isinstance(m, SystemMessage):
            text = _text_of(m.content).strip()
            if text:
                system_parts.append(text)
    if convo and isinstance(convo[-1], HumanMessage):
        last_user = _text_of(convo[-1].content)
        convo = convo[:-1]
    for m in convo:
        role = "User" if isinstance(m, HumanMessage) else "Assistant"
        text = _text_of(m.content).strip()
        if text:
            history.append(f"{role}: {text}")

    if history:
        prompt = (
            "<conversation_so_far>\n" + "\n\n".join(history) + "\n</conversation_so_far>\n\n"
            "Latest message from the user:\n" + last_user
        )
    else:
        prompt = last_user
    return "\n\n".join(system_parts), prompt


def _split_tools(raw: str) -> list[str]:
    """Split a comma list of tool rules, keeping commas inside parentheses."""
    out, depth, cur = [], 0, ""
    for ch in raw:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            if cur.strip():
                out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def _workdir_key(agent_id: str) -> str:
    key = re.sub(r"[^A-Za-z0-9_-]", "-", str(agent_id))[:64]
    return key or "default"


class ClaudeCodeExecutor:
    """Executor-shaped wrapper around one Claude Code CLI turn on the host."""

    def __init__(self, agent_id: str, model: str, system_prompt: str = ""):
        self.agent_id = agent_id
        self.model = model or "sonnet"
        self.system_prompt = system_prompt

    # ── request ──────────────────────────────────────────────────────────────

    def _request_body(self, messages: list[BaseMessage]) -> dict:
        extra_system, prompt = render_prompt(messages)
        system = "\n\n".join(p for p in (self.system_prompt.strip(), extra_system) if p)
        body: dict[str, Any] = {
            "prompt": prompt,
            "system_prompt": system,
            "model": self.model,
            "workdir_key": _workdir_key(self.agent_id),
            "permission_mode": settings.claude_code_permission_mode or "acceptEdits",
            "allowed_tools": _split_tools(settings.claude_code_allowed_tools or ""),
            "timeout_sec": settings.claude_code_timeout_sec,
        }
        if settings.claude_code_max_turns:
            body["max_turns"] = settings.claude_code_max_turns
        return body

    async def _raw_events(self, messages: list[BaseMessage]) -> AsyncIterator[dict]:
        """Yield the worker's NDJSON events. Raises ClaudeCodeError on failure."""
        url = (settings.fleet_worker_url or "").strip().rstrip("/")
        token = (settings.fleet_worker_token or "").strip()
        if not url or not token:
            raise ClaudeCodeError(
                "Claude Code not available: set FLEET_WORKER_URL and FLEET_WORKER_TOKEN "
                "so Sutra can reach the host Fleet worker."
            )
        timeout = httpx.Timeout(connect=5.0, read=float(settings.claude_code_timeout_sec) + 60, write=30.0, pool=5.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST", f"{url}/exec/claude",
                    headers={"Authorization": f"Bearer {token}"},
                    json=self._request_body(messages),
                ) as resp:
                    if resp.status_code != 200:
                        detail = (await resp.aread()).decode(errors="replace")[:500]
                        try:
                            detail = json.loads(detail).get("error", detail)
                        except Exception:
                            pass
                        if resp.status_code == 404:
                            detail += " — the Fleet worker is too old; restart it (./start.sh) to load /exec/claude"
                        raise ClaudeCodeError(f"Claude Code worker HTTP {resp.status_code}: {detail}")
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            logger.debug(f"[claude_code] non-JSON line: {line[:200]}")
        except httpx.TransportError as e:
            raise ClaudeCodeError(
                f"Claude Code worker not available at {url} ({type(e).__name__}: {e})"
            ) from e

    # ── translation to LangChain-style stream events ─────────────────────────

    async def astream_events(self, inputs: dict, config: dict | None = None, version: str = "v2"):
        """Yield on_chat_model_stream / on_tool_start / on_tool_end / on_chat_model_end."""
        messages = list(inputs.get("messages", []))
        tool_names: dict[str, str] = {}
        streamed_text = ""
        assistant_text: list[str] = []
        result: dict | None = None
        end: dict | None = None

        async for ev in self._raw_events(messages):
            etype = ev.get("type")
            top_level = not ev.get("parent_tool_use_id")

            if etype == "stream_event" and top_level:
                inner = ev.get("event") or {}
                delta = inner.get("delta") or {}
                if inner.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    if text:
                        streamed_text += text
                        yield {"event": "on_chat_model_stream", "name": PROVIDER,
                               "data": {"chunk": AIMessageChunk(content=text)}}
                elif inner.get("type") == "message_start" and streamed_text and not streamed_text.endswith("\n"):
                    # New assistant message after a tool call: keep paragraphs apart.
                    streamed_text += "\n\n"
                    yield {"event": "on_chat_model_stream", "name": PROVIDER,
                           "data": {"chunk": AIMessageChunk(content="\n\n")}}

            elif etype == "assistant":
                for block in (ev.get("message") or {}).get("content") or []:
                    if block.get("type") == "tool_use":
                        tool_names[block.get("id", "")] = block.get("name", "tool")
                        if top_level:
                            yield {"event": "on_tool_start", "name": block.get("name", "tool"),
                                   "data": {"input": block.get("input", {})}}
                    elif block.get("type") == "text" and top_level:
                        assistant_text.append(block.get("text", ""))

            elif etype == "user":
                content = (ev.get("message") or {}).get("content") or []
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result" and top_level:
                            out = _text_of(block.get("content"))
                            yield {"event": "on_tool_end",
                                   "name": tool_names.get(block.get("tool_use_id", ""), "tool"),
                                   "data": {"output": out[:4000]}}

            elif etype == "result":
                result = ev
            elif etype == "sutra_end":
                end = ev

        reply, suffix = self._finish(result, end, config, "\n\n".join(assistant_text))
        # With partial deltas the user already saw every message as it streamed;
        # without them (older CLI) send the final reply in one piece.
        to_send = suffix if streamed_text else reply + suffix
        if to_send:
            yield {"event": "on_chat_model_stream", "name": PROVIDER,
                   "data": {"chunk": AIMessageChunk(content=to_send)}}
        yield {"event": "on_chat_model_end", "name": PROVIDER,
               "data": {"output": AIMessage(content=(streamed_text or reply) + suffix)}}

    async def ainvoke(self, inputs: dict, config: dict | None = None) -> dict:
        final = ""
        async for ev in self.astream_events(inputs, config=config):
            if ev["event"] == "on_chat_model_end":
                final = ev["data"]["output"].content
        return {"messages": list(inputs.get("messages", [])) + [AIMessage(content=final)]}

    # ── end of turn ──────────────────────────────────────────────────────────

    def _finish(
        self, result: dict | None, end: dict | None, config: dict | None, text: str
    ) -> tuple[str, str]:
        """Check how the run ended and record usage.

        Returns (reply, suffix): the final reply text, and a note listing files
        the run created or changed ("" when none). Raises ClaudeCodeError.
        """
        end = end or {}
        if end.get("timed_out"):
            raise ClaudeCodeError(f"Claude Code timed out after {end.get('timeout_sec')}s")

        if result is None:
            tail = end.get("stderr_tail") or "no output"
            if _USAGE_LIMIT_RE.search(tail):
                raise ClaudeCodeError(f"Claude Code rate limit (subscription usage limit): {tail[-300:]}")
            if re.search(r"log ?in|logged in|authenticat|/login", tail, re.I):
                raise ClaudeCodeError(
                    f"Claude Code not available: the CLI is not logged in on the host. "
                    f"Run `claude` once and sign in with your Claude account. ({tail[-200:]})"
                )
            raise ClaudeCodeError(f"Claude Code exited {end.get('exit_code')} without a result: {tail[-400:]}")

        reply = str(result.get("result") or text or "").strip()
        if result.get("is_error") or result.get("subtype", "success") != "success":
            if _USAGE_LIMIT_RE.search(reply):
                raise ClaudeCodeError(f"Claude Code rate limit (subscription usage limit): {reply[:300]}")
            if result.get("subtype") == "error_max_turns":
                reply = (reply + "\n\n" if reply else "") + "_(Claude Code stopped at its turn limit.)_"
            else:
                raise ClaudeCodeError(f"Claude Code error ({result.get('subtype')}): {reply[:400]}")

        self._record_usage(result, config)

        suffix = ""
        files = end.get("files") or []
        if files:
            listing = "\n".join(f"- `{f}`" for f in files[:30])
            more = f"\n- …and {len(files) - 30} more" if len(files) > 30 else ""
            suffix = f"\n\n**Files created or changed** (on the host, in `{end.get('workdir')}`):\n{listing}{more}"
        return reply, suffix

    @staticmethod
    def _record_usage(result: dict, config: dict | None) -> None:
        usage = result.get("usage") or {}
        total = sum(int(usage.get(k) or 0) for k in (
            "input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
        ))
        if not total:
            return
        for cb in (config or {}).get("callbacks") or []:
            if hasattr(cb, "tokens_used"):
                cb.tokens_used = (cb.tokens_used or 0) + total
