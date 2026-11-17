"""Claude Code provider: Fleet worker /exec/claude + ClaudeCodeExecutor.

The worker runs against a fake `claude` command that replays stream-json
events, so these tests never touch a real subscription.
"""

import importlib.util
import json
import stat
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.config import settings
from app.core.claude_code_executor import (
    ClaudeCodeError,
    ClaudeCodeExecutor,
    _split_tools,
    render_prompt,
)
from app.core.orchestrator import _is_retriable_llm_error

WORKER = Path(__file__).resolve().parents[2] / "scripts" / "fleet_worker.py"
TOKEN = "test-token"

# Fake CLI. Behaviour is picked by the prompt text it reads on stdin.
FAKE_CLAUDE = r'''#!{python}
import json, os, sys
args = sys.argv[1:]
prompt = sys.stdin.read()
open(os.path.join({log!r}), "a").write(json.dumps({{"args": args, "prompt": prompt, "cwd": os.getcwd(),
    "api_key_seen": "ANTHROPIC_API_KEY" in os.environ, "token_seen": "FLEET_WORKER_TOKEN" in os.environ}}) + "\n")
def out(o): print(json.dumps(o), flush=True)
if "LIMIT" in prompt:
    out({{"type": "result", "subtype": "success", "is_error": True,
         "result": "Claude AI usage limit reached|1760000000"}})
    sys.exit(1)
if "LOGIN" in prompt:
    sys.stderr.write("Invalid API key · Please run /login\n"); sys.exit(1)
out({{"type": "system", "subtype": "init", "model": "claude-sonnet"}})
for t in ["Making ", "the deck."]:
    out({{"type": "stream_event", "parent_tool_use_id": None,
         "event": {{"type": "content_block_delta", "delta": {{"type": "text_delta", "text": t}}}}}})
out({{"type": "assistant", "parent_tool_use_id": None, "message": {{"content": [
    {{"type": "text", "text": "Making the deck."}},
    {{"type": "tool_use", "id": "tu1", "name": "Write", "input": {{"file_path": "deck.md"}}}}]}}}})
open("deck.md", "w").write("# Slides\n")
out({{"type": "user", "parent_tool_use_id": None, "message": {{"content": [
    {{"type": "tool_result", "tool_use_id": "tu1", "content": "File created"}}]}}}})
out({{"type": "stream_event", "parent_tool_use_id": None, "event": {{"type": "message_start"}}}})
out({{"type": "stream_event", "parent_tool_use_id": None,
     "event": {{"type": "content_block_delta", "delta": {{"type": "text_delta", "text": "Done."}}}}}})
out({{"type": "result", "subtype": "success", "is_error": False, "result": "Done.",
     "usage": {{"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 5}}}})
'''


