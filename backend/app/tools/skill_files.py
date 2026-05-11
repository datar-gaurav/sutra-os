"""Read accessory files (references/, scripts/, assets/) from a loaded skill.

Skills bodies frequently say "see references/X.md for details" — this tool
gives the agent the ability to fetch that content on demand instead of paying
the token cost on every turn.

Path traversal is blocked by the loader; this tool is a thin wrapper.
"""

from langchain_core.tools import tool

from app.skills.loader import read_skill_file as _read_skill_file


@tool
def read_skill_file(skill_slug: str, path: str) -> str:
    """Read a reference, script, or asset file from a skill's directory.

    Use this when a skill's body instructs you to consult an accessory file
    (e.g. "see references/sizing.md"). The file is read from disk and returned
    verbatim — no interpretation, no truncation.

    Args:
        skill_slug: The skill identifier (kebab-case, matches its directory name).
        path: Relative path within the skill, e.g. "references/sizing.md" or
            "assets/template.md". Absolute paths and `..` segments are rejected.
    """
    try:
        return _read_skill_file(skill_slug, path)
    except FileNotFoundError as e:
        return f"Error: file not found — {e}"
    except PermissionError as e:
        return f"Error: path not allowed — {e}"
    except Exception as e:
        return f"Error reading skill file: {e}"
