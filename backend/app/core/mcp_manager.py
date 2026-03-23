import asyncio
import logging
from typing import Any, Dict, List, Optional, Type, Union
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
from langchain_core.tools import tool, BaseTool, StructuredTool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
from pydantic import create_model, Field

from app.models.mcp_server import MCPServer
from app.api.schemas import ToolInfo

logger = logging.getLogger(__name__)

class MCPManager:
    """Manages connections to MCP servers and tool discovery."""

    def __init__(self):
        self._sessions: Dict[str, ClientSession] = {}
        self._tools: Dict[str, List[Dict[str, Any]]] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    def _get_lock(self, server_id: str) -> asyncio.Lock:
        if server_id not in self._locks:
            self._locks[server_id] = asyncio.Lock()
        return self._locks[server_id]

    async def connect_server(self, server: MCPServer) -> bool:
        """Establish a connection to an MCP server and fetch its tools."""
        async with self._get_lock(server.id):
            if server.id in self._sessions:
                return True

            try:
                if server.transport_type == "stdio":
                    params = StdioServerParameters(
                        command=server.command,
                        args=server.args or [],
                        env=server.env_vars or {}
                    )
                    asyncio.create_task(self._run_stdio_session(server, params))
                
                elif server.transport_type in ["sse", "streamable_http", "streamable-http"]:
                    asyncio.create_task(self._run_sse_session(server))
                
                else:
                    logger.error(f"Unsupported MCP transport: {server.transport_type}")
                    return False

                return True
            except Exception as e:
                logger.error(f"Failed to connect to MCP server {server.name}: {e}")
                return False

    async def _run_stdio_session(self, server: MCPServer, params: StdioServerParameters):
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._sessions[server.id] = session
                    
                    tools_result = await session.list_tools()
                    self._tools[server.id] = [
                        {
                            "name": t.name,
                            "description": t.description,
                            "input_schema": t.inputSchema
                        } for t in tools_result.tools
                    ]
                    logger.info(f"Connected to MCP stdio server {server.name}, found {len(self._tools[server.id])} tools.")
                    
                    while server.id in self._sessions:
                        await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"MCP stdio session error for {server.name}: {e}")
        finally:
            self._sessions.pop(server.id, None)
            self._tools.pop(server.id, None)

    async def _run_sse_session(self, server: MCPServer):
        try:
            if server.transport_type in ["streamable_http", "streamable-http"]:
                # Use official Streamable HTTP client
                # We need a client with the right headers
                async with httpx.AsyncClient(headers=server.headers) as http_client:
                    async with streamable_http_client(url=server.url, http_client=http_client) as (read, write, _):
                        async with ClientSession(read, write) as session:
                            await session.initialize()
                            self._sessions[server.id] = session
                            tools_result = await session.list_tools()
                            self._tools[server.id] = [
                                {
                                    "name": t.name,
                                    "description": t.description,
                                    "input_schema": t.inputSchema
                                } for t in tools_result.tools
                            ]
                            logger.info(f"Connected to MCP Streamable HTTP server {server.name}, found {len(self._tools[server.id])} tools.")
                            while server.id in self._sessions:
                                await asyncio.sleep(1)
            else:
                # Standard SSE client (GET)
                async with sse_client(url=server.url, headers=server.headers) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        self._sessions[server.id] = session
                        tools_result = await session.list_tools()
                        self._tools[server.id] = [
                            {
                                "name": t.name,
                                "description": t.description,
                                "input_schema": t.inputSchema
                            } for t in tools_result.tools
                        ]
                        logger.info(f"Connected to MCP SSE server {server.name}, found {len(self._tools[server.id])} tools.")
                        while server.id in self._sessions:
                            await asyncio.sleep(1)
        except Exception:
            logger.exception(f"MCP session error for {server.name}")
        finally:
            self._sessions.pop(server.id, None)
            self._tools.pop(server.id, None)

    async def call_tool(self, server_id: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
        session = self._sessions.get(server_id)
        if not session:
            raise Exception(f"MCP Server {server_id} is not connected.")
        
        # Ensure arguments are NOT nested if they are already top-level
        result = await session.call_tool(tool_name, arguments)
        return result.content

    def get_all_mcp_tools_metadata(self) -> List[Dict[str, Any]]:
        """Return all discovered tools from all active MCP servers as UI metadata."""
        all_tools = []
        for server_id, tools in self._tools.items():
            # Use a shorter identifier to help LLM tool calling (uuid[:8])
            short_id = server_id[:8]
            for tool_info in tools:
                all_tools.append({
                    "id": f"mcp_{short_id}_{tool_info['name']}",
                    "name": f"MCP: {tool_info['name']}",
                    "description": f"[{server_id}] {tool_info['description']}",
                    "category": "mcp",
                    "is_dangerous": False
                })
        return all_tools

    def get_langchain_tool(self, tool_id: str) -> Optional[BaseTool]:
        """Wrap a specific MCP tool into a LangChain StructuredTool."""
        if not tool_id.startswith("mcp_"):
            return None
        
        parts = tool_id.split("_", 2)
        if len(parts) < 3:
            return None
        
        short_id, tool_name = parts[1], parts[2]
        # Find the full server_id from the short_id
        server_id = next((sid for sid in self._tools.keys() if sid.startswith(short_id)), None)
        if not server_id:
            return None
            
        server_tools = self._tools.get(server_id, [])
        tool_info = next((t for t in server_tools if t["name"] == tool_name), None)
        
        if not tool_info:
            return None

        # Build dynamic Pydantic model for LangChain's StructuredTool
        # This ensures the LLM sees the correct parameters instead of generic kwargs
        schema = tool_info.get("input_schema", {})
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        field_definitions = {}
        for prop_name, prop_details in properties.items():
            # Basic type mapping
            prop_type = Any
            mcp_type = prop_details.get("type")
            if mcp_type == "string":
                prop_type = str
            elif mcp_type == "number":
                prop_type = float
            elif mcp_type == "integer":
                prop_type = int
            elif mcp_type == "boolean":
                prop_type = bool
            elif mcp_type == "object":
                prop_type = Dict[str, Any]
            elif mcp_type == "array":
                prop_type = List[Any]
            
            # Use Ellipsis (...) for required fields, None for optional
            default_val = ... if prop_name in required else None
            field_definitions[prop_name] = (
                prop_type, 
                Field(default=default_val, description=prop_details.get("description", ""))
            )

        # Create the model
        args_schema = create_model(f"{tool_name}Schema", **field_definitions) if field_definitions else None

        async def _call(**kwargs):
            return await self.call_tool(server_id, tool_name, kwargs)

        return StructuredTool.from_function(
            func=None,
            coroutine=_call,
            name=tool_id,
            description=tool_info["description"],
            args_schema=args_schema
        )

    async def sync_active_servers(self, db: AsyncSession):
        """Restore connections to all active MCP servers."""
        result = await db.execute(select(MCPServer).where(MCPServer.is_active == True))
        active_servers = result.scalars().all()
        
        for server in active_servers:
            await self.connect_server(server)

# Global singleton
mcp_manager = MCPManager()
