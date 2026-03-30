"""External tool extensions — auto-discovered from Python files in this directory.

Each extension file must define:
  EXTENSION_MANIFEST: dict  — metadata (id, name, description, credential_fields, config_fields, tool_ids)
  create_tools(agent_id: str) -> list[BaseTool]  — factory returning LangChain tools
"""

from __future__ import annotations

import importlib.util
import logging
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

logger = logging.getLogger(__name__)

_EXTENSIONS_DIR = Path(__file__).parent

_REQUIRED_MANIFEST_KEYS = {"id", "name", "description", "credential_fields", "config_fields", "tool_ids"}


@dataclass
class ExtensionInfo:
    manifest: dict[str, Any]
    module: ModuleType
    create_tools: Callable
    tool_ids: set[str] = field(default_factory=set)


_EXTENSION_REGISTRY: dict[str, ExtensionInfo] = {}


def _load_extension_module(filepath: Path) -> ModuleType | None:
    """Import a single extension file using importlib."""
    module_name = f"sutra_ext_{filepath.stem}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        if spec is None or spec.loader is None:
            logger.warning("Cannot create module spec for extension: %s", filepath.name)
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        logger.exception("Failed to load extension file: %s", filepath.name)
        return None


def _validate_manifest(manifest: dict, filename: str) -> list[str]:
    """Validate an extension manifest. Returns list of error messages (empty = valid)."""
    errors = []
    missing = _REQUIRED_MANIFEST_KEYS - set(manifest.keys())
    if missing:
        errors.append(f"Missing required keys: {missing}")
    if not isinstance(manifest.get("tool_ids"), list):
        errors.append("tool_ids must be a list of strings")
    if not isinstance(manifest.get("credential_fields"), list):
        errors.append("credential_fields must be a list")
    if not isinstance(manifest.get("config_fields"), list):
        errors.append("config_fields must be a list")
    if not isinstance(manifest.get("id"), str) or not manifest.get("id"):
        errors.append("id must be a non-empty string")
    return errors


def discover_extensions(force_reload: bool = False) -> dict[str, list[str]]:
    """Scan the extensions directory and register valid extensions.

    Returns a dict of {filename: [errors]} for files that failed validation.
    Files that loaded successfully will not appear in the result.
    """
    from app.models.integration import INTEGRATION_TYPES

    if not force_reload and _EXTENSION_REGISTRY:
        return {}

    # Clear existing extension entries from INTEGRATION_TYPES
    for ext_id in list(_EXTENSION_REGISTRY.keys()):
        INTEGRATION_TYPES.pop(ext_id, None)
    _EXTENSION_REGISTRY.clear()

    errors_by_file: dict[str, list[str]] = {}

    for filepath in sorted(_EXTENSIONS_DIR.glob("*.py")):
        if filepath.name.startswith("_") or filepath.name == "__init__.py":
            continue

        module = _load_extension_module(filepath)
        if module is None:
            errors_by_file[filepath.name] = ["Failed to import module (check logs for traceback)"]
            continue

        manifest = getattr(module, "EXTENSION_MANIFEST", None)
        if manifest is None:
            errors_by_file[filepath.name] = ["No EXTENSION_MANIFEST found"]
            continue

        validation_errors = _validate_manifest(manifest, filepath.name)
        if validation_errors:
            errors_by_file[filepath.name] = validation_errors
            continue

        factory = getattr(module, "create_tools", None)
        if not callable(factory):
            errors_by_file[filepath.name] = ["No callable create_tools(agent_id) found"]
            continue

        ext_id = manifest["id"]

        # Check for ID collisions with built-in integration types
        if ext_id in INTEGRATION_TYPES and not INTEGRATION_TYPES[ext_id].get("is_extension"):
            errors_by_file[filepath.name] = [
                f"Extension ID '{ext_id}' conflicts with a built-in integration type"
            ]
            continue

        ext_info = ExtensionInfo(
            manifest=manifest,
            module=module,
            create_tools=factory,
            tool_ids=set(manifest["tool_ids"]),
        )
        _EXTENSION_REGISTRY[ext_id] = ext_info

        # Inject into INTEGRATION_TYPES so existing /api/integrations/types returns it
        INTEGRATION_TYPES[ext_id] = {
            "name": manifest["name"],
            "description": manifest["description"],
            "icon": manifest.get("icon", "puzzle"),
            "credential_fields": manifest["credential_fields"],
            "config_fields": manifest["config_fields"],
            "tool_ids": manifest["tool_ids"],
            "is_extension": True,
            "version": manifest.get("version", ""),
            "author": manifest.get("author", ""),
        }

        logger.info(
            "Loaded extension '%s' (%s) with %d tools from %s",
            manifest["name"],
            ext_id,
            len(manifest["tool_ids"]),
            filepath.name,
        )

    if _EXTENSION_REGISTRY:
        logger.info("Extension discovery complete: %d extensions loaded", len(_EXTENSION_REGISTRY))

    return errors_by_file


def get_extension_registry() -> dict[str, ExtensionInfo]:
    """Return the current extension registry."""
    return _EXTENSION_REGISTRY


def get_extension_tool_catalog() -> list[dict]:
    """Generate TOOL_CATALOG entries for all loaded extensions."""
    catalog = []
    is_dangerous_default = False
    for ext_id, ext_info in _EXTENSION_REGISTRY.items():
        is_dangerous_default = ext_info.manifest.get("is_dangerous", False)
        for tool_id in ext_info.manifest["tool_ids"]:
            catalog.append({
                "id": tool_id,
                "name": tool_id.replace("_", " ").title(),
                "description": f"[{ext_info.manifest['name']}] {ext_info.manifest['description']}",
                "category": "extensions",
                "is_dangerous": is_dangerous_default,
            })
    return catalog


def get_all_extension_tool_ids() -> set[str]:
    """Return a set of all tool IDs from loaded extensions."""
    ids: set[str] = set()
    for ext_info in _EXTENSION_REGISTRY.values():
        ids |= ext_info.tool_ids
    return ids
