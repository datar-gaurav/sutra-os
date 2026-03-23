"""Database index creation for performance optimization.

These indexes target the most frequently queried columns.
Safe to run multiple times (IF NOT EXISTS).
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

INDEXES = [
    # ExecutionTrace — already has agent_id index, add composite for time-range queries
    "CREATE INDEX IF NOT EXISTS idx_traces_agent_created ON execution_traces (agent_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_traces_had_error ON execution_traces (had_error) WHERE had_error = true",

    # Messages — conversation history loading
    "CREATE INDEX IF NOT EXISTS idx_messages_conv_created ON messages (conversation_id, created_at)",

    # Memories — agent-scoped queries
    "CREATE INDEX IF NOT EXISTS idx_memories_agent_created ON memories (agent_id, created_at DESC)",

    # Usage records (if table exists)
    "CREATE INDEX IF NOT EXISTS idx_usage_agent_created ON usage_records (agent_id, created_at DESC)",

    # Tasks — assignee lookups
    "CREATE INDEX IF NOT EXISTS idx_tasks_assignee_status ON tasks (assignee_agent_id, status)",

    # Audit log — time-range queries
    "CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log (created_at DESC)",

    # Conversations — agent listing
    "CREATE INDEX IF NOT EXISTS idx_conversations_agent_updated ON conversations (agent_id, updated_at DESC)",

    # Approval requests — pending queue
    "CREATE INDEX IF NOT EXISTS idx_approvals_status_created ON approval_requests (status, created_at DESC)",
]


async def ensure_indexes(db: AsyncSession) -> int:
    """
    Create performance indexes if they don't exist.
    Returns the number of indexes created/verified.
    """
    created = 0
    for idx_sql in INDEXES:
        try:
            await db.execute(text(idx_sql))
            created += 1
        except Exception as e:
            # Some tables may not exist yet — that's fine
            logger.debug(f"Index creation skipped: {e}")
    await db.commit()
    logger.info(f"Database indexes verified: {created}/{len(INDEXES)} succeeded")
    return created
