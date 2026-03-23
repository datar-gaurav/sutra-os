"""Pydantic schemas for API request/response validation."""

from datetime import datetime

from pydantic import AnyHttpUrl, BaseModel, EmailStr, Field, field_validator

from app.models.discussion import DiscussionStatus, DiscussionType
from app.models.memory import MemoryType
from app.models.project import ProjectStatus
from app.models.task import TaskPriority, TaskStatus


# ─── Auth Schemas ─────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c in "!@#$%^&*()_+-=[]{}|;':\",./<>?" for c in v):
            raise ValueError("Password must contain at least one special character")
        return v

class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    user: UserResponse

class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


# ─── Memory Schemas ───────────────────────────────────────────────────────────

class MemoryCreate(BaseModel):
    content: str = Field(..., min_length=5)
    agent_id: str | None = None
    type: MemoryType = MemoryType.fact
    importance_score: float = Field(0.5, ge=0.0, le=1.0)
    tier: str = "recall"  # core, recall, archival

class MemoryResponse(BaseModel):
    id: str
    agent_id: str | None
    type: MemoryType
    content: str
    importance_score: float
    access_count: int
    last_accessed_at: datetime | None
    # Phase 5.1: Three-tier memory fields
    tier: str = "recall"
    decay_score: float = 1.0
    source: str = "auto"
    is_deleted: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Folder Schemas ───────────────────────────────────────────────────────────

class FolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

class FolderUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

