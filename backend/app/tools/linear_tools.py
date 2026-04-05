"""Linear integration tools — create and manage Linear issues."""

from __future__ import annotations

import json
import logging

import httpx
from langchain_core.tools import tool

from app.core.vault import decrypt_secret

logger = logging.getLogger(__name__)

LINEAR_TOOL_IDS = {"linear_create_issue", "linear_list_issues", "linear_update_issue"}
_LINEAR_GQL = "https://api.linear.app/graphql"


async def _get_linear_creds(agent_id: str) -> tuple[dict, dict]:
    """Return (creds, extra_config) for Linear."""
    from app.db.session import async_session_factory
    from app.models.integration import Integration
    from sqlalchemy import select, nullslast

    async with async_session_factory() as db:
        result = await db.execute(
            select(Integration)
            .where(Integration.type == "linear", Integration.is_active == True)
            .order_by(nullslast(Integration.agent_id.desc()))
        )
        rows = result.scalars().all()

    agent_specific = next((r for r in rows if r.agent_id == agent_id), None)
    system_wide = next((r for r in rows if r.agent_id is None), None)
    row = agent_specific or system_wide
    if not row or not row.credentials_enc:
        raise ValueError("No active Linear integration found")
    creds = json.loads(decrypt_secret(row.credentials_enc))
    return creds, row.extra_config or {}


async def _gql(api_key: str, query: str, variables: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            _LINEAR_GQL,
            headers={"Authorization": api_key, "Content-Type": "application/json"},
            json={"query": query, "variables": variables or {}},
        )
        resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise ValueError(data["errors"][0].get("message", "GraphQL error"))
    return data.get("data", {})


def create_linear_tools(agent_id: str):
    @tool
    async def linear_create_issue(
        title: str,
        description: str = "",
        team_id: str = "",
        priority: int = 0,
    ) -> str:
        """Create a new issue in Linear.

        Args:
            title: Issue title.
            description: Optional markdown description.
            team_id: Linear team ID. Falls back to integration default if empty.
            priority: 0=No priority, 1=Urgent, 2=High, 3=Medium, 4=Low.
        """
        creds, cfg = await _get_linear_creds(agent_id)
        tid = team_id or cfg.get("team_id", "")
        if not tid:
            raise ValueError("team_id is required (or set a default in the integration config)")

        mutation = """
        mutation CreateIssue($input: IssueCreateInput!) {
          issueCreate(input: $input) {
            success
            issue { id title url identifier }
          }
        }
        """
        variables = {"input": {"teamId": tid, "title": title, "description": description, "priority": priority}}
        data = await _gql(creds["api_key"], mutation, variables)
        issue = data["issueCreate"]["issue"]
        return f"Issue created: {issue['identifier']} — {issue['title']}\n{issue['url']}"

    @tool
    async def linear_list_issues(
        team_id: str = "",
        status: str = "",
        limit: int = 20,
    ) -> str:
        """List Linear issues, optionally filtered by team and status.

        Args:
            team_id: Linear team ID filter. Falls back to integration default.
            status: Status name filter (e.g. 'In Progress', 'Todo').
            limit: Max issues to return (default 20).
        """
        creds, cfg = await _get_linear_creds(agent_id)
        tid = team_id or cfg.get("team_id", "")

        filter_parts = []
        if tid:
            filter_parts.append(f'team: {{id: {{eq: "{tid}"}}}}')
        if status:
            filter_parts.append(f'state: {{name: {{eq: "{status}"}}}}')
        filter_str = "{" + ", ".join(filter_parts) + "}" if filter_parts else ""

        query = f"""
        query ListIssues {{
          issues(first: {limit}{f', filter: {filter_str}' if filter_str else ''}) {{
            nodes {{
              id identifier title state {{ name }} priority assignee {{ name }} url
            }}
          }}
        }}
        """
        data = await _gql(creds["api_key"], query)
        nodes = data.get("issues", {}).get("nodes", [])
        lines = []
        for n in nodes:
            state = n.get("state", {}).get("name", "?")
            assignee = (n.get("assignee") or {}).get("name", "unassigned")
            lines.append(f"[{n['identifier']}] {n['title']} | {state} | {assignee}")
        return "\n".join(lines) if lines else "No issues found."

    @tool
    async def linear_update_issue(
        issue_id: str,
        status: str = "",
        title: str = "",
        description: str = "",
        priority: int = -1,
    ) -> str:
        """Update an existing Linear issue.

        Args:
            issue_id: The Linear issue ID.
            status: New status name (e.g. 'Done', 'In Progress').
            title: New title (optional).
            description: New description (optional).
            priority: New priority 0-4 (-1 to leave unchanged).
        """
        creds, _ = await _get_linear_creds(agent_id)

        # If status given, resolve state ID
        state_id = None
        if status:
            q = f'query {{ workflowStates(filter: {{name: {{eq: "{status}"}}}}) {{ nodes {{ id name }} }} }}'
            data = await _gql(creds["api_key"], q)
            states = data.get("workflowStates", {}).get("nodes", [])
            if states:
                state_id = states[0]["id"]

        mutation = """
        mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
          issueUpdate(id: $id, input: $input) {
            success
            issue { id identifier title url }
          }
        }
        """
        input_data: dict = {}
        if title:
            input_data["title"] = title
        if description:
            input_data["description"] = description
        if state_id:
            input_data["stateId"] = state_id
        if priority >= 0:
            input_data["priority"] = priority

        data = await _gql(creds["api_key"], mutation, {"id": issue_id, "input": input_data})
        issue = data["issueUpdate"]["issue"]
        return f"Updated: {issue['identifier']} — {issue['title']}\n{issue['url']}"

    return [linear_create_issue, linear_list_issues, linear_update_issue]
