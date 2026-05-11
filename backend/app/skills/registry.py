"""SkillRegistry — scans filesystem for SKILL.md manifests and indexes them.

Scanned roots:
  1. backend/skills/   — builtins, committed
  2. settings.custom_skills_dir  — custom skills, writable volume

A malformed SKILL.md is logged and skipped, never crashes startup.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import frontmatter

logger = logging.getLogger(__name__)

# backend/app/skills/registry.py  →  backend/
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
BUILTIN_SKILLS_DIR = _BACKEND_ROOT / "skills"


@dataclass
class SkillManifest:
    """Parsed SKILL.md — frontmatter + body, with file paths resolved."""

    slug: str
    name: str
    description: str                # used as the routing trigger
    body: str                       # SKILL.md body (after frontmatter)
    icon: str | None
    color: str | None
    version: str
    category: str
    tools: list[str]
    config_schema: dict | None
    source: Literal["builtin", "custom"]
    root: Path                      # absolute path to the skill directory
    files: dict[str, Path] = field(default_factory=dict)  # rel_path → absolute path

    def has_files(self) -> bool:
        return bool(self.files)


class SkillRegistry:
    """In-memory index of all skills found on disk. Rebuilt on reload()."""

    def __init__(self) -> None:
        self._by_slug: dict[str, SkillManifest] = {}

    def reload(self, custom_skills_dir: Path | str | None = None) -> int:
        """Rescan disk. Returns the count of skills loaded."""
        self._by_slug.clear()

        roots: list[tuple[Path, Literal["builtin", "custom"]]] = [
            (BUILTIN_SKILLS_DIR, "builtin"),
        ]
        if custom_skills_dir:
            custom_path = Path(custom_skills_dir)
            if custom_path.exists():
                roots.append((custom_path, "custom"))

        for root, source in roots:
            if not root.is_dir():
                logger.debug(f"Skills root not found, skipping: {root}")
                continue
            for skill_dir in sorted(root.iterdir()):
                if not skill_dir.is_dir():
                    continue
                skill_md = skill_dir / "SKILL.md"
                if not skill_md.is_file():
                    continue
                try:
                    manifest = self._parse(skill_dir, skill_md, source)
                except Exception as e:
                    logger.warning(f"Skipping skill at {skill_dir}: {e}")
                    continue
                if manifest.slug in self._by_slug:
                    # Custom overrides builtin if slugs collide
                    if source == "builtin":
                        logger.debug(f"Builtin '{manifest.slug}' overridden by custom")
                        continue
                self._by_slug[manifest.slug] = manifest

        logger.info(f"SkillRegistry: loaded {len(self._by_slug)} skills")
        return len(self._by_slug)

    def _parse(
        self,
        skill_dir: Path,
        skill_md: Path,
        source: Literal["builtin", "custom"],
    ) -> SkillManifest:
        post = frontmatter.load(skill_md)
        meta = post.metadata
        if not isinstance(meta, dict):
            raise ValueError("frontmatter must be a YAML mapping")

        slug = meta.get("slug") or skill_dir.name
        if not isinstance(slug, str) or not slug:
            raise ValueError("missing or invalid slug")
        if slug != skill_dir.name:
            raise ValueError(f"slug '{slug}' must match directory name '{skill_dir.name}'")

        name = meta.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("missing 'name'")

        description = meta.get("description") or ""
        if not isinstance(description, str):
            raise ValueError("'description' must be a string")
        description = description.strip()

        tools = meta.get("tools") or []
        if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
            raise ValueError("'tools' must be a list of strings")

        config_schema = meta.get("config_schema")
        if config_schema is not None and not isinstance(config_schema, dict):
            raise ValueError("'config_schema' must be a mapping or null")

        files: dict[str, Path] = {}
        for sub in ("references", "scripts", "assets"):
            sub_dir = skill_dir / sub
            if not sub_dir.is_dir():
                continue
            for f in sub_dir.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(skill_dir).as_posix()
                    files[rel] = f.resolve()

        return SkillManifest(
            slug=slug,
            name=name,
            description=description,
            body=post.content.strip(),
            icon=meta.get("icon"),
            color=meta.get("color"),
            version=str(meta.get("version") or "1.0.0"),
            category=str(meta.get("category") or "general"),
            tools=tools,
            config_schema=config_schema,
            source=source,
            root=skill_dir.resolve(),
            files=files,
        )

    def get(self, slug: str) -> SkillManifest | None:
        return self._by_slug.get(slug)

    def all(self) -> list[SkillManifest]:
        return list(self._by_slug.values())

    def index(self) -> list[dict]:
        """Lightweight metadata for routing — slug + name + description only."""
        return [
            {"slug": m.slug, "name": m.name, "description": m.description}
            for m in self._by_slug.values()
        ]


# Module singleton
skill_registry = SkillRegistry()
