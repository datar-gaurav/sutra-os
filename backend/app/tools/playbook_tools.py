"""Playbook discovery and loading tools for browser automation."""

import logging
import os
import re
from pathlib import Path

import yaml
from langchain_core.tools import tool

from app.config import settings

logger = logging.getLogger(__name__)

PLAYBOOK_TOOL_IDS = {"list_playbooks", "load_playbook"}


def _get_playbooks_dir() -> str:
    """Resolve the playbooks directory to an absolute path."""
    playbooks_dir = getattr(settings, "playbooks_dir", "data/playbooks")
    if not os.path.isabs(playbooks_dir):
        # Relative to the backend directory
        playbooks_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            playbooks_dir,
        )
    return playbooks_dir


def _parse_playbook(filepath: str) -> dict | None:
    """Parse a playbook .md file and return its metadata + content."""
    try:
        with open(filepath, "r") as f:
            raw = f.read()
    except Exception:
        return None

    # Extract YAML frontmatter between --- delimiters
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw, re.DOTALL)
    if not match:
        return None

    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None

    if not isinstance(meta, dict) or "name" not in meta:
        return None

    return {
        "name": meta["name"],
        "description": meta.get("description", ""),
        "parameters": meta.get("parameters", []),
        "tags": meta.get("tags", []),
        "content": match.group(2).strip(),
        "source": filepath,
    }


def _discover_playbooks(tag: str | None = None) -> list[dict]:
    """Scan the playbooks directory for valid .md playbooks."""
    playbooks_dir = _get_playbooks_dir()
    results = []

    if not os.path.isdir(playbooks_dir):
        return results

    for filepath in sorted(Path(playbooks_dir).glob("*.md")):
        parsed = _parse_playbook(str(filepath))
        if parsed is None:
            continue
        if tag and tag.lower() not in [t.lower() for t in parsed.get("tags", [])]:
            continue
        results.append(parsed)

    return results


@tool
def list_playbooks(tag: str = "") -> str:
    """List available browser automation playbooks.

    Playbooks are reusable .md instruction files that define step-by-step
    browser tasks with configurable parameters.

    Args:
        tag: Optional tag to filter by (e.g., "login", "scraping"). Leave empty for all.
    """
    playbooks = _discover_playbooks(tag if tag else None)

    if not playbooks:
        if tag:
            return f"No playbooks found with tag '{tag}'."
        return (
            "No playbooks found. Create .md files in the playbooks directory "
            "or record a browser session with browser_record_start/stop."
        )

    lines = []
    for pb in playbooks:
        params_str = ""
        if pb["parameters"]:
            param_names = [
                p["name"] + ("*" if p.get("required") else "")
                for p in pb["parameters"]
            ]
            params_str = f" | Params: {', '.join(param_names)}"

        tags_str = ""
        if pb["tags"]:
            tags_str = f" | Tags: {', '.join(pb['tags'])}"

        lines.append(
            f"- **{pb['name']}**: {pb['description']}{params_str}{tags_str}"
        )

    return f"Available playbooks ({len(playbooks)}):\n\n" + "\n".join(lines)


@tool
def load_playbook(name: str, parameters: str = "{}") -> str:
    """Load a playbook by name and substitute parameters.

    Returns the full playbook instructions with ``{{param}}`` placeholders
    replaced by the provided values. Follow the returned instructions step
    by step using the browser tools.

    Args:
        name: The playbook name (case-insensitive).
        parameters: JSON string of parameter values, e.g. '{"username": "john", "password": "secret"}'.
    """
    import json

    playbooks = _discover_playbooks()
    match = None
    for pb in playbooks:
        if pb["name"].lower() == name.lower():
            match = pb
            break

    if match is None:
        available = ", ".join(pb["name"] for pb in playbooks) if playbooks else "(none)"
        return f"Playbook '{name}' not found. Available: {available}"

    # Parse parameters
    try:
        params = json.loads(parameters) if isinstance(parameters, str) else parameters
    except json.JSONDecodeError as e:
        return f"Invalid parameters JSON: {e}"

    # Validate required parameters
    missing = []
    for p in match.get("parameters", []):
        if p.get("required") and p["name"] not in params:
            # Check for default
            if "default" not in p:
                missing.append(p["name"])
            else:
                params[p["name"]] = p["default"]

    # Apply defaults for optional params not provided
    for p in match.get("parameters", []):
        if p["name"] not in params and "default" in p:
            params[p["name"]] = p["default"]

    if missing:
        return (
            f"Missing required parameters: {', '.join(missing)}\n"
            f"Expected: {json.dumps(match['parameters'], indent=2)}"
        )

    # Substitute {{param}} placeholders
    content = match["content"]
    for key, value in params.items():
        content = content.replace("{{" + key + "}}", str(value))

    # Warn about unsubstituted placeholders
    remaining = re.findall(r"\{\{(\w+)\}\}", content)
    warning = ""
    if remaining:
        warning = f"\n\nWARNING: Unsubstituted placeholders: {', '.join(remaining)}"

    return (
        f"# Playbook: {match['name']}\n\n"
        f"{match['description']}\n\n"
        f"{content}{warning}"
    )


def create_playbook_tools() -> list:
    """Return the playbook tools (no agent_id needed)."""
    return [list_playbooks, load_playbook]
