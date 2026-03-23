"""Conversation windowing — load only recent messages + a summary of older context."""

import hashlib
import json
import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Message

logger = logging.getLogger(__name__)

def _get_window_size() -> int:
    from app.core.system_settings import sys_settings
    return sys_settings.get("conversation_window_size") or 20


async def get_windowed_history(
    db: AsyncSession,
    conversation_id: str,
    exclude_last: bool = True,
) -> list[dict]:
    """
    Load a windowed view of conversation history:
    - If <= MAX_RECENT_MESSAGES: return all messages
    - If more: return a summary of older messages + the recent N messages

    Args:
        db: Database session
        conversation_id: The conversation to load
        exclude_last: If True, exclude the most recent message (the one just added)

    Returns:
        List of {"role": str, "content": str} dicts
    """
    # Count total messages
    count_result = await db.execute(
        select(func.count(Message.id)).where(
            Message.conversation_id == conversation_id
        )
    )
    total = count_result.scalar() or 0

    # Adjust for the message we just added
    effective_total = total - 1 if exclude_last else total

    max_recent = _get_window_size()
    if effective_total <= max_recent:
        # Load everything
        result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
        messages = result.scalars().all()
        if exclude_last:
            messages = messages[:-1]
        return [{"role": m.role, "content": m.content} for m in messages]

    # Load older messages for summarization
    older_count = effective_total - max_recent
    older_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
        .limit(older_count)
    )
    older_messages = older_result.scalars().all()

    # Load recent messages
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    all_messages = result.scalars().all()
    if exclude_last:
        all_messages = all_messages[:-1]
    recent_messages = all_messages[-max_recent:]

    # Try to get a cached summary, otherwise generate one
    summary = await _get_or_create_summary(older_messages)

    # Build the windowed history
    history = []
    if summary:
        history.append({
            "role": "system",
            "content": f"[Summary of {len(older_messages)} earlier messages]\n{summary}",
        })
    
    # Character-based safeguard for massive messages (e.g., tool outputs)
    CHAR_LIMIT = 25000  # Conservative limit for 'recent' window
    current_chars = sum(len(m.content) for m in recent_messages)
    if summary:
        current_chars += len(summary)
    
    final_messages = list(recent_messages)
    while current_chars > CHAR_LIMIT and len(final_messages) > 1:
        # Drop the oldest message from the recent window to stay within limits
        removed = final_messages.pop(0)
        current_chars -= len(removed.content)
        logger.debug(f"Trimming old message from window due to size: {len(removed.content)} chars")

    history.extend({"role": m.role, "content": m.content} for m in final_messages)

    return history


async def _get_or_create_summary(messages: list[Message]) -> str:
    """
    Generate a summary of older messages.
    Uses Redis cache keyed by message count + hash of content.
    """
    if not messages:
        return ""

    # Build a cache key from message count and content hash
    content_str = "".join(f"{m.role}:{m.content[:50]}" for m in messages[-10:])
    cache_key = f"conv_summary:{len(messages)}:{hashlib.md5(content_str.encode()).hexdigest()[:12]}"

    # Try Redis cache first
    try:
        from app.core.redis_client import get_redis
        redis = await get_redis()
        cached = await redis.get(cache_key)
        if cached:
            return cached
    except Exception:
        pass  # Redis unavailable, generate fresh

    # Generate summary via LLM
    summary = await _llm_summarize(messages)

    # Cache it (1 hour TTL)
    try:
        from app.core.redis_client import get_redis
        redis = await get_redis()
        from app.core.system_settings import sys_settings
        ttl = sys_settings.get("summary_cache_ttl") or 3600
        await redis.setex(cache_key, ttl, summary)
    except Exception:
        pass

    return summary


async def _llm_summarize(messages: list[Message]) -> str:
    """Use a fast LLM to summarize conversation messages."""
    try:
        from app.core.llm_registry import llm_registry

        # Build a condensed transcript
        transcript_lines = []
        for m in messages:
            prefix = "User" if m.role == "user" else "Assistant"
            # Truncate long messages
            content = m.content[:200] + "..." if len(m.content) > 200 else m.content
            transcript_lines.append(f"{prefix}: {content}")

        transcript = "\n".join(transcript_lines[-30:])  # Last 30 messages max

        prompt = (
            "Summarize this conversation in 2-4 sentences. "
            "Focus on key topics discussed, decisions made, and any pending items.\n\n"
            f"{transcript}"
        )

        # Use a fast/cheap model for summarization
        from app.core.system_settings import sys_settings
        provider = sys_settings.get("summary_llm_provider") or "groq"
        model = sys_settings.get("summary_llm_model") or "llama-3.1-8b-instant"
        llm = llm_registry.get_chat_model(provider=provider, model=model)
        response = await llm.ainvoke(prompt)
        return response.content if hasattr(response, "content") else str(response)
    except Exception as e:
        logger.debug(f"LLM summarization failed, using fallback: {e}")
        return _fallback_summary(messages)


def _fallback_summary(messages: list[Message]) -> str:
    """Simple extractive summary when LLM is unavailable."""
    topics = []
    for m in messages:
        if m.role == "user" and len(m.content) > 10:
            topics.append(m.content[:100])

    if not topics:
        return f"Previous conversation with {len(messages)} messages."

    # Take first and last user messages as summary
    parts = []
    if topics:
        parts.append(f"Started with: {topics[0]}")
    if len(topics) > 1:
        parts.append(f"Most recently discussed: {topics[-1]}")
    parts.append(f"({len(messages)} messages total)")

    return " ".join(parts)
