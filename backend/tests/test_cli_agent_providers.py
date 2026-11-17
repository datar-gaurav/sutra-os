"""CLI agent providers: Fleet worker /exec/{claude,codex} + their executors.

The worker runs against fake `claude` / `codex` commands that replays stream-json
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
from app.core.cli_agent_executor import (
    ClaudeCodeError,
    ClaudeCodeExecutor,
    CodexExecutor,
    fetch_codex_models,
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


FAKE_CODEX = r'''#!{python}
import json, os, sys
args = sys.argv[1:]
prompt = sys.stdin.read()
open({log!r}, "a").write(json.dumps({{"args": args, "prompt": prompt, "cwd": os.getcwd(),
    "api_key_seen": "OPENAI_API_KEY" in os.environ}}) + "\n")
def out(o): print(json.dumps(o), flush=True)
out({{"type": "thread.started", "thread_id": "t1"}})
out({{"type": "turn.started"}})
if "LIMIT" in prompt:
    out({{"type": "error", "message": "You've hit your usage limit. Try again later."}})
    out({{"type": "turn.failed", "error": {{"message": "You've hit your usage limit. Try again later."}}}})
    sys.exit(1)
out({{"type": "item.completed", "item": {{"id": "i0", "type": "reasoning", "text": "thinking"}}}})
out({{"type": "item.completed", "item": {{"id": "i1", "type": "agent_message", "text": "Building slides."}}}})
out({{"type": "item.started", "item": {{"id": "i2", "type": "command_execution", "command": "python3 make.py",
     "aggregated_output": "", "status": "in_progress"}}}})
open("deck.pptx", "w").write("x")
out({{"type": "item.completed", "item": {{"id": "i2", "type": "command_execution", "command": "python3 make.py",
     "aggregated_output": "saved deck.pptx", "exit_code": 0, "status": "completed"}}}})
out({{"type": "item.completed", "item": {{"id": "i3", "type": "file_change",
     "changes": [{{"path": os.path.join(os.getcwd(), "notes.md"), "kind": "add"}}], "status": "completed"}}}})
out({{"type": "item.completed", "item": {{"id": "i4", "type": "agent_message", "text": "Done."}}}})
out({{"type": "turn.completed", "usage": {{"input_tokens": 300, "cached_input_tokens": 200, "output_tokens": 40}}}})
'''


@pytest.fixture
def worker(tmp_path, monkeypatch):
    """Load the worker with a fake claude and serve it on a random local port."""
    log = tmp_path / "claude_calls.jsonl"
    fake = tmp_path / "claude"
    fake.write_text(FAKE_CLAUDE.format(python=sys.executable, log=str(log)))
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    codex_log = tmp_path / "codex_calls.jsonl"
    fake_codex = tmp_path / "codex"
    fake_codex.write_text(FAKE_CODEX.format(python=sys.executable, log=str(codex_log)))
    fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IEXEC)
    codex_home = tmp_path / "codex_home"
    codex_home.mkdir()
    (codex_home / "models_cache.json").write_text(json.dumps({"models": [
        {"slug": "gpt-test", "display_name": "GPT Test", "visibility": "list"},
        {"slug": "hidden-model", "visibility": "hide"}]}))

    env = {"SUTRA_URL": "http://sutra.test", "FLEET_WORKER_TOKEN": TOKEN, "FLEET_WORKER_ID": "mac",
           "FLEET_WORKSPACE_ROOT": str(tmp_path / "ws"), "SHAKHA_BIN": str(tmp_path / "shakha"),
           "CLAUDE_BIN": str(fake), "ANTHROPIC_API_KEY": "sk-should-not-leak",
           "CODEX_BIN": str(fake_codex), "CODEX_HOME": str(codex_home), "OPENAI_API_KEY": "sk-nope"}
    for k in ("GEMINI_HOME", "GITHUB_TOKEN", "CLAUDE_WORKSPACE_ROOT", "CLAUDE_ALLOW_BYPASS",
              "CODEX_WORKSPACE_ROOT", "CODEX_ALLOW_FULL_ACCESS"):
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
    mod._codex_calls = lambda: (
        [json.loads(x) for x in codex_log.read_text().splitlines()] if codex_log.exists() else [])
    monkeypatch.setattr(settings, "fleet_worker_url", mod._url)
    monkeypatch.setattr(settings, "fleet_worker_token", TOKEN)
    monkeypatch.setattr(settings, "claude_code_permission_mode", "acceptEdits")
    monkeypatch.setattr(settings, "claude_code_allowed_tools", "Bash(python3:*),Read")
    monkeypatch.setattr(settings, "claude_code_max_turns", 0)
    monkeypatch.setattr(settings, "codex_sandbox_mode", "workspace-write")
    monkeypatch.setattr(settings, "codex_reasoning_effort", "")
    yield mod
    server.shutdown()
    server.server_close()


def _post(url, body, token=TOKEN, cli="claude"):
    req = urllib.request.Request(f"{url}/exec/{cli}", data=json.dumps(body).encode(), method="POST")
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
        health = json.loads(r.read())
    assert health["claude_ready"] is True and health["codex_ready"] is True


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


# ── codex ────────────────────────────────────────────────────────────────────


def test_codex_worker_builds_safe_command(worker):
    with _post(worker._url, {"prompt": "slides", "workdir_key": "agent-9", "model": "gpt-test",
                             "system_prompt": "You build decks.", "reasoning_effort": "high"},
               cli="codex") as r:
        events = [json.loads(line) for line in r.read().decode().splitlines()]
    assert events[0]["runner"] == "codex" and events[-1]["type"] == "sutra_end"
    call = worker._codex_calls()[0]
    args = call["args"]
    assert args[:2] == ["exec", "--json"] and args[-1] == "-"
    assert args[args.index("-s") + 1] == "workspace-write"
    assert args[args.index("-m") + 1] == "gpt-test"
    assert 'model_reasoning_effort="high"' in args
    assert call["cwd"].endswith("codex/agent-9")
    assert call["prompt"].startswith("<agent_instructions>\nYou build decks.\n</agent_instructions>")
    assert call["prompt"].endswith("slides")
    assert call["api_key_seen"] is False


def test_codex_worker_rejects_full_access_and_default_model_omits_flag(worker):
    with pytest.raises(urllib.error.HTTPError) as e:
        _post(worker._url, {"prompt": "x", "workdir_key": "a", "sandbox": "danger-full-access"}, cli="codex")
    assert e.value.code == 400
    with _post(worker._url, {"prompt": "x", "workdir_key": "a", "model": "default"}, cli="codex") as r:
        r.read()
    assert "-m" not in worker._codex_calls()[0]["args"]


async def test_codex_executor_translates_events(worker):
    class CB:
        tokens_used = 0

    cb = CB()
    ex = CodexExecutor(agent_id="agent-9", model="gpt-test", system_prompt="You build decks.")
    events = await _collect(ex, [HumanMessage("slides")], {"callbacks": [cb]})
    starts = [e["name"] for e in events if e["event"] == "on_tool_start"]
    ends = [(e["name"], e["data"]["output"]) for e in events if e["event"] == "on_tool_end"]
    assert starts == ["shell", "file_change"]
    assert ends[0] == ("shell", "saved deck.pptx")
    assert ends[1][0] == "file_change" and ends[1][1].startswith("add: ")
    streamed = "".join(e["data"]["chunk"].content for e in events if e["event"] == "on_chat_model_stream")
    assert streamed.startswith("Building slides.\n\nDone.") and "deck.pptx" in streamed
    assert "thinking" not in streamed
    assert events[-1]["data"]["output"].content == streamed
    assert cb.tokens_used == 340


async def test_codex_usage_limit_falls_back(worker):
    ex = CodexExecutor(agent_id="agent-10", model="default")
    with pytest.raises(ClaudeCodeError) as e:
        await _collect(ex, [HumanMessage("LIMIT")])
    assert "Codex rate limit" in str(e.value) and _is_retriable_llm_error(e.value)


async def test_codex_models_come_from_worker(worker):
    models = await fetch_codex_models()
    assert [m["id"] for m in models] == ["default", "gpt-test"]
