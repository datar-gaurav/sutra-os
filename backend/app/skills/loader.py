"""Loader — interpolate skill bodies for a turn, read skill files safely."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.skills.registry import SkillManifest, skill_registry

logger = logging.getLogger(__name__)


@dataclass
class LoadedSkill:
    """A skill rendered for a specific turn — body interpolated, tools listed."""

    slug: str
    name: str
    body: str
    tools: list[str]
    has_files: bool


def _interpolate(body: str, overrides: dict | None) -> str:
    """Replace {param} placeholders using overrides, plus a few defaults from config_schema.

    Unknown placeholders are left in place (not an error) — they're often part
    of code examples, not template params.
    """
    if not overrides:
        return body
    try:
        return body.format_map(_SafeDict(overrides))
    except (ValueError, IndexError) as e:
        logger.debug(f"body interpolation skipped: {e}")
        return body


class _SafeDict(dict):
    """A dict that leaves unknown {keys} alone instead of raising KeyError."""

    def __missing__(self, key):
        return "{" + key + "}"


def load_skill_for_turn(slug: str, overrides: dict | None = None) -> LoadedSkill | None:
    """Look up a skill by slug and return a LoadedSkill ready for prompt assembly."""
    manifest: SkillManifest | None = skill_registry.get(slug)
    if manifest is None:
        return None

    merged: dict = {}
    if manifest.config_schema:
        for k, prop in (manifest.config_schema.get("properties") or {}).items():
            if isinstance(prop, dict) and "default" in prop:
                merged[k] = prop["default"]
    if overrides:
        merged.update(overrides)

    body = _interpolate(manifest.body, merged)
    return LoadedSkill(
        slug=manifest.slug,
        name=manifest.name,
        body=body,
        tools=list(manifest.tools),
        has_files=manifest.has_files(),
    )


def read_skill_file(slug: str, rel_path: str) -> str:
    """Read one file under a skill's directory. Path-traversal-safe."""
    manifest = skill_registry.get(slug)
    if manifest is None:
        raise FileNotFoundError(f"Unknown skill: {slug}")

    # Resolve, then verify the target stays within the skill root.
    try:
        target = (manifest.root / rel_path).resolve(strict=True)
    except FileNotFoundError:
        raise FileNotFoundError(f"{slug}:{rel_path}")
    try:
        target.relative_to(manifest.root)
    except ValueError:
        raise PermissionError(f"Path escapes skill root: {rel_path}")
    if not target.is_file():
        raise FileNotFoundError(f"{slug}:{rel_path} is not a file")
    return target.read_text()