class FolderResponse(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Rate Limit Schemas ───────────────────────────────────────────────────────

class ModelRateLimitCreate(BaseModel):
    provider: str = Field(..., min_length=1, max_length=50)
    model: str = Field(..., min_length=1, max_length=100)
    label: str | None = None
    requests_per_minute: int | None = None
    requests_per_day: int | None = None
    tokens_per_minute: int | None = None
    tokens_per_day: int | None = None
    refresh_interval_hours: int = 24

class ModelRateLimitUpdate(BaseModel):
    label: str | None = None
    requests_per_minute: int | None = None
    requests_per_day: int | None = None
    tokens_per_minute: int | None = None
    tokens_per_day: int | None = None
    refresh_interval_hours: int | None = None

class ModelRateLimitResponse(BaseModel):
    id: str
    provider: str
    model: str
    label: str | None
    requests_per_minute: int | None
    requests_per_day: int | None
    tokens_per_minute: int | None
    tokens_per_day: int | None
    refresh_interval_hours: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── LLM Purpose Schemas ─────────────────────────────────────────────────────

class PrioritySlot(BaseModel):
    provider: str
    model: str

class LLMPurposeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    is_default: bool = False
    priority_1: dict | None = None
    priority_2: dict | None = None
    priority_3: dict | None = None
    priority_4: dict | None = None
    priority_5: dict | None = None

class LLMPurposeUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    is_default: bool | None = None
    priority_1: dict | None = None
    priority_2: dict | None = None
    priority_3: dict | None = None
    priority_4: dict | None = None
    priority_5: dict | None = None

class LLMPurposeResponse(BaseModel):
    id: str
    name: str
    description: str | None
    is_default: bool
    priority_1: dict | None
    priority_2: dict | None
    priority_3: dict | None
    priority_4: dict | None
    priority_5: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Agent Schemas ────────────────────────────────────────────────────────────

class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    avatar_url: str | None = None
    system_prompt: str = "You are a helpful AI assistant."
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(4096, ge=1, le=128000)
    # Purpose-based routing (preferred)
    purpose_id: str | None = None
    # Legacy LLM fields (backward compat)
    llm_provider: str = "ollama"
    llm_model: str = "llama3"
    secondary_provider: str | None = None
    secondary_model: str | None = None
    fallback_provider: str | None = None
    fallback_model: str | None = None
    enabled_tools: list[str] = []
    folder_id: str | None = None
    slack_channel_id: str | None = None
    telegram_chat_id: str | None = None
    telegram_enabled: bool = False
    online_notification_enabled: bool = False
    metadata_: dict | None = Field(None, alias="metadata")
    # Autonomy controls
    auto_approve_below: str | None = None  # null | "low" | "medium"
    max_tool_calls_per_run: int = 0  # 0 = unlimited
    max_tokens_per_day: int = 0  # 0 = unlimited

    @field_validator("system_prompt")
    @classmethod
    def _sanitize_system_prompt(cls, v: str) -> str:
        from app.core.sanitizer import sanitize_system_prompt
        return sanitize_system_prompt(v)

    @field_validator("auto_approve_below")
    @classmethod
    def _validate_auto_approve(cls, v: str | None) -> str | None:
        if v is not None and v not in ("low", "medium"):
            raise ValueError("auto_approve_below must be null, 'low', or 'medium'")
        return v


class AgentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    avatar_url: str | None = None
    system_prompt: str | None = None

    @field_validator("system_prompt")
    @classmethod
    def _sanitize_system_prompt(cls, v: str | None) -> str | None:
        if v is None:
            return v
        from app.core.sanitizer import sanitize_system_prompt
        return sanitize_system_prompt(v)
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(None, ge=1, le=128000)
    purpose_id: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    secondary_provider: str | None = None
    secondary_model: str | None = None
    fallback_provider: str | None = None
    fallback_model: str | None = None
    enabled_tools: list[str] | None = None
    folder_id: str | None = None
    slack_channel_id: str | None = None
    telegram_chat_id: str | None = None
    telegram_enabled: bool | None = None
    online_notification_enabled: bool | None = None
    metadata_: dict | None = Field(None, alias="metadata")
    # Phase 1.4 org fields
    role_id: str | None = None
    team_id: str | None = None
    reports_to_agent_id: str | None = None
    skills: list[str] | None = None
    # Autonomy controls
    auto_approve_below: str | None = None
    max_tool_calls_per_run: int | None = None
    max_tokens_per_day: int | None = None


class AgentResponse(BaseModel):
    id: str
    name: str
    description: str | None
    avatar_url: str | None
    system_prompt: str
    temperature: float
    max_tokens: int
    purpose_id: str | None = None
    llm_provider: str
    llm_model: str
    secondary_provider: str | None
    secondary_model: str | None
    fallback_provider: str | None
    fallback_model: str | None
    enabled_tools: list[str]
    is_active: bool
    status: str
    folder_id: str | None
    slack_channel_id: str | None
    telegram_chat_id: str | None
    telegram_enabled: bool
    online_notification_enabled: bool
    # Phase 1.4 org fields
    role_id: str | None = None
    team_id: str | None = None
    reports_to_agent_id: str | None = None
    skills: list[str] = []
    # Phase 2.4 fields
    template_id: str | None = None
    is_archived: bool = False
    archived_reason: str | None = None
    # Autonomy controls
    auto_approve_below: str | None = None
    max_tool_calls_per_run: int = 0
    max_tokens_per_day: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Agent Template Schemas ───────────────────────────────────────────────────

class AgentTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    category: str = "general"
    system_prompt: str = "You are a helpful AI assistant."
    default_tools: list[str] = []
    default_llm_provider: str = "ollama"
    default_llm_model: str = "llama3"
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    role_name: str | None = None
    icon: str | None = "Bot"
    color: str | None = "#6366f1"
    tags: list[str] = []


class AgentTemplateResponse(BaseModel):
    id: str
    name: str
    description: str | None
    category: str
    system_prompt: str
    default_tools: list[str]
    default_llm_provider: str
    default_llm_model: str
    temperature: float
    role_name: str | None
    icon: str | None
    color: str | None
    tags: list[str]
    is_builtin: bool
    created_by_agent_id: str | None
    usage_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentPerformanceResponse(BaseModel):
    agent_id: str
    agent_name: str
    total_invocations: int
    error_count: int
    error_rate: float
    avg_latency_ms: float
    total_tasks_created: int
    total_tasks_completed: int
    task_completion_rate: float
    total_cost_usd: float
    performance_score: float  # 0-100


# ─── LLM Provider Schemas ────────────────────────────────────────────────────

class LLMProviderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    provider_type: str  # ollama, openai, anthropic, google, openrouter, perplexity, groq, custom
    base_url: str | None = None
    api_key: str | None = None  # Plain key — encrypted before storage
    is_default: bool = False
    supports_tool_calling: bool = True


class LLMProviderUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    is_enabled: bool | None = None
    is_default: bool | None = None
    supports_tool_calling: bool | None = None


class LLMProviderResponse(BaseModel):
    id: str
    name: str
    provider_type: str
    base_url: str | None
    is_enabled: bool
    is_default: bool
    supports_tool_calling: bool
    has_api_key: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Chat Schemas ─────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    agent_id: str
    message: str
    conversation_id: str | None = None

    @field_validator("message")
    @classmethod
    def _sanitize_message(cls, v: str) -> str:
        from app.core.sanitizer import sanitize_chat_message
        return sanitize_chat_message(v)


class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    content: str
    tool_calls: dict | None = None
    token_count: int | None = None


# ─── Tool Schemas ─────────────────────────────────────────────────────────────

class ToolInfo(BaseModel):
    id: str
    name: str
    description: str
    category: str  # os, slack, web, custom
    is_dangerous: bool = False


# ─── Ollama Schemas ───────────────────────────────────────────────────────────

class OllamaModel(BaseModel):
    name: str
    size: str
    modified_at: str
    details: dict | None = None


# ─── Groq Schemas ─────────────────────────────────────────────────────────────

class GroqModel(BaseModel):
    id: str
    name: str
    context_length: int | None = None
    description: str | None = None


# ─── System Schemas ───────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str
    ollama_connected: bool
    db_connected: bool
    redis_connected: bool


# ─── Monitor schemas ──────────────────────────────────────────────────────────

class ModelUsageResponse(BaseModel):
    provider: str
    model: str
    request_count: int

    model_config = {"from_attributes": True}


class ModelLimitUpdate(BaseModel):
    model: str = Field(default="*")
    daily_limit: int = Field(..., ge=0)


class ModelLimitResponse(BaseModel):
    provider: str
    model: str
    daily_limit: int

    model_config = {"from_attributes": True}


class MonitorUsageOverview(BaseModel):
    usages: list[ModelUsageResponse]
    limits: list[ModelLimitResponse]


# ─── Job Schemas ──────────────────────────────────────────────────────────────

class JobCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    execution_type: str  # prompt, workflow, n8n_workflow, docker_script
    target_id: str | None = None
    prompt_text: str | None = None
    n8n_webhook_url: str | None = None
    script_name: str | None = None
    cron_expression: str
    timezone: str = "America/Los_Angeles"
    is_active: bool = True
    notify_email: str | None = None  # If set, email job output on completion
    notify_telegram_chat_id: str | None = None  # If set, telegram job output on completion

class JobUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    execution_type: str | None = None
    target_id: str | None = None
    prompt_text: str | None = None
    n8n_webhook_url: str | None = None
    script_name: str | None = None
    cron_expression: str | None = None
    timezone: str | None = None
    is_active: bool | None = None
    notify_email: str | None = None
    notify_telegram_chat_id: str | None = None

class JobResponse(BaseModel):
    id: str
    name: str
    description: str | None
    execution_type: str
    target_id: str | None
    prompt_text: str | None
    n8n_webhook_url: str | None
    script_name: str | None
    cron_expression: str
    timezone: str
    is_active: bool
    notify_email: str | None
    notify_telegram_chat_id: str | None
    last_run_at: datetime | None
    last_run_status: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Batch Job Schemas ────────────────────────────────────────────────────────

class BatchJobCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    job_ids: list[str] = Field(default_factory=list)
    cron_expression: str
    timezone: str = "America/Los_Angeles"
    execution_mode: str = "parallel"  # "parallel" | "sequential"
    is_active: bool = True
    notify_email: str | None = None
    notify_telegram_chat_id: str | None = None


class BatchJobUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    job_ids: list[str] | None = None
    cron_expression: str | None = None
    timezone: str | None = None
    execution_mode: str | None = None
    is_active: bool | None = None
    notify_email: str | None = None
    notify_telegram_chat_id: str | None = None


class BatchJobResponse(BaseModel):
    id: str
    name: str
    description: str | None
    job_ids: list[str]
    cron_expression: str
    timezone: str
    execution_mode: str
    is_active: bool
    notify_email: str | None
    notify_telegram_chat_id: str | None
    last_run_at: datetime | None
    last_run_status: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BatchJobRunResponse(BaseModel):
    id: str
    batch_job_id: str
    started_at: datetime
    completed_at: datetime | None
    status: str
    results: dict

    model_config = {"from_attributes": True}


# ─── MCP Server Schemas ──────────────────────────────────────────────────────

class MCPServerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    transport_type: str = "stdio"  # stdio, sse, streamable_http
    command: str | None = None
    args: list[str] = []
    url: str | None = None
    env_vars: dict[str, str] = {}
    headers: dict[str, str] = {}
    icon: str | None = None
    tags: list[str] = []

class MCPServerUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    transport_type: str | None = None
    command: str | None = None
    args: list[str] | None = None
    url: str | None = None
    env_vars: dict[str, str] | None = None
    headers: dict[str, str] | None = None
    is_active: bool | None = None
    icon: str | None = None
    tags: list[str] | None = None

class MCPServerResponse(BaseModel):
    id: str
    name: str
    description: str | None
    transport_type: str
    command: str | None
    args: list[str] | None
    url: str | None
    env_vars: dict[str, str] | None
    headers: dict[str, str] | None
    is_active: bool
    status: str
    tools: list | None
    resources: list | None
    prompts: list | None
    icon: str | None
    tags: list | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Project Schemas ──────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    status: ProjectStatus = ProjectStatus.active
    color: str | None = None
    icon: str | None = None
    default_agent_id: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    status: ProjectStatus | None = None
    color: str | None = None
    icon: str | None = None
    default_agent_id: str | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    slug: str | None
    description: str | None
    status: str
    color: str | None
    icon: str | None
    owner_user_id: str | None
    default_agent_id: str | None
    memory_count: int
    conversation_count: int
    last_active_at: datetime | None
    compaction_summary: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectDecisionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    decision: str
    reasoning: str
    importance: str = "medium"
    alternatives_considered: list[str] | None = None
    tags: list[str] | None = None
    data_points: dict | None = None
    conversation_id: str | None = None
    agent_id: str | None = None


class ProjectDecisionUpdate(BaseModel):
    title: str | None = None
    decision: str | None = None
    reasoning: str | None = None
    importance: str | None = None
    tags: list[str] | None = None
    data_points: dict | None = None
    is_superseded: bool | None = None
    superseded_by_id: str | None = None


class ProjectDecisionResponse(BaseModel):
    id: str
    project_id: str
    title: str
    decision: str
    reasoning: str
    alternatives_considered: list[str] | None
    importance: str
    tags: list
    data_points: dict | None
    conversation_id: str | None
    agent_id: str | None
    created_by_user_id: str | None
    is_superseded: bool
    superseded_by_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectFileResponse(BaseModel):
    id: str
    project_id: str
    file_name: str
    file_path: str
    file_size: int
    mime_type: str | None
    description: str | None
    uploaded_by_user_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CompactionResultResponse(BaseModel):
    decay_updated: int = 0
    consolidated: int = 0
    conversations_summarized: int = 0


# ─── Task Schemas ─────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    status: TaskStatus = TaskStatus.backlog
    priority: TaskPriority = TaskPriority.medium
    project_id: str | None = None
    parent_task_id: str | None = None
    assignee_agent_id: str | None = None
    assignee_user_id: str | None = None
    due_date: datetime | None = None
    notes: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=500)
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    project_id: str | None = None
    parent_task_id: str | None = None
    assignee_agent_id: str | None = None
    assignee_user_id: str | None = None
    due_date: datetime | None = None
    notes: str | None = None


