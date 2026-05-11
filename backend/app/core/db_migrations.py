"""Lightweight schema migrations for dev mode (no Alembic).

Adds columns that were added to ORM models after the table was first created.
Each migration is idempotent — safe to run on every startup.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Each entry: (description, SQL)
# Uses PostgreSQL "ADD COLUMN IF NOT EXISTS" (supported in PG 9.6+).
MIGRATIONS: list[tuple[str, str]] = [
    # ── Memory three-tier fields (Phase 5.1) ─────────────────────────────────
    (
        "memories.tier",
        "ALTER TABLE memories ADD COLUMN IF NOT EXISTS tier VARCHAR(10) NOT NULL DEFAULT 'recall'",
    ),
    (
        "memories.decay_score",
        "ALTER TABLE memories ADD COLUMN IF NOT EXISTS decay_score FLOAT NOT NULL DEFAULT 1.0",
    ),
    (
        "memories.source",
        "ALTER TABLE memories ADD COLUMN IF NOT EXISTS source VARCHAR(20) NOT NULL DEFAULT 'auto'",
    ),
    (
        "memories.is_deleted",
        "ALTER TABLE memories ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT false",
    ),
    (
        "memories.deleted_reason",
        "ALTER TABLE memories ADD COLUMN IF NOT EXISTS deleted_reason VARCHAR(200)",
    ),
    (
        "memories.consolidated_from",
        "ALTER TABLE memories ADD COLUMN IF NOT EXISTS consolidated_from JSONB",
    ),
    (
        "memories.ttl_days",
        "ALTER TABLE memories ADD COLUMN IF NOT EXISTS ttl_days INTEGER",
    ),
    # ── Approval request agent tracking ──────────────────────────────────────
    (
        "approval_requests.requester_agent_id",
        "ALTER TABLE approval_requests ADD COLUMN IF NOT EXISTS requester_agent_id VARCHAR(36) REFERENCES agents(id) ON DELETE SET NULL",
    ),
    (
        "approval_requests.workflow_id",
        "ALTER TABLE approval_requests ADD COLUMN IF NOT EXISTS workflow_id VARCHAR(36)",
    ),
    (
        "approval_requests.node_id",
        "ALTER TABLE approval_requests ADD COLUMN IF NOT EXISTS node_id VARCHAR(100)",
    ),
    (
        "approval_requests.category",
        "ALTER TABLE approval_requests ADD COLUMN IF NOT EXISTS category VARCHAR(50) DEFAULT 'general'",
    ),
    (
        "approval_requests.risk_level",
        "ALTER TABLE approval_requests ADD COLUMN IF NOT EXISTS risk_level VARCHAR(20) DEFAULT 'medium'",
    ),
    (
        "approval_requests.context",
        "ALTER TABLE approval_requests ADD COLUMN IF NOT EXISTS context JSONB",
    ),
    (
        "approval_requests.action_payload",
        "ALTER TABLE approval_requests ADD COLUMN IF NOT EXISTS action_payload JSONB",
    ),
    (
        "approval_requests.reviewer_user_id",
        "ALTER TABLE approval_requests ADD COLUMN IF NOT EXISTS reviewer_user_id VARCHAR(36)",
    ),
    (
        "approval_requests.reviewer_note",
        "ALTER TABLE approval_requests ADD COLUMN IF NOT EXISTS reviewer_note TEXT",
    ),
    (
        "approval_requests.decided_at",
        "ALTER TABLE approval_requests ADD COLUMN IF NOT EXISTS decided_at TIMESTAMP",
    ),
    (
        "approval_requests.expires_at",
        "ALTER TABLE approval_requests ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP",
    ),
    # ── Agent fields added post-creation ─────────────────────────────────────
    (
        "agents.folder_id",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS folder_id VARCHAR(36)",
    ),
    (
        "agents.slack_channel_id",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS slack_channel_id VARCHAR(50)",
    ),
    (
        "agents.telegram_chat_id",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS telegram_chat_id VARCHAR(50)",
    ),
    (
        "agents.whatsapp_enabled",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS whatsapp_enabled BOOLEAN NOT NULL DEFAULT false",
    ),
    (
        "agents.telegram_enabled",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS telegram_enabled BOOLEAN NOT NULL DEFAULT false",
    ),
    (
        "agents.online_notification_enabled",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS online_notification_enabled BOOLEAN NOT NULL DEFAULT false",
    ),
    (
        "agents.role_id",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS role_id VARCHAR(36)",
    ),
    (
        "agents.team_id",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS team_id VARCHAR(36)",
    ),
    (
        "agents.reports_to_agent_id",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS reports_to_agent_id VARCHAR(36)",
    ),
    (
        "agents.skills",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS skills JSONB DEFAULT '[]'",
    ),
    (
        "agents.template_id",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS template_id VARCHAR(36)",
    ),
    (
        "agents.is_archived",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT false",
    ),
    (
        "agents.archived_at",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP",
    ),
    (
        "agents.archived_reason",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS archived_reason TEXT",
    ),
    (
        "agents.auto_approve_below",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS auto_approve_below VARCHAR(10)",
    ),
    (
        "agents.max_tool_calls_per_run",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS max_tool_calls_per_run INTEGER NOT NULL DEFAULT 0",
    ),
    (
        "agents.max_tokens_per_day",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS max_tokens_per_day INTEGER NOT NULL DEFAULT 0",
    ),
    (
        "agents.secondary_provider",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS secondary_provider VARCHAR(50)",
    ),
    (
        "agents.secondary_model",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS secondary_model VARCHAR(100)",
    ),
    (
        "agents.fallback_provider",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS fallback_provider VARCHAR(50)",
    ),
    (
        "agents.fallback_model",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS fallback_model VARCHAR(100)",
    ),
    # Widen last_fired_at from VARCHAR(30) to VARCHAR(50) — ISO timestamps are 32 chars
    (
        "agent_triggers.last_fired_at_widen",
        "ALTER TABLE agent_triggers ALTER COLUMN last_fired_at TYPE VARCHAR(50)",
    ),
    # ── Project memory management fields ───────────────────────────────────
    (
        "conversations.project_id",
        "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS project_id VARCHAR(36)",
    ),
    (
        "memories.project_id",
        "ALTER TABLE memories ADD COLUMN IF NOT EXISTS project_id VARCHAR(36)",
    ),
    # ── Token guard: estimated input tokens per trace ────────────────────
    (
        "execution_traces.input_tokens",
        "ALTER TABLE execution_traces ADD COLUMN IF NOT EXISTS input_tokens INTEGER",
    ),
    (
        "projects.slug",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS slug VARCHAR(100)",
    ),
    (
        "projects.color",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS color VARCHAR(20)",
    ),
    (
        "projects.icon",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS icon VARCHAR(50)",
    ),
    (
        "projects.default_agent_id",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS default_agent_id VARCHAR(36)",
    ),
    (
        "projects.files_dir",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS files_dir VARCHAR(500)",
    ),
    (
        "projects.memory_count",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS memory_count INTEGER NOT NULL DEFAULT 0",
    ),
    (
        "projects.conversation_count",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS conversation_count INTEGER NOT NULL DEFAULT 0",
    ),
    (
        "projects.last_active_at",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMP",
    ),
    (
        "projects.compaction_summary",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS compaction_summary TEXT",
    ),
    # ── Purpose-based LLM routing ─────────────────────────────────────────
    (
        "agents.purpose_id",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS purpose_id VARCHAR(36)",
    ),
    # ── Job applications: hiring team / reachable connections ────────────
    (
        "job_applications.people",
        "ALTER TABLE job_applications ADD COLUMN IF NOT EXISTS people JSONB",
    ),
    (
        "job_applications.review_rounds",
        "ALTER TABLE job_applications ADD COLUMN IF NOT EXISTS review_rounds INTEGER NOT NULL DEFAULT 2",
    ),
    (
        "job_applications.review_log",
        "ALTER TABLE job_applications ADD COLUMN IF NOT EXISTS review_log JSONB",
    ),
    # ── Voice integration (per-agent voice settings) ─────────────────────────
    (
        "agents.voice_enabled",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS voice_enabled BOOLEAN NOT NULL DEFAULT false",
    ),
    (
        "agents.voice_id",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS voice_id VARCHAR(100)",
    ),
    (
        "agents.voice_provider_tts",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS voice_provider_tts VARCHAR(50)",
    ),
    (
        "agents.voice_provider_stt",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS voice_provider_stt VARCHAR(50)",
    ),
    (
        "agents.voice_speed",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS voice_speed FLOAT NOT NULL DEFAULT 1.0",
    ),
    (
        "agents.telegram_voice_enabled",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS telegram_voice_enabled BOOLEAN NOT NULL DEFAULT false",
    ),
    (
        "agents.web_voice_enabled",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS web_voice_enabled BOOLEAN NOT NULL DEFAULT false",
    ),
    # ── Skills v2: filesystem-backed manifests + routing fields ──────────────
    (
        "skills.slug",
        "ALTER TABLE skills ADD COLUMN IF NOT EXISTS slug VARCHAR(100)",
    ),
    (
        "skills.slug.backfill",
        "UPDATE skills SET slug = lower(regexp_replace(name, '[^a-zA-Z0-9]+', '-', 'g')) "
        "WHERE slug IS NULL",
    ),
    (
        "skills.slug.unique",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_skills_slug ON skills (slug)",
    ),
    (
        "skills.trigger_embedding",
        "ALTER TABLE skills ADD COLUMN IF NOT EXISTS trigger_embedding TEXT",
    ),
    (
        "skills.trigger_hash",
        "ALTER TABLE skills ADD COLUMN IF NOT EXISTS trigger_hash CHAR(16)",
    ),
    (
        "skills.trigger_embed_model",
        "ALTER TABLE skills ADD COLUMN IF NOT EXISTS trigger_embed_model VARCHAR(50)",
    ),
    (
        "skills.routing_threshold",
        "ALTER TABLE skills ADD COLUMN IF NOT EXISTS routing_threshold FLOAT",
    ),
    (
        "agent_skills.always_load",
        "ALTER TABLE agent_skills ADD COLUMN IF NOT EXISTS always_load BOOLEAN NOT NULL DEFAULT false",
    ),
    (
        "role_skills.always_load",
        "ALTER TABLE role_skills ADD COLUMN IF NOT EXISTS always_load BOOLEAN NOT NULL DEFAULT false",
    ),
    (
        "agents.skill_routing_enabled",
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS skill_routing_enabled BOOLEAN",
    ),
    # Legacy column drops — safe because the orchestrator now reads bodies/tools
    # from the filesystem registry, not these DB fields.
    (
        "skills.drop.prompt_fragment",
        "ALTER TABLE skills DROP COLUMN IF EXISTS prompt_fragment",
    ),
    (
        "skills.drop.required_tool_ids",
        "ALTER TABLE skills DROP COLUMN IF EXISTS required_tool_ids",
    ),
    (
        "skills.drop.config_schema",
        "ALTER TABLE skills DROP COLUMN IF EXISTS config_schema",
    ),
    (
        "skills.drop.icon",
        "ALTER TABLE skills DROP COLUMN IF EXISTS icon",
    ),
    (
        "skills.drop.color",
        "ALTER TABLE skills DROP COLUMN IF EXISTS color",
    ),
    (
        "skills.drop.version",
        "ALTER TABLE skills DROP COLUMN IF EXISTS version",
    ),
    (
        "skills.drop.category",
        "ALTER TABLE skills DROP COLUMN IF EXISTS category",
    ),
    (
        "skills.drop.source",
        "ALTER TABLE skills DROP COLUMN IF EXISTS source",
    ),
    (
        "skills.drop.created_by_agent_id",
        "ALTER TABLE skills DROP COLUMN IF EXISTS created_by_agent_id",
    ),
]


async def run_migrations(db: AsyncSession) -> tuple[int, int]:
    """Run all pending migrations. Returns (succeeded, failed)."""
    succeeded = 0
    failed = 0
    for desc, sql in MIGRATIONS:
        try:
            await db.execute(text(sql))
            succeeded += 1
        except Exception as e:
            # Column might already exist, table might not exist yet, etc.
            logger.debug(f"Migration '{desc}' skipped: {e}")
            failed += 1
    await db.commit()
    logger.info(f"Schema migrations: {succeeded} applied, {failed} skipped")
    return succeeded, failed
