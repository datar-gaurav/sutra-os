"""Environment variables API — read/write .env settings securely from the UI.

Security model:
- Secret values (API keys, tokens, passwords) are stored AES-256 encrypted
  via the Fernet vault.  They are NEVER returned as plaintext — only a masked
  hint (e.g. "sk-••••••••••••abcd") is sent to the client.
- Non-secret values (URLs, cron expressions, feature flags) are stored
  as plaintext and returned as-is.
- The write endpoint accepts the full plaintext once; it is encrypted before
  being persisted.  The read endpoint never decrypts secrets.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.core.vault import encrypt_secret
from app.db.session import get_db
from app.models.env_var import EnvVar
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/settings/env", tags=["settings"])

# ─── Schema definition ────────────────────────────────────────────────────────
# Each entry describes one .env variable:
#   key        – env var name (also the DB primary key)
#   label      – human-readable display name
#   group      – UI section header
#   is_secret  – if True, value is encrypted + masked in API responses
#   description – tooltip shown in the UI
#   placeholder – example value shown when empty

ENV_VAR_SCHEMA: list[dict[str, Any]] = [
    # ── Database ──────────────────────────────────────────────────────────
    {
        "key": "DATABASE_URL", "group": "Infrastructure",
        "label": "Database URL", "is_secret": False,
        "description": "PostgreSQL async connection string",
        "placeholder": "postgresql+asyncpg://user:pass@host:5432/db",
    },
    {
        "key": "REDIS_URL", "group": "Infrastructure",
        "label": "Redis URL", "is_secret": False,
        "description": "Redis connection string (caching, queues)",
        "placeholder": "redis://localhost:6379/0",
    },
    {
        "key": "OLLAMA_BASE_URL", "group": "Infrastructure",
        "label": "Ollama Base URL", "is_secret": False,
        "description": "Local Ollama LLM server URL",
        "placeholder": "http://localhost:11434",
    },

    # ── Security ──────────────────────────────────────────────────────────
    {
        "key": "SECRET_KEY", "group": "Security",
        "label": "App Secret Key", "is_secret": True,
        "description": "JWT signing secret — change in production",
        "placeholder": "change-me-in-production",
    },
    {
        "key": "ENCRYPTION_KEY", "group": "Security",
        "label": "Vault Encryption Key", "is_secret": True,
        "description": "Fernet key used to encrypt API keys in the vault (base64)",
        "placeholder": "auto-generated if empty",
    },

    # ── LLM API Keys ──────────────────────────────────────────────────────
    {
        "key": "OPENAI_API_KEY", "group": "LLM API Keys",
        "label": "OpenAI API Key", "is_secret": True,
        "description": "For GPT-4o, GPT-4o-mini, embeddings",
        "placeholder": "sk-...",
    },
    {
        "key": "ANTHROPIC_API_KEY", "group": "LLM API Keys",
        "label": "Anthropic API Key", "is_secret": True,
        "description": "For Claude models",
        "placeholder": "sk-ant-...",
    },
    {
        "key": "GOOGLE_API_KEY", "group": "LLM API Keys",
        "label": "Google API Key", "is_secret": True,
        "description": "For Gemini models",
        "placeholder": "AIza...",
    },
    {
        "key": "OPENROUTER_API_KEY", "group": "LLM API Keys",
        "label": "OpenRouter API Key", "is_secret": True,
        "description": "For 200+ models via openrouter.ai",
        "placeholder": "sk-or-v1-...",
    },
    {
        "key": "PERPLEXITY_API_KEY", "group": "LLM API Keys",
        "label": "Perplexity API Key", "is_secret": True,
        "description": "For Perplexity online search models",
        "placeholder": "pplx-...",
    },
    {
        "key": "GROQ_API_KEY", "group": "LLM API Keys",
        "label": "Groq API Key", "is_secret": True,
        "description": "For ultra-fast Llama/Qwen inference",
        "placeholder": "gsk_...",
    },

    # ── GitHub ────────────────────────────────────────────────────────────
    {
        "key": "GITHUB_TOKEN", "group": "Integrations",
        "label": "GitHub Token", "is_secret": True,
        "description": "Personal access token for Forge PR creation",
        "placeholder": "github_pat_...",
    },

    # ── Slack ─────────────────────────────────────────────────────────────
    {
        "key": "SLACK_BOT_TOKEN", "group": "Integrations",
        "label": "Slack Bot Token", "is_secret": True,
        "description": "xoxb-... token for the Slack bot",
        "placeholder": "xoxb-...",
    },
    {
        "key": "SLACK_SIGNING_SECRET", "group": "Integrations",
        "label": "Slack Signing Secret", "is_secret": True,
        "description": "Used to verify Slack request signatures",
        "placeholder": "...",
    },
    {
        "key": "SLACK_APP_TOKEN", "group": "Integrations",
        "label": "Slack App (Socket) Token", "is_secret": True,
        "description": "xapp-... token for Socket Mode",
        "placeholder": "xapp-...",
    },

    # ── Telegram ──────────────────────────────────────────────────────────
    {
        "key": "TELEGRAM_BOT_TOKEN", "group": "Integrations",
        "label": "Telegram Bot Token", "is_secret": True,
        "description": "Token for the Telegram bot (from @BotFather)",
        "placeholder": "123456:ABC-...",
    },
    {
        "key": "TELEGRAM_DEFAULT_CHAT_ID", "group": "Integrations",
        "label": "Telegram Default Chat ID", "is_secret": False,
        "description": "Default chat/user ID for proactive agent notifications",
        "placeholder": "7910625389",
    },

    # ── WhatsApp ──────────────────────────────────────────────────────────
    {
        "key": "WHATSAPP_PHONE_NUMBER_ID", "group": "Integrations",
        "label": "WhatsApp Phone Number ID", "is_secret": False,
        "description": "Meta Cloud API phone number ID",
        "placeholder": "...",
    },
    {
        "key": "WHATSAPP_ACCESS_TOKEN", "group": "Integrations",
        "label": "WhatsApp Access Token", "is_secret": True,
        "description": "Meta Cloud API access token",
        "placeholder": "EAAxx...",
    },
    {
        "key": "WHATSAPP_VERIFY_TOKEN", "group": "Integrations",
        "label": "WhatsApp Webhook Verify Token", "is_secret": False,
        "description": "Custom string for webhook verification",
        "placeholder": "sutra-whatsapp-verify",
    },
    {
        "key": "WHATSAPP_APP_SECRET", "group": "Integrations",
        "label": "WhatsApp App Secret", "is_secret": True,
        "description": "Used to validate webhook payload signatures",
        "placeholder": "...",
    },

    # ── Google OAuth ──────────────────────────────────────────────────────
    {
        "key": "GOOGLE_CLIENT_ID", "group": "Integrations",
        "label": "Google OAuth Client ID", "is_secret": False,
        "description": "For Gmail integration and Google OAuth login",
        "placeholder": "xxx.apps.googleusercontent.com",
    },
    {
        "key": "GOOGLE_CLIENT_SECRET", "group": "Integrations",
        "label": "Google OAuth Client Secret", "is_secret": True,
        "description": "Google OAuth 2.0 client secret",
        "placeholder": "GOCSPX-...",
    },

    # ── SMTP ──────────────────────────────────────────────────────────────
    {
        "key": "SMTP_HOST", "group": "Email (SMTP)",
        "label": "SMTP Host", "is_secret": False,
        "description": "Outgoing mail server hostname",
        "placeholder": "smtppro.zoho.com",
    },
    {
        "key": "SMTP_PORT", "group": "Email (SMTP)",
        "label": "SMTP Port", "is_secret": False,
        "description": "Outgoing mail server port (usually 587 or 465)",
        "placeholder": "587",
    },
    {
        "key": "SMTP_USER", "group": "Email (SMTP)",
        "label": "SMTP Username", "is_secret": False,
        "description": "SMTP authentication username (usually your email)",
        "placeholder": "me@example.com",
    },
    {
        "key": "SMTP_PASS", "group": "Email (SMTP)",
        "label": "SMTP Password", "is_secret": True,
        "description": "SMTP authentication password or app password",
        "placeholder": "app-password",
    },
    {
        "key": "SMTP_FROM", "group": "Email (SMTP)",
        "label": "From Email", "is_secret": False,
        "description": "Email address used as the sender",
        "placeholder": "me@example.com",
    },

    # ── Scheduled jobs ────────────────────────────────────────────────────
    {
        "key": "CHECKIN_CRON", "group": "Scheduler",
        "label": "Check-in Schedule (cron)", "is_secret": False,
        "description": "Daily agent check-in cron (America/Los_Angeles). Default: 8 AM PT",
        "placeholder": "0 8 * * *",
    },
    {
        "key": "FORGE_QUEUE_CRON", "group": "Scheduler",
        "label": "Forge Queue Schedule (cron)", "is_secret": False,
        "description": "When the Forge queue runner fires (America/Los_Angeles). Default: 7 PM PT",
        "placeholder": "0 19 * * *",
    },

    # ── Agent Tools ───────────────────────────────────────────────────────
    {
        "key": "ALLOWED_AGENT_FILE_PATHS", "group": "Agent Tools",
        "label": "Allowed File Paths", "is_secret": False,
        "description": "Comma-separated absolute paths agents may read/write",
        "placeholder": "/home/user/projects",
    },
]

# Build a fast lookup map
_SCHEMA_MAP: dict[str, dict] = {s["key"]: s for s in ENV_VAR_SCHEMA}


def _mask(value: str) -> str:
    """Return a masked version that shows only the last 4 chars."""
    if not value:
        return ""
    visible = value[-4:] if len(value) >= 4 else value
    bullets = "•" * min(12, max(4, len(value) - 4))
    return f"{bullets}{visible}"


# ─── Pydantic schemas ─────────────────────────────────────────────────────────

class EnvVarItem(BaseModel):
    """Returned by the list/get endpoint — never exposes secret plaintext."""
    key: str
    group: str
    label: str
    description: str
    placeholder: str
    is_secret: bool
    is_set: bool          # True if a value exists in DB (non-empty)
    masked_value: str     # "••••••••abcd" for secrets, plaintext for non-secrets
    source: str           # "db" | "env" | "default"


class EnvVarWrite(BaseModel):
    key: str
    value: str  # always plaintext from the client


class EnvVarBulkWrite(BaseModel):
    vars: list[EnvVarWrite]


# ─── Helper ───────────────────────────────────────────────────────────────────

async def _load_db_vars(db: AsyncSession) -> dict[str, "EnvVar"]:
    result = await db.execute(select(EnvVar))
    return {row.key: row for row in result.scalars().all()}


def _build_item(schema: dict, db_row: "EnvVar | None") -> EnvVarItem:
    """Build a response item from schema + optional DB row."""
    import os
    key = schema["key"]
    is_secret = schema["is_secret"]

    if db_row and db_row.value:
        # DB value takes priority
        if is_secret:
            # We don't decrypt; compute mask from ciphertext length proxy
            masked = _mask("*" * 20 + db_row.value[-4:])
        else:
            masked = db_row.value
        source = "db"
        is_set = True
    else:
        # Fall back to actual process environment (from .env / real env)
        env_val = os.environ.get(key, "")
        if env_val:
            masked = _mask(env_val) if is_secret else env_val
            source = "env"
            is_set = True
        else:
            masked = ""
            source = "default"
            is_set = False

    return EnvVarItem(
        key=key,
        group=schema["group"],
        label=schema["label"],
        description=schema["description"],
        placeholder=schema["placeholder"],
        is_secret=is_secret,
        is_set=is_set,
        masked_value=masked,
        source=source,
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[EnvVarItem])
async def list_env_vars(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all configurable env vars with their masked values and source."""
    db_rows = await _load_db_vars(db)
    return [
        _build_item(schema, db_rows.get(schema["key"]))
        for schema in ENV_VAR_SCHEMA
    ]


