"""GitLab integration tools — create issues and merge requests."""

from __future__ import annotations

import json
import logging
from urllib.parse import quote

import httpx
from langchain_core.tools import tool

from app.core.vault import decrypt_secret

logger = logging.getLogger(__name__)

GITLAB_TOOL_IDS = {"gitlab_create_issue", "gitlab_list_issues", "gitlab_create_mr"}


async def _get_gitlab_creds(agent_id: str) -> tuple[dict, dict]:
    from app.db.session import async_session_factory
    from app.models.integration import Integration
    from sqlalchemy import select, nullslast

    async with async_session_factory() as db:
        result = await db.execute(
            select(Integration)
            .where(Integration.type == "gitlab", Integration.is_active == True)
            .order_by(nullslast(Integration.agent_id.desc()))
        )
        rows = result.scalars().all()

    agent_specific = next((r for r in rows if r.agent_id == agent_id), None)
    system_wide = next((r for r in rows if r.agent_id is None), None)
    row = agent_specific or system_wide
    if not row or not row.credentials_enc:
        raise ValueError("No active GitLab integration found")
    creds = json.loads(decrypt_secret(row.credentials_enc))
    return creds, row.extra_config or {}


def create_gitlab_tools(agent_id: str):
    @tool
    async def gitlab_create_issue(
        title: str,
        description: str = "",
        project: str = "",
        labels: str = "",
        milestone_id: int = 0,
    ) -> str:
        """Create a new GitLab issue.

        Args:
            title: Issue title.
            description: Issue description (markdown supported).
            project: Project path (namespace/repo). Falls back to integration default.
            labels: Comma-separated labels to apply.
            milestone_id: Optional milestone ID.
        """
        creds, cfg = await _get_gitlab_creds(agent_id)
        base_url = cfg.get("base_url", "https://gitlab.com").rstrip("/")
        proj = project or cfg.get("default_project", "")
        if not proj:
            raise ValueError("project is required (or set default_project in integration config)")

        proj_encoded = quote(proj, safe="")
        payload: dict = {"title": title, "description": description}
        if labels:
            payload["labels"] = labels
        if milestone_id:
            payload["milestone_id"] = milestone_id

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{base_url}/api/v4/projects/{proj_encoded}/issues",
                headers={"PRIVATE-TOKEN": creds["private_token"], "Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()
        data = resp.json()
        return f"Issue #{data['iid']} created: {data['title']}\n{data['web_url']}"

    @tool
    async def gitlab_list_issues(
        project: str = "",
        state: str = "opened",
        limit: int = 20,
    ) -> str:
        """List GitLab issues for a project.

        Args:
            project: Project path (namespace/repo). Falls back to integration default.
            state: 'opened', 'closed', or 'all'.
            limit: Maximum issues to return.
        """
        creds, cfg = await _get_gitlab_creds(agent_id)
        base_url = cfg.get("base_url", "https://gitlab.com").rstrip("/")
        proj = project or cfg.get("default_project", "")
        if not proj:
            raise ValueError("project is required (or set default_project in integration config)")

        proj_encoded = quote(proj, safe="")
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{base_url}/api/v4/projects/{proj_encoded}/issues",
                headers={"PRIVATE-TOKEN": creds["private_token"]},
                params={"state": state, "per_page": limit},
            )
            resp.raise_for_status()
        issues = resp.json()
        lines = []
        for i in issues:
            labels = ", ".join(i.get("labels", []))
            assignee = (i.get("assignee") or {}).get("username", "unassigned")
            lines.append(f"#{i['iid']} [{i['state']}] {i['title']} | {assignee}" + (f" | {labels}" if labels else ""))
        return "\n".join(lines) if lines else "No issues found."

    @tool
    async def gitlab_create_mr(
        source_branch: str,
        target_branch: str,
        title: str,
        description: str = "",
        project: str = "",
        remove_source_branch: bool = True,
    ) -> str:
        """Create a GitLab Merge Request.

        Args:
            source_branch: Source branch name.
            target_branch: Target branch name (e.g. 'main').
            title: MR title.
            description: MR description.
            project: Project path. Falls back to integration default.
            remove_source_branch: Whether to delete the source branch on merge.
        """
        creds, cfg = await _get_gitlab_creds(agent_id)
        base_url = cfg.get("base_url", "https://gitlab.com").rstrip("/")
        proj = project or cfg.get("default_project", "")
        if not proj:
            raise ValueError("project is required (or set default_project in integration config)")

        proj_encoded = quote(proj, safe="")
        payload = {
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": title,
            "description": description,
            "remove_source_branch": remove_source_branch,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{base_url}/api/v4/projects/{proj_encoded}/merge_requests",
                headers={"PRIVATE-TOKEN": creds["private_token"], "Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()
        data = resp.json()
        return f"MR !{data['iid']} created: {data['title']}\n{data['web_url']}"

    return [gitlab_create_issue, gitlab_list_issues, gitlab_create_mr]
