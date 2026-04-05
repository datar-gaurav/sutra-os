"""Integration model — stores third-party service credentials per agent or system-wide."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, generate_uuid

# ─── Integration type metadata (for UI form generation) ──────────────────────

INTEGRATION_TYPES: dict[str, dict] = {
    "notion": {
        "name": "Notion",
        "description": "Read and write Notion pages and databases",
        "icon": "notion",
        "credential_fields": [
            {"key": "api_key", "label": "Integration Token", "secret": True, "placeholder": "secret_..."},
        ],
        "config_fields": [],
        "tool_ids": ["notion_search", "notion_get_page", "notion_create_page", "notion_query_database"],
    },
    "linear": {
        "name": "Linear",
        "description": "Create and manage Linear issues",
        "icon": "linear",
        "credential_fields": [
            {"key": "api_key", "label": "API Key", "secret": True, "placeholder": "lin_api_..."},
        ],
        "config_fields": [
            {"key": "team_id", "label": "Default Team ID", "secret": False, "placeholder": "TEAM-123"},
        ],
        "tool_ids": ["linear_create_issue", "linear_list_issues", "linear_update_issue"],
    },
    "jira": {
        "name": "Jira",
        "description": "Create and search Jira issues",
        "icon": "jira",
        "credential_fields": [
            {"key": "email", "label": "Email", "secret": False, "placeholder": "you@company.com"},
            {"key": "api_token", "label": "API Token", "secret": True, "placeholder": "ATATT..."},
        ],
        "config_fields": [
            {"key": "base_url", "label": "Jira Base URL", "secret": False, "placeholder": "https://yourorg.atlassian.net"},
            {"key": "project_key", "label": "Default Project Key", "secret": False, "placeholder": "ENG"},
        ],
        "tool_ids": ["jira_create_issue", "jira_search_issues", "jira_update_issue"],
    },
    "slack": {
        "name": "Slack",
        "description": "Post messages and read Slack channels",
        "icon": "slack",
        "credential_fields": [
            {"key": "bot_token", "label": "Bot Token", "secret": True, "placeholder": "xoxb-..."},
        ],
        "config_fields": [
            {"key": "default_channel", "label": "Default Channel", "secret": False, "placeholder": "#general"},
        ],
        "tool_ids": ["slack_post_message", "slack_list_channels"],
    },
    "gitlab": {
        "name": "GitLab",
        "description": "Create issues and merge requests on GitLab",
        "icon": "gitlab",
        "credential_fields": [
            {"key": "private_token", "label": "Personal Access Token", "secret": True, "placeholder": "glpat-..."},
        ],
        "config_fields": [
            {"key": "base_url", "label": "GitLab URL", "secret": False, "placeholder": "https://gitlab.com"},
            {"key": "default_project", "label": "Default Project (namespace/repo)", "secret": False, "placeholder": "myorg/myrepo"},
        ],
        "tool_ids": ["gitlab_create_issue", "gitlab_list_issues", "gitlab_create_mr"],
    },
    "github": {
        "name": "GitHub (Extended)",
        "description": "List issues, read files, search code on GitHub",
        "icon": "github",
        "credential_fields": [
            {"key": "token", "label": "Personal Access Token", "secret": True, "placeholder": "ghp_..."},
        ],
        "config_fields": [
            {"key": "default_repo", "label": "Default Repository (owner/repo)", "secret": False, "placeholder": "myorg/myrepo"},
        ],
        "tool_ids": ["github_list_issues", "github_get_file", "github_search_code"],
    },
    "google_drive": {
        "name": "Google Drive",
        "description": "Read, write, upload, and organise files in Google Drive",
        "icon": "google-drive",
        "oauth": True,  # connected via OAuth flow, not manual API key
        "credential_fields": [],  # credentials managed via /auth/google/login?service=drive
        "config_fields": [
            {"key": "google_email", "label": "Connected Account", "secret": False, "readonly": True},
            {"key": "default_folder_id", "label": "Default Folder ID", "secret": False, "placeholder": "Leave empty for My Drive root"},
        ],
        "tool_ids": [
            "gdrive_search_files",
            "gdrive_read_file",
            "gdrive_upload_file",
            "gdrive_create_document",
            "gdrive_list_folder",
            "gdrive_create_folder",
            "gdrive_move_file",
        ],
    },
    "google_calendar": {
        "name": "Google Calendar",
        "description": "Create and manage events in Google Calendar",
        "icon": "google-calendar",
        "oauth": True,
        "credential_fields": [],
        "config_fields": [
            {"key": "google_email", "label": "Connected Account", "secret": False, "readonly": True},
        ],
        "tool_ids": [
            "gcal_list_events",
            "gcal_create_event",
            "gcal_delete_event",
        ],
    },
}


class Integration(Base, TimestampMixin):
    """Third-party integration config, optionally scoped to an agent."""

    __tablename__ = "integrations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # None = system-wide fallback; set = agent-specific config
    agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Encrypted JSON: {"api_key": "...", "bot_token": "..."}
    credentials_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Plain JSON for non-secret config: {"base_url": "...", "team_id": "..."}
    extra_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
