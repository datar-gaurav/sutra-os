import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from langchain.tools import tool

logger = logging.getLogger(__name__)

# Config from environment
# For AFFINE Cloud, use https://app.affine.pro/graphql
# For self-hosted, use your local URL
AFFINE_BASE_URL = os.getenv("AFFINE_BASE_URL", "https://app.affine.pro").rstrip("/")
AFFINE_TOKEN = os.getenv("AFFINE_TOKEN")


async def _query_affine(query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Execute a GraphQL query against the AFFiNE API."""
    if not AFFINE_TOKEN:
        raise ValueError("AFFINE_TOKEN is not set in environment variables.")

    url = f"{AFFINE_BASE_URL}/graphql"
    
    headers = {
        "Content-Type": "application/json",
    }

    # Support for both API Tokens (start with ut_) and Session Cookies
    if AFFINE_TOKEN.startswith("ut_"):
        headers["Authorization"] = f"Bearer {AFFINE_TOKEN}"
    else:
        # Fallback to session cookie for backward compatibility with older session based auth
        headers["Cookie"] = f"__Secure-next-auth.session-token={AFFINE_TOKEN}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                url,
                json={"query": query, "variables": variables or {}},
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
            
            if "errors" in data:
                error_msg = data["errors"][0].get("message", "Unknown GraphQL error")
                logger.error(f"AFFiNE GraphQL error: {error_msg}")
                raise Exception(f"AFFiNE API error: {error_msg}")
                
            return data.get("data", {})
        except httpx.HTTPStatusError as e:
            logger.error(f"AFFiNE API HTTP error: {e.response.status_code} - {e.response.text}")
            raise Exception(f"AFFiNE API connection failed: {e.response.status_code}")
        except Exception as e:
            logger.error(f"AFFiNE API error: {str(e)}")
            raise e
    
    return {} # Should be unreachable due to returns/raises above


@tool
async def list_affine_workspaces() -> List[Dict[str, Any]]:
    """List all available AFFiNE workspaces.
    
    Returns:
        A list of workspaces with their IDs and names.
    """
    query = """
    query {
      workspaces {
        id
      }
    }
    """
    data = await _query_affine(query)
    return data.get("workspaces", [])


@tool
async def search_affine_documents(workspace_id: str, query_text: str) -> List[Dict[str, Any]]:
    """Search for documents in an AFFiNE workspace by title or content.
    
    Args:
        workspace_id: The ID of the workspace to search in.
        query_text: The search term to look for.
        
    Returns:
        A list of matching document nodes with snippets.
    """
    query = """
    query Search($id: String!, $query: String!) {
      workspace(id: $id) {
        search(query: $query) {
          nodes {
            id
            title
            content
          }
        }
      }
    }
    """
    data = await _query_affine(query, {"id": workspace_id, "query": query_text})
    workspace = data.get("workspace")
    if not workspace:
        return []
        
    return workspace.get("search", {}).get("nodes", [])


@tool
async def get_affine_document_meta(workspace_id: str, doc_id: str) -> Dict[str, Any]:
    """Get metadata for a specific AFFiNE document.
    
    Args:
        workspace_id: The ID of the workspace.
        doc_id: The ID of the document.
        
    Returns:
        Document metadata including title and IDs.
    """
    query = """
    query GetDoc($workspaceId: String!, $docId: String!) {
      workspace(id: $workspaceId) {
        doc(id: $docId) {
          id
          title
        }
      }
    }
    """
    data = await _query_affine(query, {"workspaceId": workspace_id, "docId": doc_id})
    workspace = data.get("workspace")
    if not workspace:
        return {}
        
    return workspace.get("doc", {})
