"""Photo Enhancement extension — command building, path resolution, tools."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest

from app.tools.extensions import photo_enhancement as pe


# ─── Pure helpers ────────────────────────────────────────────────────────────


def test_build_command_all_flags():
    args = pe._build_command(
        "/venv/python", "/in", "/out", 0.7, "cpu", bg_upsample=True, face_upsample=True
    )
    assert args[:8] == [
        "/venv/python",
        "inference_codeformer.py",
        "-w",
        "0.7",
        "--input_path",
        "/in",
        "--output_path",
        "/out",
    ]
    assert "--bg_upsampler" in args and args[args.index("--bg_upsampler") + 1] == "realesrgan"
    assert "--face_upsample" in args
    assert args[args.index("--device") + 1] == "cpu"


def test_build_command_omits_optional_flags():
    args = pe._build_command(
        "/venv/python", "/in", "/out", 0.5, "", bg_upsample=False, face_upsample=False
    )
    assert "--bg_upsampler" not in args
    assert "--face_upsample" not in args
    assert "--device" not in args  # empty device is not passed
    assert args[args.index("-w") + 1] == "0.5"


def test_resolve_config_paths_override_wins():
    config = {
        "input_dir": "/cfg/in",
        "output_dir": "/cfg/out",
        "python_bin": "/cfg/py",
        "codeformer_dir": "/cfg/cf",
        "device": "mps",
    }
    p = pe._resolve_config_paths(config, input_dir="/call/in")
    assert p["input_dir"] == "/call/in"  # per-call override wins
    assert p["output_dir"] == "/cfg/out"  # falls back to config
    assert p["device"] == "mps"


def test_resolve_config_paths_defaults_device():
    p = pe._resolve_config_paths({})
    assert p["device"] == pe.DEFAULT_DEVICE


def test_count_results_prefers_final_results(tmp_path):
    (tmp_path / "final_results").mkdir()
    (tmp_path / "final_results" / "a.png").write_bytes(b"x")
    (tmp_path / "final_results" / "b.jpg").write_bytes(b"x")
    (tmp_path / "cropped_faces").mkdir()
    (tmp_path / "cropped_faces" / "c.png").write_bytes(b"x")  # must NOT be counted
    assert pe._count_results(str(tmp_path)) == 2


def test_count_inputs_only_images(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"x")
    (tmp_path / "b.HEIC").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("x")
    assert pe._count_inputs(str(tmp_path)) == 2


# ─── Tool: photo_enhance ─────────────────────────────────────────────────────


def _tool(name: str):
    tools = {t.name: t for t in pe.create_tools("agent-1")}
    return tools[name]


@pytest.mark.parametrize("bad_w", [-0.1, 1.5])
async def test_photo_enhance_rejects_out_of_range_w(bad_w):
    # Numeric-but-out-of-range passes pydantic schema and hits our own guard.
    with patch.object(pe, "_get_config", new=AsyncMock()) as cfg:
        result = await _tool("photo_enhance").ainvoke({"w": bad_w})
    assert "Invalid w" in result
    cfg.assert_not_called()  # bails before touching config


@pytest.mark.parametrize("bad_w", ["hi", None])
async def test_photo_enhance_non_numeric_w_rejected_by_schema(bad_w):
    # Non-numeric w is rejected by the @tool pydantic schema before our code runs.
    from pydantic import ValidationError

    with patch.object(pe, "_get_config", new=AsyncMock()) as cfg:
        with pytest.raises(ValidationError):
            await _tool("photo_enhance").ainvoke({"w": bad_w})
    cfg.assert_not_called()


async def test_photo_enhance_missing_input_dir(tmp_path):
    # Valid python/codeformer but no input dir.
    py = tmp_path / "python"
    py.write_text("")
    cf = tmp_path / "CodeFormer"
    cf.mkdir()
    (cf / pe.SCRIPT_NAME).write_text("")
    config = {
        "python_bin": str(py),
        "codeformer_dir": str(cf),
        "input_dir": str(tmp_path / "nope"),
        "output_dir": str(tmp_path / "out"),
    }
    with patch.object(pe, "_get_config", new=AsyncMock(return_value=config)):
        result = await _tool("photo_enhance").ainvoke({"w": 0.7})
    assert "Input folder not found" in result


async def _make_env(tmp_path, with_input=True):
    py = tmp_path / "python"
    py.write_text("")
    cf = tmp_path / "CodeFormer"
    cf.mkdir()
    (cf / pe.SCRIPT_NAME).write_text("")
    (cf / "weights" / "CodeFormer").mkdir(parents=True)
    inp = tmp_path / "input"
    inp.mkdir()
    if with_input:
        (inp / "photo.jpg").write_bytes(b"x")
    out = tmp_path / "output"
    return {
        "python_bin": str(py),
        "codeformer_dir": str(cf),
        "input_dir": str(inp),
        "output_dir": str(out),
        "device": "cpu",
    }


async def test_photo_enhance_runs_and_reports(tmp_path):
    config = await _make_env(tmp_path)

    captured = {}

    async def fake_communicate():
        return (b"done", b"")

    class FakeProc:
        returncode = 0

        async def communicate(self):
            return await fake_communicate()

    async def fake_exec(*args, **kwargs):
        captured["args"] = list(args)
        captured["cwd"] = kwargs.get("cwd")
        # Simulate CodeFormer writing one final result into the dated output.
        out_path = args[args.index("--output_path") + 1]
        os.makedirs(os.path.join(out_path, "final_results"), exist_ok=True)
        open(os.path.join(out_path, "final_results", "photo.png"), "wb").close()
        return FakeProc()

    with (
        patch.object(pe, "_get_config", new=AsyncMock(return_value=config)),
        patch("asyncio.create_subprocess_exec", new=fake_exec),
    ):
        result = await _tool("photo_enhance").ainvoke(
            {"w": 0.55, "bg_upsample": True, "face_upsample": False}
        )

    # Command was built correctly and run in the CodeFormer dir.
    assert captured["cwd"] == config["codeformer_dir"]
    assert captured["args"][:4] == [config["python_bin"], pe.SCRIPT_NAME, "-w", "0.55"]
    assert "--bg_upsampler" in captured["args"]
    assert "--face_upsample" not in captured["args"]
    # Output went into a dated subfolder under output_dir, not output_dir itself.
    out_arg = captured["args"][captured["args"].index("--output_path") + 1]
    assert out_arg.startswith(config["output_dir"] + os.sep)
    # Summary reflects the result.
    assert "Enhanced 1 of 1 image(s) at w=0.55" in result


async def test_photo_enhance_nonzero_exit_surfaces_stderr(tmp_path):
    config = await _make_env(tmp_path)

    class FakeProc:
        returncode = 2

        async def communicate(self):
            return (b"", b"CUDA not available: boom")

    async def fake_exec(*args, **kwargs):
        out_path = args[args.index("--output_path") + 1]
        os.makedirs(out_path, exist_ok=True)
        return FakeProc()

    with (
        patch.object(pe, "_get_config", new=AsyncMock(return_value=config)),
        patch("asyncio.create_subprocess_exec", new=fake_exec),
    ):
        result = await _tool("photo_enhance").ainvoke({"w": 0.7})
    assert "exited with code 2" in result
    assert "boom" in result


async def test_photo_enhance_empty_input_folder(tmp_path):
    config = await _make_env(tmp_path, with_input=False)
    with patch.object(pe, "_get_config", new=AsyncMock(return_value=config)):
        result = await _tool("photo_enhance").ainvoke({"w": 0.7})
    assert "No images found" in result


# ─── Tool: photo_enhance_status + test_connection ────────────────────────────


async def test_status_reports_ready(tmp_path):
    config = await _make_env(tmp_path)
    with patch.object(pe, "_get_config", new=AsyncMock(return_value=config)):
        result = await _tool("photo_enhance_status").ainvoke({})
    assert "READY" in result and "NOT READY" not in result
    assert "1 image(s)" in result


async def test_status_reports_not_ready_when_weights_missing(tmp_path):
    config = await _make_env(tmp_path)
    # Remove weights.
    import shutil

    shutil.rmtree(os.path.join(config["codeformer_dir"], "weights"))
    with patch.object(pe, "_get_config", new=AsyncMock(return_value=config)):
        result = await _tool("photo_enhance_status").ainvoke({})
    assert "NOT READY" in result


def test_test_connection_ok(tmp_path):
    cf = tmp_path / "CodeFormer"
    (cf / "weights" / "CodeFormer").mkdir(parents=True)
    (cf / pe.SCRIPT_NAME).write_text("")
    py = tmp_path / "python"
    py.write_text("")
    res = pe.test_connection({}, {"python_bin": str(py), "codeformer_dir": str(cf)})
    assert res["ok"] is True


def test_test_connection_reports_problems():
    res = pe.test_connection({}, {"python_bin": "/nope/py", "codeformer_dir": "/nope/cf"})
    assert res["ok"] is False
    assert "python_bin missing" in res["detail"]
    assert "codeformer_dir missing" in res["detail"]


# ─── Manifest sanity ─────────────────────────────────────────────────────────


def test_manifest_is_config_only():
    m = pe.EXTENSION_MANIFEST
    assert m["id"] == "photo_enhancement"
    assert m["credential_fields"] == []  # nothing secret; all local
    assert set(m["tool_ids"]) == {"photo_enhance", "photo_enhance_status"}
    keys = {f["key"] for f in m["config_fields"]}
    assert {"input_dir", "output_dir", "python_bin", "codeformer_dir", "device"} <= keys