class TaskResponse(BaseModel):
    id: str
    title: str
    description: str | None
    status: str
    priority: str
    project_id: str | None
    parent_task_id: str | None
    assignee_agent_id: str | None
    assignee_user_id: str | None
    creator_agent_id: str | None
    creator_user_id: str | None
    due_date: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Discussion Schemas ───────────────────────────────────────────────────────

class DiscussionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    topic: str = Field(..., min_length=5)
    type: DiscussionType = DiscussionType.brainstorm
    participant_agent_ids: list[str] = Field(..., min_length=1)
    moderator_agent_id: str | None = None
    max_rounds: int = Field(2, ge=1, le=5)
    task_id: str | None = None


class DiscussionUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    topic: str | None = None
    type: DiscussionType | None = None
    participant_agent_ids: list[str] | None = None
    moderator_agent_id: str | None = None
    max_rounds: int | None = Field(None, ge=1, le=5)


class DiscussionResponse(BaseModel):
    id: str
    title: str
    topic: str
    type: str
    status: str
    participant_agent_ids: list
    moderator_agent_id: str | None
    messages: list
    summary: str | None
    action_items: list | None
    max_rounds: int
    task_id: str | None
    created_by_user_id: str | None
    created_by_agent_id: str | None
    concluded_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Approval Request Schemas ─────────────────────────────────────────────────

class ApprovalRequestCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    description: str | None = None
    category: str = "general"
    risk_level: str = "medium"
    context: dict | None = None
    action_payload: dict | None = None
    requester_agent_id: str | None = None
    workflow_id: str | None = None
    node_id: str | None = None
    expires_in_minutes: int | None = None


class ApprovalRequestResponse(BaseModel):
    id: str
    title: str
    description: str | None
    category: str | None
    risk_level: str | None
    context: dict | None
    action_payload: dict | None
    status: str
    requester_agent_id: str | None
    workflow_id: str | None
    node_id: str | None
    reviewer_user_id: str | None
    reviewer_note: str | None
    decided_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApprovalDecision(BaseModel):
    note: str | None = None


# ─── Knowledge Base / RAG Schemas ─────────────────────────────────────────────

class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    is_shared: bool = True


class KnowledgeBaseResponse(BaseModel):
    id: str
    name: str
    description: str | None
    is_shared: bool
    owner_user_id: str | None
    document_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentIngestRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    source_type: str  # "url" or "text"
    source_url: str | None = None
    content: str | None = None


class DocumentResponse(BaseModel):
    id: str
    knowledge_base_id: str
    title: str
    source_type: str
    source_url: str | None
    file_name: str | None
    status: str
    chunk_count: int
    token_count: int
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class KBSearchResult(BaseModel):
    chunk_id: str
    content: str
    score: float
    document_id: str
    document_title: str
    source_url: str | None
    knowledge_base_id: str


