"""GitHub extended integration tools — list issues, get file contents, search code.

These tools use the stored Integration credential and are distinct from the existing
github_tools.py (which uses a fixed env-var token for issue/PR creation).
"""

from __future__ import annotations

import json
import logging
from base64 import b64decode

import httpx
from langchain_core.tools import tool

from app.core.vault import decrypt_secret

logger = logging.getLogger(__name__)

GITHUB_INTEGRATION_TOOL_IDS = {"github_list_issues", "github_get_file", "github_search_code"}

_GH_API = "https://api.github.com"


async def _get_github_creds(agent_id: str) -> tuple[dict, dict]:
    from app.db.session import async_session_factory
    from app.models.integration import Integration
    from sqlalchemy import select, nullslast

    async with async_session_factory() as db:
        result = await db.execute(
            select(Integration)
            .where(Integration.type == "github", Integration.is_active == True)
            .order_by(nullslast(Integration.agent_id.desc()))
        )
        rows = result.scalars().all()

    agent_specific = next((r for r in rows if r.agent_id == agent_id), None)
    system_wide = next((r for r in rows if r.agent_id is None), None)
    row = agent_specific or system_wide
    if not row or not row.credentials_enc:
        raise ValueError("No active GitHub integration found")
    creds = json.loads(decrypt_secret(row.credentials_enc))
    return creds, row.extra_config or {}


def create_github_integration_tools(agent_id: str):
    @tool
    async def github_list_issues(
        repo: str = "",
        state: str = "open",
        labels: str = "",
        limit: int = 20,
    ) -> str:
        """List GitHub issues for a repository.

        Args:
            repo: Repository in 'owner/repo' format. Falls back to integration default.
            state: 'open', 'closed', or 'all'.
            labels: Comma-separated label names to filter by.
            limit: Maximum issues to return.
        """
        creds, cfg = await _get_github_creds(agent_id)
        repository = repo or cfg.get("default_repo", "")
        if not repository:
            raise ValueError("repo is required (or set default_repo in integration config)")

        params: dict = {"state": state, "per_page": min(limit, 100)}
        if labels:
            params["labels"] = labels

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_GH_API}/repos/{repository}/issues",
                headers={
                    "Authorization": f"token {creds['token']}",
                    "Accept": "application/vnd.github+json",
                },
                params=params,
            )
            resp.raise_for_status()
        issues = resp.json()
        lines = []
        for i in issues:
            if "pull_request" in i:
                continue  # Skip PRs
            labels_str = ", ".join(lbl["name"] for lbl in i.get("labels", []))
            assignee = (i.get("assignee") or {}).get("login", "unassigned")
            lines.append(
                f"#{i['number']} [{i['state']}] {i['title']} | {assignee}"
                + (f" | {labels_str}" if labels_str else "")
            )
        return "\n".join(lines) if lines else "No issues found."

    @tool
    async def github_get_file(
        path: str,
        repo: str = "",
        ref: str = "HEAD",
    ) -> str:
        """Get the contents of a file from a GitHub repository.

        Args:
            path: File path within the repository (e.g. 'src/main.py').
            repo: Repository in 'owner/repo' format. Falls back to integration default.
            ref: Git ref (branch, tag, or commit SHA). Default is HEAD.
        """
        creds, cfg = await _get_github_creds(agent_id)
        repository = repo or cfg.get("default_repo", "")
        if not repository:
            raise ValueError("repo is required (or set default_repo in integration config)")

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_GH_API}/repos/{repository}/contents/{path}",
                headers={
                    "Authorization": f"token {creds['token']}",
                    "Accept": "application/vnd.github+json",
                },
                params={"ref": ref},
            )
            resp.raise_for_status()
        data = resp.json()
        if data.get("encoding") == "base64":
            content = b64decode(data["content"]).decode("utf-8", errors="replace")
        else:
            content = data.get("content", "")
        size = data.get("size", 0)
        return f"# {path} ({size} bytes)\n\n{content}"

    @tool
    async def github_search_code(
        query: str,
        repo: str = "",
        limit: int = 10,
    ) -> str:
        """Search code in a GitHub repository.

        Args:
            query: Search query string (GitHub code search syntax).
            repo: Restrict search to 'owner/repo'. Falls back to integration default.
            limit: Maximum results to return.
        """
        creds, cfg = await _get_github_creds(agent_id)
        repository = repo or cfg.get("default_repo", "")

        search_query = query
        if repository:
            search_query += f" repo:{repository}"

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_GH_API}/search/code",
                headers={
                    "Authorization": f"token {creds['token']}",
                    "Accept": "application/vnd.github+json",
                },
                params={"q": search_query, "per_page": min(limit, 30)},
            )
            resp.raise_for_status()
        items = resp.json().get("items", [])
        lines = []
        for item in items:
            lines.append(f"{item['path']} — {item['repository']['full_name']} (sha: {item['sha'][:7]})")
        return "\n".join(lines) if lines else "No results found."

    return [github_list_issues, github_get_file, github_search_code]
