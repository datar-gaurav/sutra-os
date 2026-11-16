"""Fleet worker's Shakha runner, driven against a fake `shakha` command."""

import importlib.util
import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest

WORKER = Path(__file__).resolve().parents[2] / "scripts" / "fleet_worker.py"


@pytest.fixture
def worker(tmp_path, monkeypatch):
    """Load the worker with a fake shakha that logs calls and replays fixtures."""
    repo = tmp_path / "checkout"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin",
                    "git@github.com:Acme/Widgets.git"], check=True)

    calls = tmp_path / "calls.jsonl"
    state = tmp_path / "task.json"
    fake = tmp_path / "shakha"
    fake.write_text(f"""#!{sys.executable}
import json, sys
args = sys.argv[1:]
open({str(calls)!r}, "a").write(json.dumps(args) + "\\n")
if args[:2] == ["repo", "list"]:
    print(json.dumps({{"repos": [
        {{"repoId": "r0", "path": "/nope", "name": "gone", "exists": False, "added": True, "lastUsedAt": "x"}},
        {{"repoId": "r1", "path": {str(repo)!r}, "name": "checkout", "exists": True, "added": True, "lastUsedAt": "x"}}]}}))
elif args[:2] == ["task", "create"]:
    print(json.dumps({{"taskId": "task_01HZZZZZZZZZZZZZZZZZZZZZZZ"}}))
elif args[:2] == ["task", "get"]:
    print(open({str(state)!r}).read())
elif args[:2] == ["task", "cancel"]:
    print("{{}}")
elif args[:1] == ["status"]:
    print("{{}}")
else:
    sys.exit(3)
""")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)

    env = {"SUTRA_URL": "http://sutra.test", "FLEET_WORKER_TOKEN": "t", "FLEET_WORKER_ID": "mac",
           "FLEET_WORKSPACE_ROOT": str(tmp_path / "ws"), "SHAKHA_BIN": str(fake)}
    for k in ("GEMINI_HOME", "GITHUB_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    spec = importlib.util.spec_from_file_location("fleet_worker_under_test", WORKER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    sent = []
    monkeypatch.setattr(mod, "_api", lambda method, path, body=None: sent.append((method, path, body)) or mod._test_api_reply(method, path))
    mod._test_api_reply = lambda method, path: None
    mod._calls = lambda: [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []
    mod._set_task = lambda task: state.write_text(json.dumps(task))
    mod._sent = sent
    mod._repo = str(repo)
    return mod


def test_shakha_only_worker_needs_no_gemini_or_github(worker):
    assert worker.RUNNERS == ["shakha"]
    worker.claim_job()
    assert worker._sent[-1] == ("POST", "/claim", {"runners": ["shakha"]})


def test_normalize_repo_forms(worker):
    for url in ("git@github.com:Acme/Widgets.git", "https://github.com/acme/widgets",
                "https://github.com/acme/widgets.git/", "ssh://git@github.com/Acme/Widgets", "acme/widgets"):
        assert worker.normalize_repo(url) == "acme/widgets", url


def test_start_creates_task_idempotently_in_the_matching_checkout(worker):
    rc = worker.start_shakha_job({"id": "job-1", "repo_url": "acme/widgets", "title": "Add X", "prompt": "Do X"})
    assert rc == 0
    create = next(c for c in worker._calls() if c[:2] == ["task", "create"])
    assert create[create.index("--repo") + 1] == worker._repo
    assert create[create.index("--agent") + 1] == "auto", "never the fake test agent"
    assert create[create.index("--key") + 1] == "sutra-fleet-job-1"
    last = worker._sent[-1]
    assert last[1] == "/job-1/status"
    assert last[2]["external_ref"] == "task_01HZZZZZZZZZZZZZZZZZZZZZZZ"


def test_unknown_repo_fails_with_instructions(worker):
    rc = worker.start_shakha_job({"id": "job-2", "repo_url": "acme/other", "title": "t", "prompt": "p"})
    assert rc == 1
    status = worker._sent[-1][2]
    assert status["status"] == "failed" and "shakha repo add" in status["error"]
    assert not any(c[:2] == ["task", "create"] for c in worker._calls())


@pytest.mark.parametrize("task, expected", [
    ({"execution": "awaiting_approval", "attentionReasons": [{"level": "action_required", "type": "plan_approval"}]},
     {"status": "running", "note": "Shakha: awaiting_approval (plan_approval) — answer in Shakha or Powerdial"}),
    ({"execution": "running", "deliveryDetail": {"url": "https://github.com/acme/widgets/pull/42", "status": "published"}},
     {"status": "running", "pr_url": "https://github.com/acme/widgets/pull/42", "pr_number": 42}),
    ({"execution": "completed", "deliveryDetail": {"url": "https://github.com/acme/widgets/pull/42"}},
     {"status": "pr_created", "pr_number": 42}),
    ({"execution": "completed", "deliveryDetail": {"status": "waiting_for_acceptance"}},
     {"status": "running"}),
    ({"execution": "completed", "deliveryDetail": {"status": "not_requested"}},
     {"status": "completed"}),
    ({"execution": "failed", "gate": {"reasons": ["tests failed"]}},
     {"status": "failed", "error": "tests failed"}),
    ({"execution": "cancelled"}, {"status": "cancelled"}),
])
def test_task_view_maps_to_fleet_status(worker, task, expected):
    update = worker.shakha_report(task)
    for k, v in expected.items():
        assert update[k] == v, (k, update)


def test_sync_reports_changes_once_and_cancels_on_request(worker):
    worker._test_api_reply = lambda m, p: (
        [{"id": "job-1", "external_ref": "task_A", "status": "running"}] if p.startswith("/worker/sync") else None)
    worker._set_task({"execution": "running"})
    worker.shakha_sync_once()
    worker.shakha_sync_once()
    statuses = [s for s in worker._sent if s[1] == "/job-1/status"]
    assert len(statuses) == 1, "an unchanged task is not re-reported"

    worker._test_api_reply = lambda m, p: (
        [{"id": "job-1", "external_ref": "task_A", "status": "cancelled"}] if p.startswith("/worker/sync") else None)
    worker.shakha_sync_once()
    cancel = [c for c in worker._calls() if c[:2] == ["task", "cancel"]]
    assert cancel == [["task", "cancel", "task_A", "--key", "sutra-cancel-job-1"]]

    worker._set_task({"execution": "cancelled"})
    worker.shakha_sync_once()
    assert len([c for c in worker._calls() if c[:2] == ["task", "cancel"]]) == 1, "no cancel once Shakha agrees"


def test_claimed_shakha_jobs_go_to_the_shakha_runner(worker, monkeypatch):
    called = []
    monkeypatch.setattr(worker, "start_shakha_job", lambda job: called.append("shakha") or 0)
    worker._test_api_reply = lambda m, p: {"id": "j", "runner": "shakha"} if p == "/claim" else None
    worker._run_one_job_inner()
    assert called == ["shakha"]


def test_shakha_ready_uses_status(worker):
    assert worker.shakha_ready() is True
    worker.SHAKHA_BIN = "/nonexistent"
    assert worker.shakha_ready() is False
