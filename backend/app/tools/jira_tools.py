"""Jira integration tools — create and search Jira issues."""

from __future__ import annotations

import json
import logging

import httpx
from langchain_core.tools import tool

from app.core.vault import decrypt_secret

logger = logging.getLogger(__name__)

JIRA_TOOL_IDS = {"jira_create_issue", "jira_search_issues", "jira_update_issue"}


async def _get_jira_creds(agent_id: str) -> tuple[dict, dict]:
    from app.db.session import async_session_factory
    from app.models.integration import Integration
    from sqlalchemy import select, nullslast

    async with async_session_factory() as db:
        result = await db.execute(
            select(Integration)
            .where(Integration.type == "jira", Integration.is_active == True)
            .order_by(nullslast(Integration.agent_id.desc()))
        )
        rows = result.scalars().all()

    agent_specific = next((r for r in rows if r.agent_id == agent_id), None)
    system_wide = next((r for r in rows if r.agent_id is None), None)
    row = agent_specific or system_wide
    if not row or not row.credentials_enc:
        raise ValueError("No active Jira integration found")
    creds = json.loads(decrypt_secret(row.credentials_enc))
    return creds, row.extra_config or {}


def create_jira_tools(agent_id: str):
    @tool
    async def jira_create_issue(
        summary: str,
        description: str = "",
        issue_type: str = "Task",
        project_key: str = "",
        priority: str = "Medium",
    ) -> str:
        """Create a new Jira issue.

        Args:
            summary: Issue title/summary.
            description: Optional issue description.
            issue_type: Issue type e.g. 'Task', 'Bug', 'Story'.
            project_key: Jira project key. Falls back to integration default.
            priority: Priority name e.g. 'Highest', 'High', 'Medium', 'Low', 'Lowest'.
        """
        creds, cfg = await _get_jira_creds(agent_id)
        base_url = cfg.get("base_url", "").rstrip("/")
        proj = project_key or cfg.get("project_key", "")
        if not base_url:
            raise ValueError("base_url is required in the Jira integration config")
        if not proj:
            raise ValueError("project_key is required")

        payload = {
            "fields": {
                "project": {"key": proj},
                "summary": summary,
                "issuetype": {"name": issue_type},
                "priority": {"name": priority},
            }
        }
        if description:
            payload["fields"]["description"] = {
                "version": 1,
                "type": "doc",
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}],
            }

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{base_url}/rest/api/3/issue",
                auth=(creds["email"], creds["api_token"]),
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()
        data = resp.json()
        key = data.get("key", "")
        return f"Issue created: {key}\nURL: {base_url}/browse/{key}"

    @tool
    async def jira_search_issues(
        jql: str,
        max_results: int = 20,
    ) -> str:
        """Search Jira issues using JQL (Jira Query Language).

        Args:
            jql: JQL query string e.g. 'project = ENG AND status = "In Progress"'.
            max_results: Maximum number of results to return.
        """
        creds, cfg = await _get_jira_creds(agent_id)
        base_url = cfg.get("base_url", "").rstrip("/")
        if not base_url:
            raise ValueError("base_url is required in the Jira integration config")

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{base_url}/rest/api/3/search",
                auth=(creds["email"], creds["api_token"]),
                headers={"Accept": "application/json"},
                params={"jql": jql, "maxResults": max_results, "fields": "summary,status,priority,assignee"},
            )
            resp.raise_for_status()
        issues = resp.json().get("issues", [])
        lines = []
        for i in issues:
            key = i["key"]
            fields = i.get("fields", {})
            summary = fields.get("summary", "")
            status = (fields.get("status") or {}).get("name", "?")
            priority = (fields.get("priority") or {}).get("name", "?")
            assignee = (fields.get("assignee") or {}).get("displayName", "unassigned")
            lines.append(f"[{key}] {summary} | {status} | {priority} | {assignee}")
        return "\n".join(lines) if lines else "No issues found."

    @tool
    async def jira_update_issue(
        issue_key: str,
        summary: str = "",
        status: str = "",
        comment: str = "",
    ) -> str:
        """Update a Jira issue — change summary, transition status, or add a comment.

        Args:
            issue_key: Jira issue key e.g. 'ENG-42'.
            summary: New summary (optional).
            status: Transition the issue to this status name (optional).
            comment: Add a comment to the issue (optional).
        """
        creds, cfg = await _get_jira_creds(agent_id)
        base_url = cfg.get("base_url", "").rstrip("/")
        if not base_url:
            raise ValueError("base_url is required in the Jira integration config")

        messages = []
        auth = (creds["email"], creds["api_token"])
        headers = {"Accept": "application/json", "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=15) as client:
            if summary:
                resp = await client.put(
                    f"{base_url}/rest/api/3/issue/{issue_key}",
                    auth=auth,
                    headers=headers,
                    json={"fields": {"summary": summary}},
                )
                resp.raise_for_status()
                messages.append("summary updated")

            if status:
                # Get available transitions
                tr_resp = await client.get(
                    f"{base_url}/rest/api/3/issue/{issue_key}/transitions",
                    auth=auth,
                    headers={"Accept": "application/json"},
                )
                tr_resp.raise_for_status()
                transitions = tr_resp.json().get("transitions", [])
                match = next((t for t in transitions if t["name"].lower() == status.lower()), None)
                if match:
                    tr_put = await client.post(
                        f"{base_url}/rest/api/3/issue/{issue_key}/transitions",
                        auth=auth,
                        headers=headers,
                        json={"transition": {"id": match["id"]}},
                    )
                    tr_put.raise_for_status()
                    messages.append(f"status → {status}")
                else:
                    available = [t["name"] for t in transitions]
                    messages.append(f"status '{status}' not found (available: {available})")

            if comment:
                c_resp = await client.post(
                    f"{base_url}/rest/api/3/issue/{issue_key}/comment",
                    auth=auth,
                    headers=headers,
                    json={
                        "body": {
                            "version": 1,
                            "type": "doc",
                            "content": [{"type": "paragraph", "content": [{"type": "text", "text": comment}]}],
                        }
                    },
                )
                c_resp.raise_for_status()
                messages.append("comment added")

        return f"{issue_key}: " + ", ".join(messages) if messages else f"{issue_key}: no changes made"

    return [jira_create_issue, jira_search_issues, jira_update_issue]
