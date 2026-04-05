"""AgentRole model and predefined role templates."""

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, generate_uuid

# Import rich prompts from agent_template module (single source of truth)
from app.models.agent_template import (
    _CEO_PROMPT, _PM_PROMPT, _ENGINEER_PROMPT, _MARKETING_PROMPT,
    _FINANCE_PROMPT, _HR_PROMPT, _SECURITY_PROMPT, _DATA_PROMPT,
    _CUSTOMER_SUCCESS_PROMPT, _RESEARCH_PROMPT,
)


# Predefined role templates — shown in UI, users can save them as roles or create custom ones
ROLE_TEMPLATES = [
    {
        "name": "CEO",
        "description": "Chief Executive Officer — sets organizational strategy, makes high-level decisions, and delegates to department leads.",
        "system_prompt_template": _CEO_PROMPT,
        "default_tools": ["create_task", "list_tasks", "update_task", "get_task", "start_discussion", "ask_agent", "control_agent", "request_approval", "create_agent_from_template", "list_agent_templates", "archive_agent", "save_memory", "search_memory"],
        "permissions": {"can_create_agents": True, "can_approve": True, "budget_limit": None},
        "reports_to_role": None,
        "color": "#6366f1",
        "icon": "Crown",
    },
    {
        "name": "Product Manager",
        "description": "Breaks strategic goals into actionable tasks, manages roadmap, and coordinates across teams.",
        "system_prompt_template": _PM_PROMPT,
        "default_tools": ["create_task", "list_tasks", "update_task", "get_task", "start_discussion", "ask_agent", "save_memory", "search_memory"],
        "permissions": {"can_create_agents": False, "can_approve": False, "budget_limit": 1000},
        "reports_to_role": "CEO",
        "color": "#8b5cf6",
        "icon": "Briefcase",
    },
    {
        "name": "Software Engineer",
        "description": "Implements features, fixes bugs, writes code and tests.",
        "system_prompt_template": _ENGINEER_PROMPT,
        "default_tools": ["read_file", "write_file", "list_directory", "search_files", "run_shell_command", "create_github_issue", "create_github_pr", "commit_and_push", "create_task", "update_task", "list_tasks", "get_task", "start_discussion", "ask_agent", "request_approval", "save_memory", "search_memory"],
        "permissions": {"can_create_agents": False, "can_approve": False, "budget_limit": 500},
        "reports_to_role": "Product Manager",
        "color": "#06b6d4",
        "icon": "Code2",
    },
    {
        "name": "Marketing Specialist",
        "description": "Creates content, runs campaigns, and manages brand communications.",
        "system_prompt_template": _MARKETING_PROMPT,
        "default_tools": ["create_task", "list_tasks", "update_task", "get_task", "scrape_webpage", "search_knowledge_base", "ingest_url_to_kb", "start_discussion", "ask_agent", "request_approval", "save_memory", "search_memory", "append_to_google_sheet"],
        "permissions": {"can_create_agents": False, "can_approve": False, "budget_limit": 2000},
        "reports_to_role": "CEO",
        "color": "#f59e0b",
        "icon": "Megaphone",
    },
    {
        "name": "Finance Analyst",
        "description": "Tracks costs, manages budgets, and produces financial reports.",
        "system_prompt_template": _FINANCE_PROMPT,
        "default_tools": ["analyze_data", "read_file", "create_task", "list_tasks", "update_task", "start_discussion", "ask_agent", "request_approval", "save_memory", "search_memory", "append_to_google_sheet"],
        "permissions": {"can_create_agents": False, "can_approve": True, "budget_limit": None},
        "reports_to_role": "CEO",
        "color": "#10b981",
        "icon": "DollarSign",
    },
    {
        "name": "HR Manager",
        "description": "Manages agent onboarding, performance reviews, and organizational culture.",
        "system_prompt_template": _HR_PROMPT,
        "default_tools": ["create_agent_from_template", "list_agent_templates", "archive_agent", "create_task", "list_tasks", "update_task", "get_task", "start_discussion", "ask_agent", "request_approval", "save_memory", "search_memory"],
        "permissions": {"can_create_agents": True, "can_approve": False, "budget_limit": 500},
        "reports_to_role": "CEO",
        "color": "#ec4899",
        "icon": "Users",
    },
    {
        "name": "Security Specialist",
        "description": "Audits systems for vulnerabilities, enforces security policies, and responds to incidents.",
        "system_prompt_template": _SECURITY_PROMPT,
        "default_tools": ["read_file", "list_directory", "search_files", "run_shell_command", "get_system_info", "list_processes", "scrape_webpage", "create_task", "list_tasks", "update_task", "start_discussion", "ask_agent", "request_approval", "search_knowledge_base", "ingest_url_to_kb", "save_memory", "search_memory"],
        "permissions": {"can_create_agents": False, "can_approve": True, "budget_limit": 1000},
        "reports_to_role": "CEO",
        "color": "#ef4444",
        "icon": "ShieldCheck",
    },
    {
        "name": "Data Analyst",
        "description": "Analyzes datasets, builds reports, and generates actionable insights.",
        "system_prompt_template": _DATA_PROMPT,
        "default_tools": ["analyze_data", "read_file", "search_files", "search_knowledge_base", "create_task", "list_tasks", "update_task", "start_discussion", "ask_agent", "save_memory", "search_memory", "append_to_google_sheet"],
        "permissions": {"can_create_agents": False, "can_approve": False, "budget_limit": 500},
        "reports_to_role": "Product Manager",
        "color": "#14b8a6",
        "icon": "BarChart3",
    },
    {
        "name": "Customer Success",
        "description": "Handles customer interactions, resolves issues, and drives satisfaction.",
        "system_prompt_template": _CUSTOMER_SUCCESS_PROMPT,
        "default_tools": ["create_task", "update_task", "search_knowledge_base", "ingest_url_to_kb", "ask_agent", "save_memory", "search_memory"],
        "permissions": {"can_create_agents": False, "can_approve": False, "budget_limit": 200},
        "reports_to_role": "CEO",
        "color": "#f97316",
        "icon": "HeartHandshake",
    },
    {
        "name": "Research Specialist",
        "description": "Conducts deep research on topics and produces comprehensive reports.",
        "system_prompt_template": _RESEARCH_PROMPT,
        "default_tools": ["scrape_webpage", "search_knowledge_base", "ingest_url_to_kb", "create_task", "list_tasks", "update_task", "start_discussion", "ask_agent", "save_memory", "search_memory"],
        "permissions": {"can_create_agents": False, "can_approve": False, "budget_limit": 300},
        "reports_to_role": "Product Manager",
        "color": "#a855f7",
        "icon": "Search",
    },
]


class AgentRole(Base, TimestampMixin):
    """Represents a role that can be assigned to an agent."""

    __tablename__ = "agent_roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_tools: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    permissions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    reports_to_role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
