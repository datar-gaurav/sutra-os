"""Loader — body interpolation + path-traversal-safe file reads."""

from __future__ import annotations

import pytest

from app.skills.loader import load_skill_for_turn, read_skill_file
from app.skills.registry import skill_registry


def setup_module(_):
    skill_registry.reload()


def test_load_skill_for_turn_resolves_placeholders_from_defaults():
    ls = load_skill_for_turn("alpaca-trading", overrides=None)
    assert ls is not None
    # `risk_pct` has a default in the config_schema; should be interpolated
    assert "{risk_pct}" not in ls.body
    assert "0.05" in ls.body


def test_load_skill_for_turn_overrides_beat_defaults():
    ls = load_skill_for_turn("sql-query", overrides={"dialect": "snowflake"})
    assert ls is not None
    assert "snowflake" in ls.body
    assert "postgresql" not in ls.body or "Dialect: snowflake" in ls.body


def test_load_skill_for_turn_unknown_slug_returns_none():
    assert load_skill_for_turn("does-not-exist") is None


def test_read_skill_file_returns_content():
    contents = read_skill_file("alpaca-trading", "references/sizing.md")
    assert "Position Sizing" in contents
    assert "risk_per_share" in contents


def test_read_skill_file_blocks_path_traversal():
    with pytest.raises((PermissionError, FileNotFoundError)):
        read_skill_file("alpaca-trading", "../../../../etc/passwd")


def test_read_skill_file_blocks_absolute_path():
    with pytest.raises((PermissionError, FileNotFoundError, ValueError)):
        read_skill_file("alpaca-trading", "/etc/passwd")


def test_read_skill_file_unknown_skill():
    with pytest.raises(FileNotFoundError):
        read_skill_file("nope", "references/anything.md")


def test_read_skill_file_unknown_path_in_existing_skill():
    with pytest.raises(FileNotFoundError):
        read_skill_file("alpaca-trading", "references/does_not_exist.md")
