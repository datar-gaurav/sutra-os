"""CLI agent executors — run a chat turn on the user's Claude or ChatGPT subscription.

A purpose slot with provider ``claude_code`` or ``codex`` routes the whole turn
here instead of to a LangChain chat model. These CLIs are agents, not models:
they run their own tool loop (files, shell, skills), so they cannot sit inside
LangGraph's ReAct graph. The executors mimic the two methods the orchestrator
calls (``ainvoke`` and ``astream_events``) so routing, fallback, circuit
breakers, traces and usage tracking all keep working unchanged.

Each turn is sent to the host Fleet worker (``POST {fleet_worker_url}/exec/<cli>``),
which runs the official CLI logged in with the user's subscription. The login
never leaves the host. The worker streams the CLI's JSON events back as NDJSON
(framed by ``sutra_start`` / ``sutra_end``); each subclass translates its CLI's
events into LangChain-style stream events.

Each call is stateless: the agent's system prompt, memory context and recent
chat history are rendered into the prompt every turn. Files persist between
turns because each agent gets its own working folder on the host.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage

from app.config import settings

logger = logging.getLogger(__name__)

CLI_PROVIDERS = frozenset({"claude_code", "codex"})

# Aliases the Claude Code CLI accepts; full model ids (claude-sonnet-…) also work.
CLAUDE_CODE_MODELS = ["sonnet", "opus", "haiku", "opusplan"]

_USAGE_LIMIT_RE = re.compile(
    r"usage limit|limit reached|hit your (usage )?limit|rate.?limit|out of (extra )?usage|too many requests",
    re.I,
)
_LOGIN_RE = re.compile(r"log ?in|logged in|authenticat|/login|unauthorized|\b401\b", re.I)


class CliAgentError(RuntimeError):
    """A CLI agent turn failed. Messages are phrased so the orchestrator's
    retriable-error check (``rate limit`` / ``not available`` / ``capacity``)
    sends the turn to the next purpose slot when that makes sense."""


# Backwards-compatible name from the Claude-only version.
ClaudeCodeError = CliAgentError


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
    user message so the CLI sees the conversation.
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


def _stream(provider: str, text: str) -> dict:
    return {"event": "on_chat_model_stream", "name": provider,
            "data": {"chunk": AIMessageChunk(content=text)}}


@dataclass
class _Run:
    """What a translator learned from one CLI run."""

    streamed: str = ""                  # text already sent to the user as tokens
    reply: str = ""                     # final reply, if the CLI reports one
    error: str = ""                     # CLI-reported failure
    error_kind: str = ""                # CLI-specific failure label
    tokens: int = 0
    end: dict = field(default_factory=dict)
    finished: bool = False              # the CLI reported a final result


class CliAgentExecutor:
    """Executor-shaped wrapper around one CLI agent turn on the host."""

    provider = ""
    label = ""
    endpoint = ""
    default_model = ""

    def __init__(self, agent_id: str, model: str, system_prompt: str = ""):
        self.agent_id = agent_id
        self.model = model or self.default_model
        self.system_prompt = system_prompt

    # ── subclass hooks ───────────────────────────────────────────────────────

    @property
    def timeout_sec(self) -> int:
        raise NotImplementedError

    def _extra_body(self) -> dict:
        return {}

    def _translate(self, raw: AsyncIterator[dict], run: _Run) -> AsyncIterator[dict]:
        """Yield LangChain-style events for the CLI's events, filling in ``run``."""
        raise NotImplementedError

    # ── request ──────────────────────────────────────────────────────────────

    def _request_body(self, messages: list[BaseMessage]) -> dict:
        extra_system, prompt = render_prompt(messages)
        system = "\n\n".join(p for p in (self.system_prompt.strip(), extra_system) if p)
        return {
            "prompt": prompt,
            "system_prompt": system,
            "model": self.model,
            "workdir_key": _workdir_key(self.agent_id),
            "timeout_sec": self.timeout_sec,
            **self._extra_body(),
        }

    async def _raw_events(self, messages: list[BaseMessage]) -> AsyncIterator[dict]:
        """Yield the worker's NDJSON events. Raises CliAgentError on failure."""
        url = (settings.fleet_worker_url or "").strip().rstrip("/")
        token = (settings.fleet_worker_token or "").strip()
        if not url or not token:
            raise CliAgentError(
                f"{self.label} not available: set FLEET_WORKER_URL and FLEET_WORKER_TOKEN "
                "so Sutra can reach the host Fleet worker."
            )
        timeout = httpx.Timeout(connect=5.0, read=float(self.timeout_sec) + 60, write=30.0, pool=5.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST", f"{url}{self.endpoint}",
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
                            detail += (f" — the Fleet worker is too old; restart it (./start.sh) "
                                       f"to load {self.endpoint}")
                        raise CliAgentError(f"{self.label} worker HTTP {resp.status_code}: {detail}")
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            logger.debug(f"[{self.provider}] non-JSON line: {line[:200]}")
        except httpx.TransportError as e:
            raise CliAgentError(
                f"{self.label} worker not available at {url} ({type(e).__name__}: {e})"
            ) from e

    async def _framed(self, messages: list[BaseMessage], run: _Run) -> AsyncIterator[dict]:
        """CLI events only; the worker's sutra_end frame goes into ``run.end``."""
        async for ev in self._raw_events(messages):
            if ev.get("type") == "sutra_end":
                run.end = ev
            elif ev.get("type") != "sutra_start":
                yield ev

    # ── LangChain-style interface ────────────────────────────────────────────

    async def astream_events(self, inputs: dict, config: dict | None = None, version: str = "v2"):
        """Yield on_chat_model_stream / on_tool_start / on_tool_end / on_chat_model_end."""
        messages = list(inputs.get("messages", []))
        run = _Run()
        async for ev in self._translate(self._framed(messages, run), run):
            yield ev

        reply, suffix = self._finish(run, config)
        # With streamed text the user already saw every message; otherwise send
        # the final reply in one piece.
        to_send = suffix if run.streamed else reply + suffix
        if to_send:
            yield _stream(self.provider, to_send)
        yield {"event": "on_chat_model_end", "name": self.provider,
               "data": {"output": AIMessage(content=(run.streamed or reply) + suffix)}}

    async def ainvoke(self, inputs: dict, config: dict | None = None) -> dict:
        final = ""
        async for ev in self.astream_events(inputs, config=config):
            if ev["event"] == "on_chat_model_end":
                final = ev["data"]["output"].content
        return {"messages": list(inputs.get("messages", [])) + [AIMessage(content=final)]}

    # ── end of turn ──────────────────────────────────────────────────────────

    def _finish(self, run: _Run, config: dict | None) -> tuple[str, str]:
        """Check how the run ended and record usage.

        Returns (reply, suffix): the final reply text, and a note listing files
        the run created or changed ("" when none). Raises CliAgentError.
        """
        end = run.end
        if end.get("timed_out"):
            raise CliAgentError(f"{self.label} timed out after {end.get('timeout_sec')}s")

        if run.error:
            if _USAGE_LIMIT_RE.search(run.error):
                raise CliAgentError(f"{self.label} rate limit (subscription usage limit): {run.error[:300]}")
            if _LOGIN_RE.search(run.error):
                raise CliAgentError(f"{self.label} not available: {self._login_hint()} ({run.error[:200]})")
            raise CliAgentError(f"{self.label} error{f' ({run.error_kind})' if run.error_kind else ''}: "
                                f"{run.error[:400]}")

        if not run.finished:
            tail = end.get("stderr_tail") or "no output"
            if _USAGE_LIMIT_RE.search(tail):
                raise CliAgentError(f"{self.label} rate limit (subscription usage limit): {tail[-300:]}")
            if _LOGIN_RE.search(tail):
                raise CliAgentError(f"{self.label} not available: {self._login_hint()} ({tail[-200:]})")
            raise CliAgentError(f"{self.label} exited {end.get('exit_code')} without a result: {tail[-400:]}")

        for cb in (config or {}).get("callbacks") or []:
            if run.tokens and hasattr(cb, "tokens_used"):
                cb.tokens_used = (cb.tokens_used or 0) + run.tokens

        suffix = ""
        files = end.get("files") or []
        if files:
            listing = "\n".join(f"- `{f}`" for f in files[:30])
            more = f"\n- …and {len(files) - 30} more" if len(files) > 30 else ""
            suffix = f"\n\n**Files created or changed** (on the host, in `{end.get('workdir')}`):\n{listing}{more}"
        return run.reply.strip(), suffix

    def _login_hint(self) -> str:
        return "the CLI is not logged in on the host"


# ─── Claude Code ─────────────────────────────────────────────────────────────


class ClaudeCodeExecutor(CliAgentExecutor):
    """Claude Code (`claude -p --output-format stream-json`) on a Claude subscription."""

    provider = "claude_code"
    label = "Claude Code"
    endpoint = "/exec/claude"
    default_model = "sonnet"

    @property
    def timeout_sec(self) -> int:
        return settings.claude_code_timeout_sec

    def _extra_body(self) -> dict:
        body: dict[str, Any] = {
            "permission_mode": settings.claude_code_permission_mode or "acceptEdits",
            "allowed_tools": _split_tools(settings.claude_code_allowed_tools or ""),
        }
        if settings.claude_code_max_turns:
            body["max_turns"] = settings.claude_code_max_turns
        return body

    def _login_hint(self) -> str:
        return ("the CLI is not logged in on the host. "
                "Run `claude` once and sign in with your Claude account")

    async def _translate(self, raw: AsyncIterator[dict], run: _Run) -> AsyncIterator[dict]:
        tool_names: dict[str, str] = {}
        assistant_text: list[str] = []
        async for ev in raw:
            etype = ev.get("type")
            top_level = not ev.get("parent_tool_use_id")

            if etype == "stream_event" and top_level:
                inner = ev.get("event") or {}
                delta = inner.get("delta") or {}
                if inner.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    if text:
                        run.streamed += text
                        yield _stream(self.provider, text)
                elif inner.get("type") == "message_start" and run.streamed and not run.streamed.endswith("\n"):
                    # New assistant message after a tool call: keep paragraphs apart.
                    run.streamed += "\n\n"
                    yield _stream(self.provider, "\n\n")

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
                            yield {"event": "on_tool_end",
                                   "name": tool_names.get(block.get("tool_use_id", ""), "tool"),
                                   "data": {"output": _text_of(block.get("content"))[:4000]}}

            elif etype == "result":
                run.finished = True
                text = str(ev.get("result") or "\n\n".join(assistant_text) or "")
                usage = ev.get("usage") or {}
                run.tokens = sum(int(usage.get(k) or 0) for k in (
                    "input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
                ))
                subtype = ev.get("subtype", "success")
                if subtype == "error_max_turns":
                    run.reply = (text + "\n\n" if text else "") + "_(Claude Code stopped at its turn limit.)_"
                    if run.streamed:
                        run.streamed += "\n\n_(Claude Code stopped at its turn limit.)_"
                        yield _stream(self.provider, "\n\n_(Claude Code stopped at its turn limit.)_")
                elif ev.get("is_error") or subtype != "success":
                    run.error, run.error_kind = text or "unknown error", subtype
                else:
                    run.reply = text


# ─── Codex ───────────────────────────────────────────────────────────────────


class CodexExecutor(CliAgentExecutor):
    """OpenAI Codex (`codex exec --json`) on a ChatGPT subscription."""

    provider = "codex"
    label = "Codex"
    endpoint = "/exec/codex"
    default_model = "default"

    @property
    def timeout_sec(self) -> int:
        return settings.codex_timeout_sec

    def _extra_body(self) -> dict:
        body: dict[str, Any] = {"sandbox": settings.codex_sandbox_mode or "workspace-write"}
        if settings.codex_reasoning_effort:
            body["reasoning_effort"] = settings.codex_reasoning_effort
        return body

    def _login_hint(self) -> str:
        return ("the CLI is not logged in on the host. "
                "Run `codex login` and choose Sign in with ChatGPT")

    @staticmethod
    def _tool_start(item: dict) -> tuple[str, Any] | None:
        kind = item.get("type")
        if kind == "command_execution":
            return "shell", {"command": item.get("command", "")}
        if kind == "file_change":
            return "file_change", {"changes": item.get("changes", [])}
        if kind == "mcp_tool_call":
            return f"{item.get('server', 'mcp')}.{item.get('tool', 'tool')}", item.get("arguments", {})
        if kind == "web_search":
            return "web_search", {"query": item.get("query", "")}
        return None

    @staticmethod
    def _tool_output(item: dict) -> str:
        kind = item.get("type")
        if kind == "command_execution":
            out = item.get("aggregated_output", "") or ""
            code = item.get("exit_code")
            return (out + (f"\n(exit code {code})" if code not in (None, 0) else "")).strip()
        if kind == "file_change":
            return "\n".join(f"{c.get('kind', 'change')}: {c.get('path', '')}" for c in item.get("changes", []))
        if kind == "mcp_tool_call":
            if item.get("error"):
                return f"error: {item['error']}"
            return json.dumps(item.get("result"), default=str)[:4000]
        return str(item.get("status", "done"))

    async def _translate(self, raw: AsyncIterator[dict], run: _Run) -> AsyncIterator[dict]:
        started: set[str] = set()
        messages: list[str] = []
        async for ev in raw:
            etype = ev.get("type", "")
            item = ev.get("item") or {}

            if etype == "item.started":
                tool = self._tool_start(item)
                if tool:
                    started.add(item.get("id", ""))
                    yield {"event": "on_tool_start", "name": tool[0], "data": {"input": tool[1]}}

            elif etype == "item.completed":
                if item.get("type") == "agent_message":
                    text = item.get("text", "") or ""
                    if text:
                        sep = "\n\n" if run.streamed else ""
                        run.streamed += sep + text
                        messages.append(text)
                        yield _stream(self.provider, sep + text)
                    continue
                tool = self._tool_start(item)
                if tool:
                    if item.get("id", "") not in started:
                        yield {"event": "on_tool_start", "name": tool[0], "data": {"input": tool[1]}}
                    yield {"event": "on_tool_end", "name": tool[0],
                           "data": {"output": self._tool_output(item)[:4000]}}

            elif etype == "turn.completed":
                run.finished = True
                usage = ev.get("usage") or {}
                run.tokens = sum(int(usage.get(k) or 0) for k in ("input_tokens", "output_tokens"))
                run.reply = messages[-1] if messages else ""

            elif etype == "turn.failed":
                run.error = str((ev.get("error") or {}).get("message") or "turn failed")
                run.error_kind = "turn.failed"

            elif etype == "error" and not run.error:
                run.error = str(ev.get("message") or "unknown error")
                run.error_kind = "error"


_EXECUTORS: dict[str, type[CliAgentExecutor]] = {
    "claude_code": ClaudeCodeExecutor,
    "codex": CodexExecutor,
}


def build_cli_executor(provider: str, agent_id: str, model: str, system_prompt: str) -> CliAgentExecutor:
    return _EXECUTORS[provider](agent_id=agent_id, model=model, system_prompt=system_prompt)


async def fetch_codex_models() -> list[dict]:
    """Models the host's Codex login offers (via the Fleet worker). [] when unreachable."""
    url = (settings.fleet_worker_url or "").strip().rstrip("/")
    token = (settings.fleet_worker_token or "").strip()
    models: list[dict] = [{"id": "default", "name": "Default (Codex config)"}]
    if not url or not token:
        return models
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{url}/models/codex", headers={"Authorization": f"Bearer {token}"})
            if r.status_code == 200:
                models += [{"id": m["id"], "name": m.get("name") or m["id"]}
                           for m in r.json().get("models", []) if m.get("id")]
    except Exception as e:
        logger.debug(f"[codex] model list unavailable: {e}")
    return models
