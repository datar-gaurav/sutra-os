"""LangChain tool for agents to send outbound HTTP webhook calls."""

import json
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

WEBHOOK_TOOL_IDS = {"call_webhook"}


def create_webhook_tools(agent_id: str):
    """Create webhook tools bound to a specific agent."""

    @tool
    async def call_webhook(
        url: str,
        payload: str,
        method: str = "POST",
        headers: str = "{}",
    ) -> str:
        """Send an HTTP request to an external URL (outbound webhook / API call).

        Use this to notify external systems, trigger Zapier/Make automations,
        call n8n workflows, post to Slack webhook URLs, or integrate with any
        HTTP-based service.

        IMPORTANT: This sends data outside Sutra. Only call trusted URLs.
        For high-stakes external communications, use request_approval first.

        Args:
            url: The full URL to POST to (must start with https://).
            payload: JSON string with the request body.
            method: HTTP method — POST, PUT, or PATCH (default: POST).
            headers: JSON string of extra request headers (optional).

        Returns JSON with status_code and response body (truncated to 1000 chars).
        """
        import httpx

        method = method.upper()
        if method not in ("POST", "PUT", "PATCH"):
            return json.dumps({"error": f"Unsupported method '{method}'. Use POST, PUT, or PATCH."})

        try:
            body_dict = json.loads(payload) if payload.strip() else {}
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"Invalid JSON payload: {exc}"})

        try:
            extra_headers = json.loads(headers) if headers.strip() != "{}" else {}
        except json.JSONDecodeError:
            extra_headers = {}

        request_headers = {
            "Content-Type": "application/json",
            "X-Sutra-Agent": agent_id,
            **extra_headers,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.request(
                    method,
                    url,
                    json=body_dict,
                    headers=request_headers,
                )
                logger.info(
                    f"Agent {agent_id} called webhook {url} → HTTP {resp.status_code}"
                )
                return json.dumps({
                    "status_code": resp.status_code,
                    "ok": resp.is_success,
                    "response": resp.text[:1000],
                })
        except Exception as exc:
            logger.error(f"Agent {agent_id} webhook call failed: {exc}")
            return json.dumps({"error": f"Request failed: {exc}"})

    return [call_webhook]
