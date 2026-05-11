"""Skills package — filesystem-backed skill manifests, routing, and sync.

A skill is a directory under either `backend/skills/` (builtins, shipped with
the repo) or `<custom_skills_dir>` (user-authored, writable volume) containing
a `SKILL.md` with YAML frontmatter + body, plus optional `references/`,
`scripts/`, and `assets/` subdirectories.

Public API:
    skill_registry          — singleton SkillRegistry
    SkillManifest           — frontmatter + body, in-memory
    LoadedSkill             — interpolated body + tools ready to inject per turn
    load_skill_for_turn(slug, overrides) -> LoadedSkill
    read_skill_file(slug, rel_path) -> str   (path-traversal-safe)
"""

from app.skills.registry import SkillManifest, SkillRegistry, skill_registry
from app.skills.loader import LoadedSkill, load_skill_for_turn, read_skill_file
from app.skills.router import (
    AttachedSkill,
    RoutingDecision,
    SkillRouter,
    parse_trigger_embedding,
    skill_router,
)

__all__ = [
    "SkillManifest",
    "SkillRegistry",
    "skill_registry",
    "LoadedSkill",
    "load_skill_for_turn",
    "read_skill_file",
    "AttachedSkill",
    "RoutingDecision",
    "SkillRouter",
    "skill_router",
    "parse_trigger_embedding",
]