@pytest.fixture
def worker(tmp_path, monkeypatch):
    """Load the worker with a fake claude and serve it on a random local port."""
    log = tmp_path / "claude_calls.jsonl"
    fake = tmp_path / "claude"
    fake.write_text(FAKE_CLAUDE.format(python=sys.executable, log=str(log)))
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)

    env = {"SUTRA_URL": "http://sutra.test", "FLEET_WORKER_TOKEN": TOKEN, "FLEET_WORKER_ID": "mac",
           "FLEET_WORKSPACE_ROOT": str(tmp_path / "ws"), "SHAKHA_BIN": str(tmp_path / "shakha"),
           "CLAUDE_BIN": str(fake), "ANTHROPIC_API_KEY": "sk-should-not-leak"}
    for k in ("GEMINI_HOME", "GITHUB_TOKEN", "CLAUDE_WORKSPACE_ROOT", "CLAUDE_ALLOW_BYPASS"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    spec = importlib.util.spec_from_file_location("fleet_worker_claude_test", WORKER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    server = mod._ReuseAddrServer(("127.0.0.1", 0), mod.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    mod._url = f"http://127.0.0.1:{server.server_address[1]}"
    mod._calls = lambda: [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
    monkeypatch.setattr(settings, "fleet_worker_url", mod._url)
    monkeypatch.setattr(settings, "fleet_worker_token", TOKEN)
    monkeypatch.setattr(settings, "claude_code_permission_mode", "acceptEdits")
    monkeypatch.setattr(settings, "claude_code_allowed_tools", "Bash(python3:*),Read")
    monkeypatch.setattr(settings, "claude_code_max_turns", 0)
    yield mod
    server.shutdown()
    server.server_close()


def _post(url, body, token=TOKEN):
    req = urllib.request.Request(f"{url}/exec/claude", data=json.dumps(body).encode(), method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    return urllib.request.urlopen(req, timeout=30)


# ── worker ───────────────────────────────────────────────────────────────────


def test_worker_streams_events_and_lists_changed_files(worker):
    with _post(worker._url, {"prompt": "make a deck", "workdir_key": "agent-1", "model": "opus",
                             "system_prompt": "You build decks."}) as r:
        events = [json.loads(line) for line in r.read().decode().splitlines()]
    assert events[0]["type"] == "sutra_start"
    assert any(e["type"] == "result" for e in events)
    end = events[-1]
    assert end["type"] == "sutra_end" and end["exit_code"] == 0 and not end["timed_out"]
    assert end["files"] == [str(Path(end["workdir"]) / "deck.md")]

    call = worker._calls()[0]
    assert call["prompt"] == "make a deck"
    assert call["cwd"].endswith("claude-code/agent-1")
    assert call["args"][call["args"].index("--model") + 1] == "opus"
    assert call["args"][call["args"].index("--append-system-prompt") + 1] == "You build decks."
    # Secrets never reach the CLI; an API key would bill the API, not the subscription.
    assert call["api_key_seen"] is False and call["token_seen"] is False


def test_worker_rejects_bad_requests(worker):
    with pytest.raises(urllib.error.HTTPError) as e:
        _post(worker._url, {"prompt": "x", "workdir_key": "a"}, token="wrong")
    assert e.value.code == 403
    for body in ({"prompt": "x", "workdir_key": "../etc"},
                 {"prompt": "", "workdir_key": "a"},
                 {"prompt": "x", "workdir_key": "a", "permission_mode": "bypassPermissions"},
                 {"prompt": "x", "workdir_key": "a", "model": "sonnet; rm -rf /"},
                 {"prompt": "x", "workdir_key": "a", "allowed_tools": ["Bash(x)) --evil"]}):
        with pytest.raises(urllib.error.HTTPError) as e:
            _post(worker._url, body)
        assert e.value.code == 400, body
    assert worker._calls() == []


def test_worker_health_reports_claude(worker):
    with urllib.request.urlopen(f"{worker._url}/health", timeout=10) as r:
        assert json.loads(r.read())["claude_ready"] is True


# ── executor end to end ──────────────────────────────────────────────────────


async def _collect(executor, messages, config=None):
    return [e async for e in executor.astream_events({"messages": messages}, config=config or {})]


async def test_executor_translates_stream_to_langchain_events(worker):
    class CB:
        tokens_used = 0

    cb = CB()
    ex = ClaudeCodeExecutor(agent_id="agent-1", model="sonnet", system_prompt="You build decks.")
    events = await _collect(ex, [SystemMessage("Memory: likes dark themes"), HumanMessage("deck please")],
                            {"callbacks": [cb]})
    kinds = [e["event"] for e in events]
    assert kinds.count("on_tool_start") == 1 and kinds.count("on_tool_end") == 1
    tool_start = next(e for e in events if e["event"] == "on_tool_start")
    assert tool_start["name"] == "Write"
    assert next(e for e in events if e["event"] == "on_tool_end")["data"]["output"] == "File created"

    streamed = "".join(e["data"]["chunk"].content for e in events if e["event"] == "on_chat_model_stream")
    assert streamed.startswith("Making the deck.\n\nDone.")
    assert "deck.md" in streamed  # files note is streamed too
    final = events[-1]
    assert final["event"] == "on_chat_model_end" and final["data"]["output"].content == streamed
    assert cb.tokens_used == 125

    call = worker._calls()[0]
    system = call["args"][call["args"].index("--append-system-prompt") + 1]
    assert system.startswith("You build decks.") and "likes dark themes" in system
    tools = call["args"][call["args"].index("--allowedTools") + 1]
    assert tools == "Bash(python3:*),Read"


async def test_executor_ainvoke_returns_final_message(worker):
    ex = ClaudeCodeExecutor(agent_id="agent-2", model="sonnet")
    out = await ex.ainvoke({"messages": [HumanMessage("deck please")]})
    assert isinstance(out["messages"][-1], AIMessage)
    assert "Done." in out["messages"][-1].content


async def test_usage_limit_is_retriable_so_purpose_falls_back(worker):
    ex = ClaudeCodeExecutor(agent_id="agent-3", model="sonnet")
    with pytest.raises(ClaudeCodeError) as e:
        await _collect(ex, [HumanMessage("LIMIT")])
    assert "rate limit" in str(e.value) and _is_retriable_llm_error(e.value)


async def test_not_logged_in_is_explained(worker):
    ex = ClaudeCodeExecutor(agent_id="agent-4", model="sonnet")
    with pytest.raises(ClaudeCodeError) as e:
        await _collect(ex, [HumanMessage("LOGIN")])
    assert "not logged in" in str(e.value) and _is_retriable_llm_error(e.value)


async def test_worker_offline_is_retriable(monkeypatch):
    monkeypatch.setattr(settings, "fleet_worker_url", "http://127.0.0.1:9")
    monkeypatch.setattr(settings, "fleet_worker_token", TOKEN)
    ex = ClaudeCodeExecutor(agent_id="agent-5", model="sonnet")
    with pytest.raises(ClaudeCodeError) as e:
        await _collect(ex, [HumanMessage("hi")])
    assert _is_retriable_llm_error(e.value)


# ── helpers ──────────────────────────────────────────────────────────────────


def test_render_prompt_includes_history():
    system, prompt = render_prompt([
        SystemMessage("time: now"), HumanMessage("first"), AIMessage("answer"), HumanMessage("second"),
    ])
    assert system == "time: now"
    assert "User: first" in prompt and "Assistant: answer" in prompt
    assert prompt.endswith("Latest message from the user:\nsecond")
    assert render_prompt([HumanMessage("only")]) == ("", "only")


def test_split_tools_keeps_commas_in_parentheses():
    assert _split_tools("Read, Bash(git diff:*,x), Write") == ["Read", "Bash(git diff:*,x)", "Write"]
    assert _split_tools("") == []