@router.put("/", response_model=list[EnvVarItem])
async def upsert_env_vars(
    payload: EnvVarBulkWrite,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create or update one or more env vars.

    Secret values are encrypted before storage. The plaintext is NEVER logged.
    Returns the updated list with masked values.
    """
    for item in payload.vars:
        key = item.key
        schema = _SCHEMA_MAP.get(key)
        if not schema:
            raise HTTPException(status_code=400, detail=f"Unknown env var key: {key!r}")

        is_secret = schema["is_secret"]
        stored_value = encrypt_secret(item.value) if is_secret else item.value

        # Upsert
        row = await db.get(EnvVar, key)
        if row:
            row.value = stored_value
            row.is_secret = is_secret
        else:
            db.add(EnvVar(key=key, value=stored_value, is_secret=is_secret))

        # Also update the live process environment so config.py and llm_registry
        # pick up the value on the next request without requiring a restart.
        import os
        os.environ[key] = item.value

    await db.commit()

    # Return fresh list
    db_rows = await _load_db_vars(db)
    return [
        _build_item(schema, db_rows.get(schema["key"]))
        for schema in ENV_VAR_SCHEMA
    ]


@router.delete("/{key}")
async def delete_env_var(
    key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a stored env var (reverts to .env file / process environment)."""
    if key not in _SCHEMA_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown env var key: {key!r}")
    row = await db.get(EnvVar, key)
    if row:
        await db.delete(row)
        await db.commit()
    return {"ok": True, "key": key}
