"""Application configuration using Pydantic BaseSettings."""

import logging

from cryptography.fernet import Fernet
from pydantic import field_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Global application settings loaded from environment variables."""

    # App
    app_name: str = "Sutra"
    debug: bool = False  # Must be explicitly enabled; never default to True in prod

    # Database
    database_url: str = "postgresql+asyncpg://sutra:sutra_dev@localhost:5432/sutra"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"

    # LLM API Keys (optional — managed via UI but can be seeded from env)
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    openrouter_api_key: str = ""
    perplexity_api_key: str = ""
    groq_api_key: str = ""
    clod_api_key: str = ""
    nvidia_nim_api_key: str = ""
    google_dev_api_mode: str = "N"

    # Google OAuth 2.0 (for Gmail Integration)
    google_client_id: str = ""
    google_client_secret: str = ""

    # GitHub Integration
    github_token: str | None = None

    # Slack
    slack_bot_token: str = ""
    slack_signing_secret: str = ""
    slack_app_token: str = ""  # For Socket Mode

    # WhatsApp (Meta Cloud API via pywa)
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_verify_token: str = "sutra-whatsapp-verify"  # Custom string for webhook verification
    whatsapp_app_secret: str = ""  # For validating webhook signatures (optional)

    # Telegram
    telegram_bot_token: str = ""
    telegram_default_chat_id: str = ""  # Default chat/user ID for proactive agent messages

    # Security — both MUST be set via environment / .env
    secret_key: str = ""
    encryption_key: str = ""  # For API key vault — auto-generated if empty

    # CORS — comma-separated list of allowed origins
    cors_origins: str = (
        "http://localhost:3000,http://localhost:3001,"
        "http://127.0.0.1:3000,http://127.0.0.1:3001"
    )

    # Content-Security-Policy header value (configurable per environment)
    csp_header: str = "default-src 'none'; frame-ancestors 'none'"

    # JWT
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7

    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Agent Tools configuration
    allowed_agent_file_paths: str = ""  # Comma-separated list of allowed absolute paths for agent file access

    # Browser Automation — playbook directory (relative to backend/ or absolute)
    playbooks_dir: str = "data/playbooks"

    # Scheduled check-ins — cron expression in America/Los_Angeles timezone
    # Default: 8:00 AM Pacific (handles DST automatically)
    checkin_cron: str = "0 8 * * *"

    # Forge — autonomous feature implementation engine
    forge_max_concurrent: int = 1             # max parallel forge requests
    forge_workspace_root: str = "/tmp/sutra-forge"  # temp clone directory
    forge_default_provider: str = "groq"      # default LLM provider for forge coding
    forge_default_model: str = "qwen/qwen3-32b"  # default LLM model for forge coding
    forge_recursion_limit: int = 25           # LangGraph step limit for coding agent
    forge_rate_limit_max_retries: int = 5     # max retries on rate-limit errors
    forge_rate_limit_base_delay: float = 2.0  # base delay (seconds) for exponential backoff
    # Forge queue scheduler — cron in America/Los_Angeles (PST/PDT)
    # Default: 7:00 PM Pacific every day  →  "0 19 * * *"
    forge_queue_cron: str = "0 19 * * *"

    # Social Pulse — trending content research
    social_pulse_cron: str = "*/30 * * * *"  # every 30 min
    social_pulse_default_subreddits: str = "technology,programming,business,marketing,worldnews"

    # SMTP Notifications
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = ""

    # ── Resilience & Performance (Phase 5.2 / 5.4) ─────────────────────────
    # LLM retry
    llm_retry_max_retries: int = 2
    llm_retry_base_delay: float = 1.0
    llm_retry_max_delay: float = 10.0

    # Circuit breaker
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_window_seconds: int = 60
    circuit_breaker_cooldown_seconds: int = 30

    # Agent watchdog
    watchdog_check_interval: int = 60
    watchdog_timeout_multiplier: int = 3
    watchdog_max_restarts: int = 3

    # Prompt cache
    prompt_cache_ttl: int = 1800          # seconds (30 min)
    prompt_cache_max_messages: int = 3    # last N messages in cache key

    # Conversation windowing
    conversation_window_size: int = 20
    summary_llm_provider: str = "groq"
    summary_llm_model: str = "llama-3.1-8b-instant"
    summary_cache_ttl: int = 3600         # 1 hour

    # ── Memory (Phase 5.1) ─────────────────────────────────────────────────
    memory_decay_half_life_days: int = 7
    memory_consolidation_age_days: int = 14
    memory_consolidation_decay_threshold: float = 0.1
    memory_archival_delete_days: int = 90
    memory_core_max_tokens: int = 2000
    memory_maintenance_cron: str = "0 3 * * *"

    # Project memory
    project_compaction_cron: str = "30 3 * * *"
    project_files_root: str = "data/projects"

    # Embedding batcher
    embedding_batch_size: int = 20
    embedding_flush_interval: float = 0.3

    # ── Evolve — self-improving platform agent ─────────────────────────────
    evolve_daily_cron: str = "0 6 * * *"  # 6 AM PT daily
    evolve_competitor_cron: str = "0 9 * * 1"  # 9 AM PT Mondays
    evolve_competitor_repos: str = "crewAIInc/crewAI,microsoft/autogen,langchain-ai/langgraph,langgenius/dify"

    # ── Alerting ────────────────────────────────────────────────────────
    alert_evaluation_interval_minutes: int = 30
    alert_default_cooldown_minutes: int = 30
    alert_auto_resolve_enabled: str = "true"

    # ── MLflow / LLMOps Tracing ───────────────────────────────────────────
    mlflow_enabled: bool = False
    mlflow_tracking_uri: str = "http://mlflow:5000"
    mlflow_experiment: str = "sutra-agent-runs"
    rag_eval_enabled: bool = False
    # Judge model used by the LLM-as-judge RAG eval loop. Only invoked when
    # rag_eval_enabled=True AND the eval CLI/Celery task is explicitly run.
    # Format: "<provider>/<model>". Kept cheap by default.
    rag_eval_judge_provider: str = "anthropic"
    rag_eval_judge_model: str = "claude-haiku-4-5-20251001"

    # ── Rate Limits ────────────────────────────────────────────────────────
    rate_limit_chat: str = "200/hour"
    rate_limit_auth_login: str = "10/hour"
    rate_limit_auth_register: str = "20/hour"
    rate_limit_auth_refresh: str = "60/hour"

    @field_validator("encryption_key", mode="before")
    @classmethod
    def ensure_encryption_key(cls, v: str) -> str:
        """Auto-generate an ephemeral Fernet key if ENCRYPTION_KEY is not set."""
        if not v:
            key = Fernet.generate_key().decode()
            logger.warning(
                "ENCRYPTION_KEY is not set — generated an ephemeral key. "
                "LLM API keys encrypted this session will NOT be recoverable after restart. "
                "Set ENCRYPTION_KEY in .env to persist encrypted secrets."
            )
            return key
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",  # Allow extra environment variables without crashing
    }


settings = Settings()