# ─── Email Schemas ─────────────────────────────────────────────────────────────

class EmailConfigCreate(BaseModel):
    agent_id: str | None = None
    label: str | None = None
    provider: str = "SMTP"
    google_email: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_from_name: str | None = None
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    imap_host: str | None = None
    imap_port: int = 993
    imap_username: str | None = None
    imap_password: str | None = None
    imap_use_ssl: bool = True
    imap_folder: str = "INBOX"


class EmailConfigUpdate(BaseModel):
    agent_id: str | None = None
    label: str | None = None
    provider: str | None = None
    google_email: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None  # Only set to update the password
    smtp_from_email: str | None = None
    smtp_from_name: str | None = None
    smtp_use_tls: bool | None = None
    smtp_use_ssl: bool | None = None
    imap_host: str | None = None
    imap_port: int | None = None
    imap_username: str | None = None
    imap_password: str | None = None
    imap_use_ssl: bool | None = None
    imap_folder: str | None = None


class EmailConfigResponse(BaseModel):
    id: str
    agent_id: str | None
    label: str | None
    provider: str
    google_email: str | None
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_from_email: str | None
    smtp_from_name: str | None
    smtp_use_tls: bool
    smtp_use_ssl: bool
    imap_host: str | None
    imap_port: int
    imap_username: str | None
    imap_use_ssl: bool
    imap_folder: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EmailTestRequest(BaseModel):
    to: str = Field(..., description="Recipient address for the test email")


