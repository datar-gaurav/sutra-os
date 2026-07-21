"""Photo Enhancement extension for Sutra OS.

Restores/enhances Apple Photos images **fully locally** on macOS using
CodeFormer (https://github.com/sczhou/CodeFormer) — face restoration plus
optional Real-ESRGAN background upscale. No cloud calls; images never leave
the device. Reserves nothing for a remote API — all inference is on-host.

Integrates in the same single-file style as ``alpaca_trading.py``
(``EXTENSION_MANIFEST`` + ``create_tools`` + ``test_connection``). All paths
are configured from the Integrations page via ``config_fields`` — nothing is
hardcoded. Export from Apple Photos and re-import are **manual** and
nondestructive; this extension only runs the enhancement step.

Two agent tools:
  - photo_enhance:        run one CodeFormer batch over the input folder,
                          with an agent/user-provided ``w`` fidelity dial.
  - photo_enhance_status: report whether the local CodeFormer env, weights,
                          and configured folders are present.

── One-time host setup (Apple Silicon, e.g. M4) ──────────────────────────────
CodeFormer's ``basicsr`` imports a torchvision module newer versions removed,
so pin torchvision:

    python3.10 -m venv ~/codeformer-env
    source ~/codeformer-env/bin/activate
    git clone https://github.com/sczhou/CodeFormer.git && cd CodeFormer
    pip install torch torchvision==0.16.2   # pin avoids the functional_tensor break
    pip install -r requirements.txt
    python basicsr/setup.py develop
    python scripts/download_pretrained_models.py facelib
    python scripts/download_pretrained_models.py CodeFormer

Then point this extension's config at ``~/codeformer-env/bin/python`` and the
cloned ``CodeFormer`` directory. MPS acceleration is inconsistent for some ops
and may fall back to CPU — fine for personal batches (dozens–hundreds).
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime

from langchain_core.tools import tool

EXTENSION_ID = "photo_enhancement"

EXTENSION_MANIFEST = {
    "id": EXTENSION_ID,
    "name": "Photo Enhancement",
    "description": (
        "Restore and enhance photos fully locally with CodeFormer (face "
        "restoration + background upscale). Export/re-import to Apple Photos "
        "stays manual; agents run the enhancement with a chosen fidelity dial."
    ),
    "icon": "image",
    "version": "0.1.0",
    "author": "Gaurav Datar",
    # Nothing secret — it's all local. Config-only extension.
    "credential_fields": [],
    "config_fields": [
        {
            "key": "input_dir",
            "label": "Input folder (exported originals)",
            "secret": False,
            "placeholder": "~/Pictures/photo-enhance/input",
        },
        {
            "key": "output_dir",
            "label": "Output folder (enhanced copies)",
            "secret": False,
            "placeholder": "~/Pictures/photo-enhance/output",
        },
        {
            "key": "python_bin",
            "label": "CodeFormer venv Python",
            "secret": False,
            "placeholder": "~/codeformer-env/bin/python",
        },
        {
            "key": "codeformer_dir",
            "label": "CodeFormer repo directory",
            "secret": False,
            "placeholder": "~/CodeFormer",
        },
        {
            "key": "device",
            "label": "Inference device (cpu or mps)",
            "secret": False,
            "placeholder": "cpu",
        },
    ],
    "tool_ids": [
        "photo_enhance",
        "photo_enhance_status",
    ],
    # Only writes to its own output folder; never touches the Photos library.
    "is_dangerous": False,
}

# ─── Defaults (all overridable via config_fields) ────────────────────────────
DEFAULT_DEVICE = "cpu"
DEFAULT_W = 0.7
SCRIPT_NAME = "inference_codeformer.py"
# CodeFormer batches on CPU can run for a while; cap so a wedged run can't hang
# the tool call forever.
BATCH_TIMEOUT_SECONDS = 3600
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic"}


# ─── Config plumbing ─────────────────────────────────────────────────────────
async def _get_config(agent_id: str) -> dict:
    """Fetch this extension's extra_config (agent-specific, else system-wide).

    Like the Smart Organizer and unlike ``get_extension_creds``, this does not
    require stored credentials — the Photo Enhancer has none — so it reads the
    Integration row directly.
    """
    from sqlalchemy import nullslast, select

    from app.db.session import async_session_factory
    from app.models.integration import Integration

    async with async_session_factory() as db:
        result = await db.execute(
            select(Integration)
            .where(Integration.type == EXTENSION_ID, Integration.is_active == True)  # noqa: E712
            .order_by(nullslast(Integration.agent_id.desc()))
        )
        rows = result.scalars().all()

    agent_specific = next((r for r in rows if r.agent_id == agent_id), None)
    system_wide = next((r for r in rows if r.agent_id is None), None)
    row = agent_specific or system_wide
    if not row:
        raise ValueError(
            f"No active '{EXTENSION_ID}' integration found. "
            f"Please configure it in Settings > Integrations."
        )
    return dict(row.extra_config or {})


def _expand(path: str) -> str:
    """Expand ``~`` and env vars; return '' unchanged."""
    return os.path.expanduser(os.path.expandvars(path)) if path else ""


def _resolve_config_paths(config: dict, input_dir: str = "", output_dir: str = "") -> dict:
    """Resolve the effective paths/device from config, with per-call overrides.

    Per-call ``input_dir`` / ``output_dir`` win over the UI-configured defaults;
    empty falls back to config.
    """
    return {
        "python_bin": _expand(config.get("python_bin") or ""),
        "codeformer_dir": _expand(config.get("codeformer_dir") or ""),
        "input_dir": _expand(input_dir or config.get("input_dir") or ""),
        "output_dir": _expand(output_dir or config.get("output_dir") or ""),
        "device": (config.get("device") or DEFAULT_DEVICE).strip(),
    }


def _build_command(
    python_bin: str,
    input_dir: str,
    output_dir: str,
    w: float,
    device: str,
    bg_upsample: bool,
    face_upsample: bool,
) -> list[str]:
    """Build the ``inference_codeformer.py`` argv (run with cwd=codeformer_dir)."""
    args = [
        python_bin,
        SCRIPT_NAME,
        "-w",
        str(w),
        "--input_path",
        input_dir,
        "--output_path",
        output_dir,
    ]
    if bg_upsample:
        args += ["--bg_upsampler", "realesrgan"]
    if face_upsample:
        args.append("--face_upsample")
    if device:
        args += ["--device", device]
    return args


def _count_results(output_dir: str) -> int:
    """Count enhanced images CodeFormer wrote.

    CodeFormer writes whole-image results under ``final_results/``; fall back to
    a recursive image count if that folder is absent.
    """
    final = os.path.join(output_dir, "final_results")
    scan_dir = final if os.path.isdir(final) else output_dir
    if not os.path.isdir(scan_dir):
        return 0
    count = 0
    for root, _dirs, files in os.walk(scan_dir):
        for f in files:
            if os.path.splitext(f)[1].lower() in _IMAGE_EXTS:
                count += 1
    return count


def _count_inputs(input_dir: str) -> int:
    if not os.path.isdir(input_dir):
        return 0
    return sum(1 for f in os.listdir(input_dir) if os.path.splitext(f)[1].lower() in _IMAGE_EXTS)


def create_tools(agent_id: str):
    @tool
    async def photo_enhance(
        w: float = DEFAULT_W,
        input_dir: str = "",
        output_dir: str = "",
        bg_upsample: bool = True,
        face_upsample: bool = True,
    ) -> str:
        """Enhance a folder of photos locally with CodeFormer (face restoration).

        Runs one batch over the input folder and writes enhanced copies to a
        new dated subfolder under the output folder. Nondestructive — the Apple
        Photos library is never touched; export the originals into the input
        folder and re-import the results yourself.

        Args:
            w: Fidelity dial, 0.0–1.0. Start at 0.7. Lower (~0.5) for rough or
               blurry faces (more reconstruction); higher (0.8–0.9) for
               already-decent photos (more faithful to the original).
            input_dir: Folder of exported originals. Empty = the folder
               configured on the Integrations page.
            output_dir: Destination root; a dated subfolder is created inside
               it. Empty = the configured folder.
            bg_upsample: Real-ESRGAN upscale the whole image, not just the face.
            face_upsample: Sharpen the restored face back into full resolution.
        """
        if not isinstance(w, (int, float)) or not (0.0 <= float(w) <= 1.0):
            return f"Invalid w={w!r}: must be a number between 0.0 and 1.0 (start at 0.7)."
        w = float(w)

        try:
            config = await _get_config(agent_id)
        except ValueError as e:
            return str(e)

        p = _resolve_config_paths(config, input_dir, output_dir)

        # Validate the local environment before spending time on a batch.
        if not p["python_bin"] or not os.path.isfile(p["python_bin"]):
            return (
                f"CodeFormer Python not found at '{p['python_bin']}'. "
                f"Set 'python_bin' in Settings > Integrations."
            )
        if not p["codeformer_dir"] or not os.path.isdir(p["codeformer_dir"]):
            return (
                f"CodeFormer directory not found at '{p['codeformer_dir']}'. "
                f"Set 'codeformer_dir' in Settings > Integrations."
            )
        script_path = os.path.join(p["codeformer_dir"], SCRIPT_NAME)
        if not os.path.isfile(script_path):
            return f"'{SCRIPT_NAME}' not found in '{p['codeformer_dir']}'."
        if not p["input_dir"] or not os.path.isdir(p["input_dir"]):
            return (
                f"Input folder not found at '{p['input_dir']}'. Export originals "
                f"from Apple Photos into it, or set 'input_dir' in Integrations."
            )
        if not p["output_dir"]:
            return "No output folder configured. Set 'output_dir' in Integrations."

        input_count = _count_inputs(p["input_dir"])
        if input_count == 0:
            return f"No images found in input folder '{p['input_dir']}'."

        dated_out = os.path.join(p["output_dir"], datetime.now().strftime("%Y-%m-%d_%H%M%S"))
        os.makedirs(dated_out, exist_ok=True)

        args = _build_command(
            p["python_bin"],
            p["input_dir"],
            dated_out,
            w,
            p["device"],
            bg_upsample,
            face_upsample,
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=p["codeformer_dir"],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=BATCH_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return (
                    f"CodeFormer timed out after {BATCH_TIMEOUT_SECONDS}s on "
                    f"{input_count} image(s). Partial results may be in '{dated_out}'."
                )
        except Exception as e:
            return f"Failed to launch CodeFormer: {e}"

        if proc.returncode != 0:
            err = (stderr or b"").decode("utf-8", "replace").strip()
            return (
                f"CodeFormer exited with code {proc.returncode}.\n"
                f"{err[-800:] if err else '(no stderr)'}"
            )

        produced = _count_results(dated_out)
        return (
            f"Enhanced {produced} of {input_count} image(s) at w={w} "
            f"(device={p['device']}, bg_upsample={bg_upsample}, "
            f"face_upsample={face_upsample}).\n"
            f"Output: {dated_out}\n"
            f"Review, then re-import into Apple Photos manually (File > Import)."
        )

    @tool
    async def photo_enhance_status() -> str:
        """Report whether the local CodeFormer environment and folders are ready.

        Checks the configured Python binary, CodeFormer directory + inference
        script, pretrained weights, and the input/output folders. Use this
        before photo_enhance to confirm setup.
        """
        try:
            config = await _get_config(agent_id)
        except ValueError as e:
            return str(e)

        p = _resolve_config_paths(config)
        script_path = os.path.join(p["codeformer_dir"], SCRIPT_NAME) if p["codeformer_dir"] else ""
        weights_dir = os.path.join(p["codeformer_dir"], "weights") if p["codeformer_dir"] else ""
        cf_weight = os.path.join(weights_dir, "CodeFormer") if weights_dir else ""

        def _mark(ok: bool) -> str:
            return "OK " if ok else "MISSING"

        python_ok = bool(p["python_bin"]) and os.path.isfile(p["python_bin"])
        dir_ok = bool(p["codeformer_dir"]) and os.path.isdir(p["codeformer_dir"])
        script_ok = bool(script_path) and os.path.isfile(script_path)
        weights_ok = bool(cf_weight) and os.path.isdir(cf_weight)
        input_ok = bool(p["input_dir"]) and os.path.isdir(p["input_dir"])
        output_ok = bool(p["output_dir"])

        input_count = _count_inputs(p["input_dir"]) if input_ok else 0
        ready = python_ok and dir_ok and script_ok and weights_ok and input_ok and output_ok

        lines = [
            f"Photo Enhancement — {'READY' if ready else 'NOT READY'}",
            f"  [{_mark(python_ok)}] python_bin: {p['python_bin'] or '(unset)'}",
            f"  [{_mark(dir_ok)}] codeformer_dir: {p['codeformer_dir'] or '(unset)'}",
            f"  [{_mark(script_ok)}] {SCRIPT_NAME}",
            f"  [{_mark(weights_ok)}] pretrained weights (weights/CodeFormer)",
            f"  [{_mark(input_ok)}] input_dir: {p['input_dir'] or '(unset)'}"
            + (f" — {input_count} image(s)" if input_ok else ""),
            f"  [{_mark(output_ok)}] output_dir: {p['output_dir'] or '(unset)'}",
            f"  device: {p['device']}",
        ]
        return "\n".join(lines)

    return [photo_enhance, photo_enhance_status]


def test_connection(creds: dict, config: dict) -> dict:
    """Verify the local CodeFormer setup from the Integrations page.

    Config-only extension — ``creds`` is unused. Checks that the Python binary,
    CodeFormer directory + inference script, and pretrained weights exist.
    """
    python_bin = _expand(config.get("python_bin") or "")
    codeformer_dir = _expand(config.get("codeformer_dir") or "")
    script_path = os.path.join(codeformer_dir, SCRIPT_NAME) if codeformer_dir else ""
    cf_weight = os.path.join(codeformer_dir, "weights", "CodeFormer") if codeformer_dir else ""

    problems = []
    if not python_bin or not os.path.isfile(python_bin):
        problems.append(f"python_bin missing ('{python_bin or 'unset'}')")
    if not codeformer_dir or not os.path.isdir(codeformer_dir):
        problems.append(f"codeformer_dir missing ('{codeformer_dir or 'unset'}')")
    elif not os.path.isfile(script_path):
        problems.append(f"{SCRIPT_NAME} not found in codeformer_dir")
    if codeformer_dir and not os.path.isdir(cf_weight):
        problems.append("pretrained weights not found (run download_pretrained_models.py)")

    if problems:
        return {"ok": False, "detail": "Setup incomplete — " + "; ".join(problems)}
    return {
        "ok": True,
        "detail": f"CodeFormer ready at {codeformer_dir} (python: {python_bin})",
    }
