"""Registry parses every SKILL.md under backend/skills/ without error."""

from __future__ import annotations

from app.skills.registry import skill_registry, BUILTIN_SKILLS_DIR


def test_registry_loads_all_builtins():
    n = skill_registry.reload()
    assert n >= 19, f"expected at least 19 builtin skills, found {n}"


def test_every_builtin_has_a_load_when_description():
    skill_registry.reload()
    for m in skill_registry.all():
        d = m.description.lower()
        # Routing trigger should start with "load when"
        assert d.startswith("load when"), (
            f"{m.slug}: description must start with 'Load when…' — got {m.description!r}"
        )
        # And not be a wall of text
        assert len(m.description) <= 400, f"{m.slug}: description too long ({len(m.description)} chars)"


def test_slug_matches_directory_name():
    skill_registry.reload()
    for m in skill_registry.all():
        assert m.root.name == m.slug, f"slug/dir mismatch: {m.slug} vs {m.root.name}"


def test_index_contains_routing_fields_only():
    skill_registry.reload()
    idx = skill_registry.index()
    assert idx
    sample = idx[0]
    assert set(sample.keys()) == {"slug", "name", "description"}


def test_reference_files_are_discovered():
    skill_registry.reload()
    alpaca = skill_registry.get("alpaca-trading")
    assert alpaca is not None
    # References we shipped:
    assert "references/sizing.md" in alpaca.files
    assert "references/error-handling.md" in alpaca.files
    assert "assets/summary_template.md" in alpaca.files


def test_no_banner_in_bodies():
    """Bodies must not start with the old 'You have been equipped...' banner."""
    skill_registry.reload()
    for m in skill_registry.all():
        first_line = m.body.split("\n", 1)[0].lower()
        assert "you have been equipped" not in first_line, (
            f"{m.slug}: body still has the equipped-banner — strip it"
        )


def test_builtin_skills_dir_resolves_to_real_path():
    assert BUILTIN_SKILLS_DIR.is_dir()