class EmailWhitelistCreate(BaseModel):
    agent_id: str | None = None
    email_address: str = Field(..., min_length=5)
    label: str | None = None
    is_active: bool = True


class EmailWhitelistResponse(BaseModel):
    id: str
    agent_id: str | None
    email_address: str
    label: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Webhook Schemas ───────────────────────────────────────────────────────────

class WebhookSubscriptionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    url: AnyHttpUrl
    secret: str | None = None
    events: list[str] = Field(default_factory=lambda: ["*"])
    is_active: bool = True
    agent_id: str | None = None
    headers: dict | None = None


class WebhookSubscriptionUpdate(BaseModel):
    name: str | None = None
    url: AnyHttpUrl | None = None
    secret: str | None = None
    events: list[str] | None = None
    is_active: bool | None = None
    agent_id: str | None = None
    headers: dict | None = None


class WebhookSubscriptionResponse(BaseModel):
    id: str
    name: str
    url: str
    events: list
    is_active: bool
    agent_id: str | None
    headers: dict | None
    delivery_count: int
    failure_count: int
    last_delivery_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WebhookDeliveryResponse(BaseModel):
    id: str
    subscription_id: str
    event_type: str
    payload: dict
    status: str
    response_status: int | None
    response_body: str | None
    attempt_count: int
    delivered_at: datetime | None
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Skill Schemas ─────────────────────────────────────────────────────────────

class SkillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    version: str = "1.0.0"
    category: str = "general"
    prompt_fragment: str = Field(..., min_length=1)
    required_tool_ids: list[str] = []
    config_schema: dict | None = None
    icon: str | None = None
    color: str | None = None


class SkillUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    version: str | None = None
    category: str | None = None
    prompt_fragment: str | None = None
    required_tool_ids: list[str] | None = None
    config_schema: dict | None = None
    icon: str | None = None
    color: str | None = None
    is_active: bool | None = None


class SkillResponse(BaseModel):
    id: str
    name: str
    description: str | None
    version: str
    category: str
    prompt_fragment: str
    required_tool_ids: list
    config_schema: dict | None
    source: str
    icon: str | None
    color: str | None
    is_active: bool
    created_by_agent_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentSkillCreate(BaseModel):
    skill_id: str
    priority: int = 0
    config_overrides: dict = {}


class AgentSkillUpdate(BaseModel):
    priority: int | None = None
    config_overrides: dict | None = None
    is_active: bool | None = None


class AgentSkillResponse(BaseModel):
    id: str
    agent_id: str
    skill_id: str
    priority: int
    config_overrides: dict
    is_active: bool
    skill: SkillResponse
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RoleSkillCreate(BaseModel):
    skill_id: str
    priority: int = 0
    config_overrides: dict = {}


