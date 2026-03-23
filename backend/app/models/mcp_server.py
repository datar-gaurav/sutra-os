"""MCP Server database model."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class MCPServer(Base, TimestampMixin):
    """Represents a configured MCP (Model Context Protocol) server."""

    __tablename__ = "mcp_servers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    # Connection
    transport_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="stdio"
    )  # stdio, sse, streamable_http
    command: Mapped[str] = mapped_column(Text, nullable=True)        # e.g. "npx -y @modelcontextprotocol/server-filesystem /tmp"
    args: Mapped[list] = mapped_column(JSON, nullable=True, default=list)  # additional CLI args
    url: Mapped[str] = mapped_column(String(500), nullable=True)      # for SSE / streamable HTTP transports
    env_vars: Mapped[dict] = mapped_column(JSON, nullable=True, default=dict)  # environment variables for the process
    headers: Mapped[dict] = mapped_column(JSON, nullable=True, default=dict)   # custom headers for HTTP/SSE

    # State
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="stopped"
    )  # stopped, starting, running, error

    # Discovered capabilities (populated after connecting)
    tools: Mapped[list] = mapped_column(JSON, nullable=True, default=list)        # [{name, description}]
    resources: Mapped[list] = mapped_column(JSON, nullable=True, default=list)    # [{uri, name, description}]
    prompts: Mapped[list] = mapped_column(JSON, nullable=True, default=list)      # [{name, description}]

    # Metadata
    icon: Mapped[str] = mapped_column(String(50), nullable=True)  # emoji or icon name
    tags: Mapped[list] = mapped_column(JSON, nullable=True, default=list)

    def __repr__(self) -> str:
        return f"<MCPServer(id={self.id}, name={self.name}, status={self.status})>"
