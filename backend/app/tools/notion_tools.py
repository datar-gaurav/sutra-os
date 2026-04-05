"""Notion integration tools — search, read, and create Notion pages."""

from __future__ import annotations

import json
import logging

import httpx
from langchain_core.tools import tool

from app.core.vault import decrypt_secret

logger = logging.getLogger(__name__)

NOTION_TOOL_IDS = {"notion_search", "notion_get_page", "notion_create_page", "notion_query_database"}

_NOTION_VERSION = "2022-06-28"


async def _get_notion_creds(agent_id: str) -> dict:
    """Fetch Notion credentials for agent_id (agent-specific first, then system-wide)."""
    from app.db.session import async_session_factory
    from app.models.integration import Integration
    from sqlalchemy import select, nullslast

    async with async_session_factory() as db:
        result = await db.execute(
            select(Integration)
            .where(Integration.type == "notion", Integration.is_active == True)
            .order_by(nullslast(Integration.agent_id.desc()))
        )
        rows = result.scalars().all()

    agent_specific = next((r for r in rows if r.agent_id == agent_id), None)
    system_wide = next((r for r in rows if r.agent_id is None), None)
    row = agent_specific or system_wide
    if not row or not row.credentials_enc:
        raise ValueError("No active Notion integration found")
    return json.loads(decrypt_secret(row.credentials_enc))


def _notion_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": _NOTION_VERSION,
        "Content-Type": "application/json",
    }


def create_notion_tools(agent_id: str):
    @tool
    async def notion_search(query: str) -> str:
        """Search Notion workspace for pages and databases matching a query."""
        creds = await _get_notion_creds(agent_id)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.notion.com/v1/search",
                headers=_notion_headers(creds["api_key"]),
                json={"query": query, "page_size": 10},
            )
            resp.raise_for_status()
        results = resp.json().get("results", [])
        items = []
        for r in results:
            obj_type = r.get("object", "unknown")
            title = ""
            if obj_type == "page":
                props = r.get("properties", {})
                title_prop = props.get("title") or props.get("Name") or next(iter(props.values()), {})
                if isinstance(title_prop, dict):
                    rich = title_prop.get("title") or title_prop.get("rich_text", [])
                    title = "".join(t.get("plain_text", "") for t in rich)
            elif obj_type == "database":
                title_list = r.get("title", [])
                title = "".join(t.get("plain_text", "") for t in title_list)
            items.append(f"[{obj_type}] {title} (id: {r['id']})")
        return "\n".join(items) if items else "No results found."

    @tool
    async def notion_get_page(page_id: str) -> str:
        """Get the content of a Notion page by its ID."""
        creds = await _get_notion_creds(agent_id)
        async with httpx.AsyncClient(timeout=15) as client:
            # Get page metadata
            page_resp = await client.get(
                f"https://api.notion.com/v1/pages/{page_id}",
                headers=_notion_headers(creds["api_key"]),
            )
            page_resp.raise_for_status()
            # Get page blocks
            blocks_resp = await client.get(
                f"https://api.notion.com/v1/blocks/{page_id}/children",
                headers=_notion_headers(creds["api_key"]),
            )
            blocks_resp.raise_for_status()

        page = page_resp.json()
        blocks = blocks_resp.json().get("results", [])

        # Extract title
        props = page.get("properties", {})
        title_prop = props.get("title") or props.get("Name") or next(iter(props.values()), {})
        if isinstance(title_prop, dict):
            rich = title_prop.get("title") or title_prop.get("rich_text", [])
            title = "".join(t.get("plain_text", "") for t in rich)
        else:
            title = page_id

        lines = [f"# {title}", ""]
        for block in blocks:
            btype = block.get("type", "")
            bdata = block.get(btype, {})
            rich = bdata.get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in rich)
            if btype in ("paragraph",):
                lines.append(text)
            elif btype.startswith("heading_"):
                level = btype[-1]
                lines.append("#" * int(level) + " " + text)
            elif btype == "bulleted_list_item":
                lines.append(f"• {text}")
            elif btype == "numbered_list_item":
                lines.append(f"1. {text}")
            elif btype == "code":
                lang = bdata.get("language", "")
                lines.append(f"```{lang}\n{text}\n```")
        return "\n".join(lines)

    @tool
    async def notion_create_page(
        parent_id: str,
        title: str,
        content: str = "",
        parent_type: str = "page",
    ) -> str:
        """Create a new Notion page under a parent page or database.

        Args:
            parent_id: ID of the parent page or database.
            title: Page title.
            content: Optional text content to add as a paragraph block.
            parent_type: 'page' or 'database_id'.
        """
        creds = await _get_notion_creds(agent_id)
        parent_key = "database_id" if parent_type == "database_id" else "page_id"
        payload: dict = {
            "parent": {parent_key: parent_id},
            "properties": {
                "title": {"title": [{"text": {"content": title}}]}
            },
        }
        if content:
            payload["children"] = [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"text": {"content": content}}]},
                }
            ]
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.notion.com/v1/pages",
                headers=_notion_headers(creds["api_key"]),
                json=payload,
            )
            resp.raise_for_status()
        page = resp.json()
        return f"Page created: id={page['id']} url={page.get('url', '')}"

    @tool
    async def notion_query_database(database_id: str, filter_json: str = "") -> str:
        """Query a Notion database and return matching rows.

        Args:
            database_id: The Notion database ID.
            filter_json: Optional JSON filter object as a string (Notion filter format).
        """
        creds = await _get_notion_creds(agent_id)
        payload: dict = {"page_size": 20}
        if filter_json:
            try:
                payload["filter"] = json.loads(filter_json)
            except json.JSONDecodeError:
                pass
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://api.notion.com/v1/databases/{database_id}/query",
                headers=_notion_headers(creds["api_key"]),
                json=payload,
            )
            resp.raise_for_status()
        rows = resp.json().get("results", [])
        lines = []
        for r in rows:
            props = r.get("properties", {})
            row_parts = []
            for key, val in props.items():
                vtype = val.get("type", "")
                if vtype == "title":
                    text = "".join(t.get("plain_text", "") for t in val.get("title", []))
                elif vtype in ("rich_text", "text"):
                    text = "".join(t.get("plain_text", "") for t in val.get("rich_text", []))
                elif vtype == "select":
                    text = (val.get("select") or {}).get("name", "")
                elif vtype == "number":
                    text = str(val.get("number", ""))
                elif vtype == "checkbox":
                    text = str(val.get("checkbox", ""))
                elif vtype == "date":
                    text = (val.get("date") or {}).get("start", "")
                else:
                    text = ""
                if text:
                    row_parts.append(f"{key}: {text}")
            lines.append(" | ".join(row_parts) + f" (id: {r['id']})")
        return "\n".join(lines) if lines else "No results."

    return [notion_search, notion_get_page, notion_create_page, notion_query_database]