class RoleSkillResponse(BaseModel):
    id: str
    role_id: str
    skill_id: str
    priority: int
    config_overrides: dict
    skill: SkillResponse
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SkillExportBundle(BaseModel):
    version: str = "1.0"
    exported_at: str
    skills: list[SkillResponse]


# ─── Task Decompose Schema ─────────────────────────────────────────────────────

class TaskDecomposeRequest(BaseModel):
    agent_id: str | None = None
    guidance: str | None = None
    max_subtasks: int = Field(5, ge=1, le=20)


# ─── API Key Schemas ──────────────────────────────────────────────────────────

class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    expires_in_days: int | None = Field(None, ge=1, le=365)


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    is_active: bool
    last_used_at: datetime | None
    expires_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyCreatedResponse(ApiKeyResponse):
    key: str  # Full key — shown once only


# ─── Integration Schemas ──────────────────────────────────────────────────────

class IntegrationCreate(BaseModel):
    type: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    agent_id: str | None = None
    credentials: dict = Field(default_factory=dict)  # plain — will be encrypted server-side
    extra_config: dict = Field(default_factory=dict)
    is_active: bool = True


class IntegrationUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    agent_id: str | None = None
    credentials: dict | None = None  # if provided, re-encrypts
    extra_config: dict | None = None
    is_active: bool | None = None


class IntegrationResponse(BaseModel):
    id: str
    type: str
    name: str
    agent_id: str | None
    extra_config: dict
    is_active: bool
    has_credentials: bool  # True if credentials_enc is set (never returns the actual secrets)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Evolve Schemas ──────────────────────────────────────────────────────────

class EvolveSuggestionResponse(BaseModel):
    id: str
    evolve_agent_id: str | None
    category: str
    source: str
    title: str
    description: str
    evidence: dict | None
    priority: str
    status: str
    approval_request_id: str | None
    action_type: str | None
    action_config: dict | None
    result_id: str | None
    result_type: str | None
    run_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EvolveRunResponse(BaseModel):
    id: str
    run_type: str
    started_at: datetime | None
    completed_at: datetime | None
    status: str
    stats: dict | None
    error_log: str | None
    suggestions_generated: int
    created_at: datetime

    model_config = {"from_attributes": True}


class EvolveDashboardResponse(BaseModel):
    health_score: float
    suggestion_counts: dict
    total_suggestions: int
    pending_count: int
    approved_count: int
    rejected_count: int
    competitor_gaps: int
    recent_runs: list


# ─── Alert Schemas ───────────────────────────────────────────────────────────

class AlertRecordResponse(BaseModel):
    id: str
    rule_id: str | None
    rule_type: str
    severity: str
    status: str
    title: str
    message: str
    agent_id: str | None
    fingerprint: str
    context: dict | None
    fired_at: datetime | None
    acknowledged_at: datetime | None
    acknowledged_by: str | None
    resolved_at: datetime | None
    resolved_by: str | None
    notification_sent: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    rule_type: str = Field(..., description="error_rate|latency_p95|agent_failure_streak|quota_usage|agent_down")
    severity: str = "warning"
    agent_id: str | None = None
    threshold: float
    window_minutes: int = 10
    cooldown_minutes: int = 30
    notify_webhook: bool = True
    notify_websocket: bool = True
    notify_email: str | None = None


class AlertRuleUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    severity: str | None = None
    threshold: float | None = None
    window_minutes: int | None = None
    cooldown_minutes: int | None = None
    notify_webhook: bool | None = None
    notify_websocket: bool | None = None
    notify_email: str | None = None


class AlertRuleResponse(BaseModel):
    id: str
    name: str
    rule_type: str
    is_active: bool
    severity: str
    agent_id: str | None
    threshold: float
    window_minutes: int
    cooldown_minutes: int
    notify_webhook: bool
    notify_websocket: bool
    notify_email: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AlertSummaryResponse(BaseModel):
    firing_count: int
    acknowledged_count: int
    critical_count: int
    warning_count: int
