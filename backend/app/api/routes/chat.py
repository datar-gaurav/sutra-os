"""Chat API routes — synchronous and streaming."""

import asyncio
import json
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import ChatRequest, ChatResponse
from app.core.agent_manager import agent_manager
from app.core.conversation_window import get_windowed_history
from app.core.orchestrator import orchestrator
from app.config import settings
from app.core.rate_limiter import limiter
from app.db.session import async_session_factory, get_db
from app.models.agent import Agent
from app.models.conversation import Conversation, Message

router = APIRouter(prefix="/chat", tags=["chat"])


async def _log_bg_error(exc: Exception, agent_id: str | None, task: str) -> None:
    """Fire-and-forget helper: persist a background error without crashing callers."""
    from app.core.error_logger import log_error
    await log_error(
        source="background_task",
        error=exc,
        severity="warning",
        agent_id=agent_id,
        context={"task": task},
    )


async def _auto_extract_memories(
    agent_id: str, user_message: str, assistant_response: str,
    llm_provider: str, llm_model: str,
    project_id: str | None = None,
    conversation_id: str | None = None,
):
    """Background task: extract and persist key facts from a conversation exchange."""
    try:
        from app.core.memory_service import memory_service
        async with async_session_factory() as db:
            await memory_service.auto_extract(
                db=db,
                agent_id=agent_id,
                user_message=user_message,
                assistant_response=assistant_response,
                llm_provider=llm_provider,
                llm_model=llm_model,
            )
            # Auto-extract decisions if project is active
            if project_id:
                from app.core.project_memory_service import auto_extract_decisions
                await auto_extract_decisions(
                    db=db,
                    project_id=project_id,
                    agent_id=agent_id,
                    user_message=user_message,
                    assistant_response=assistant_response,
                    llm_provider=llm_provider,
                    llm_model=llm_model,
                    conversation_id=conversation_id,
                )
            await db.commit()
    except Exception as exc:
        # Never crash the chat route, but do persist the error for Evolve visibility
        import asyncio
        from app.core.error_logger import log_error
        asyncio.create_task(log_error(
            source="background_task",
            error=exc,
            severity="warning",
            agent_id=agent_id,
            context={"task": "auto_extract_memories"},
        ))


@router.post("/", response_model=ChatResponse)
@limiter.limit(lambda: settings.rate_limit_chat)
async def chat(request: Request, payload: ChatRequest, db: AsyncSession = Depends(get_db)):
    """Send a message to an agent and get a response."""
    # Validate agent exists and is running
    agent = await db.get(Agent, payload.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not agent_manager.is_running(payload.agent_id):
        raise HTTPException(status_code=400, detail="Agent is not running. Start it first.")

    # Detect project switch
    active_project_id = None
    switch_notice = ""
    try:
        from app.core.project_memory_service import (
            detect_project_switch, get_active_project, handle_project_switch
        )
        active_project_id = await get_active_project(db, payload.agent_id)
        new_project_id = await detect_project_switch(db, payload.message)
        if new_project_id and new_project_id != active_project_id:
            switch_notice = await handle_project_switch(
                db, payload.agent_id, active_project_id, new_project_id
            )
            active_project_id = new_project_id
    except Exception as exc:
        asyncio.create_task(_log_bg_error(exc, payload.agent_id, "detect_project_switch"))

    # Get or create conversation
    if payload.conversation_id:
        conversation = await db.get(Conversation, payload.conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conversation = Conversation(
            agent_id=payload.agent_id,
            title=payload.message[:100],
            source="ui",
            project_id=active_project_id,
        )
        db.add(conversation)
        await db.flush()
        await db.refresh(conversation)

    # Save user message
    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=payload.message,
    )
    db.add(user_msg)
    await db.flush()

    # Load chat history (windowed — summary + recent messages for long conversations)
    chat_history = await get_windowed_history(db, conversation.id, exclude_last=True)

    # Prepend switch notice to message if project changed
    effective_message = payload.message
    if switch_notice:
        effective_message = f"[System: {switch_notice}]\n\n{payload.message}"

    # Set conversation context for browser session scoping
    from app.core.browser_session_manager import current_conversation_id
    current_conversation_id.set(str(conversation.id))

    # Route to agent (pass db for memory injection)
    result = await orchestrator.route_message(
        agent_id=payload.agent_id,
        message=effective_message,
        chat_history=chat_history,
        db=db,
    )

    # Save assistant response
    assistant_msg = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=result["output"],
        tool_calls={"steps": result.get("intermediate_steps", [])} if result.get("intermediate_steps") else None,
    )
    db.add(assistant_msg)
    await db.flush()
    await db.refresh(assistant_msg)

    # Fire-and-forget: auto-extract memories from this exchange
    asyncio.create_task(
        _auto_extract_memories(
            agent_id=payload.agent_id,
            user_message=payload.message,
            assistant_response=result["output"],
            llm_provider=agent.llm_provider,
            llm_model=agent.llm_model,
            project_id=active_project_id,
            conversation_id=conversation.id,
        )
    )

    return ChatResponse(
        conversation_id=conversation.id,
        message_id=assistant_msg.id,
        content=result["output"],
        tool_calls=assistant_msg.tool_calls,
    )


@router.post("/stream")
@limiter.limit(lambda: settings.rate_limit_chat)
async def chat_stream(request: Request, payload: ChatRequest, db: AsyncSession = Depends(get_db)):
    """Send a message to an agent and stream the response."""
    agent = await db.get(Agent, payload.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not agent_manager.is_running(payload.agent_id):
        raise HTTPException(status_code=400, detail="Agent is not running.")

    # Detect project switch
    active_project_id = None
    switch_notice = ""
    try:
        from app.core.project_memory_service import (
            detect_project_switch, get_active_project, handle_project_switch
        )
        active_project_id = await get_active_project(db, payload.agent_id)
        new_project_id = await detect_project_switch(db, payload.message)
        if new_project_id and new_project_id != active_project_id:
            switch_notice = await handle_project_switch(
                db, payload.agent_id, active_project_id, new_project_id
            )
            active_project_id = new_project_id
    except Exception as exc:
        asyncio.create_task(_log_bg_error(exc, payload.agent_id, "detect_project_switch"))

    # Get or create conversation
    if payload.conversation_id:
        conversation = await db.get(Conversation, payload.conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conversation = Conversation(
            agent_id=payload.agent_id,
            title=payload.message[:100],
            source="ui",
            project_id=active_project_id,
        )
        db.add(conversation)
        await db.flush()
        await db.refresh(conversation)

    # Save user message
    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=payload.message,
    )
    db.add(user_msg)
    await db.flush()

    # Load chat history (windowed — summary + recent messages for long conversations)
    chat_history = await get_windowed_history(db, conversation.id, exclude_last=True)

    conversation_id = conversation.id
    agent_id = payload.agent_id
    user_message = payload.message
    if switch_notice:
        user_message = f"[System: {switch_notice}]\n\n{payload.message}"

    # Set conversation context for browser session scoping
    from app.core.browser_session_manager import current_conversation_id as _conv_id_var
    _conv_id_var.set(str(conversation_id))

    # Commit conversation + user message before streaming starts,
    # so the conversation appears in the sidebar immediately.
    await db.commit()

    async def event_generator():
        full_response = ""
        intermediate_steps = []

        # Send conversation ID first
        yield f"data: {json.dumps({'type': 'meta', 'conversation_id': conversation_id})}\n\n"

        # Send project switch event if applicable
        if switch_notice and active_project_id:
            yield f"data: {json.dumps({'type': 'project_switch', 'project_id': active_project_id})}\n\n"

        async for chunk in orchestrator.stream_message(
            agent_id=agent_id,
            message=user_message,
            chat_history=chat_history,
            db=db,
        ):
            if chunk["type"] == "token":
                full_response += chunk["content"]
            elif chunk["type"] == "tool_start":
                intermediate_steps.append(chunk)
            yield f"data: {json.dumps(chunk)}\n\n"

        # Save assistant message with a fresh session
        try:
            async with async_session_factory() as save_db:
                assistant_msg = Message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=full_response,
                    tool_calls={"steps": intermediate_steps} if intermediate_steps else None,
                )
                save_db.add(assistant_msg)
                await save_db.commit()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to save assistant message: {e}")

        yield f"data: {json.dumps({'type': 'complete', 'content': full_response})}\n\n"

        # Fire-and-forget: auto-extract memories
        asyncio.create_task(
            _auto_extract_memories(
                agent_id=agent_id,
                user_message=payload.message,
                assistant_response=full_response,
                llm_provider=agent.llm_provider,
                llm_model=agent.llm_model,
                project_id=active_project_id,
                conversation_id=conversation_id,
            )
        )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

# ─── Daily Usage ──────────────────────────────────────────────────────────────

@router.get("/usage/{agent_id}")
async def agent_daily_usage(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Get today's request count for an agent."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(sa_func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.agent_id == agent_id,
            Message.role == "user",
            Message.created_at >= today_start,
        )
    )
    count = result.scalar() or 0
    return {
        "agent_id": agent_id,
        "date": str(date.today()),
        "request_count": count,
    }


# ─── Conversation History ─────────────────────────────────────────────────────

@router.get("/conversations/{agent_id}")
async def list_conversations(agent_id: str, db: AsyncSession = Depends(get_db)):
    """List all conversations for an agent."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.agent_id == agent_id)
        .order_by(Conversation.updated_at.desc())
    )
    conversations = result.scalars().all()
    return [
        {
            "id": c.id,
            "title": c.title,
            "source": c.source,
            "created_at": str(c.created_at),
            "updated_at": str(c.updated_at),
        }
        for c in conversations
    ]


@router.delete("/conversations/{agent_id}/{conversation_id}")
async def delete_conversation(
    agent_id: str, conversation_id: str, db: AsyncSession = Depends(get_db)
):
    """Delete a conversation and all its messages."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.agent_id == agent_id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.execute(delete(Message).where(Message.conversation_id == conversation_id))
    await db.delete(conv)
    await db.commit()
    return {"status": "deleted"}


@router.get("/conversations/{agent_id}/{conversation_id}/messages")
async def get_conversation_messages(
    agent_id: str, conversation_id: str, db: AsyncSession = Depends(get_db)
):
    """Get all messages in a conversation."""
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    messages = result.scalars().all()
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "tool_calls": m.tool_calls,
            "created_at": str(m.created_at),
        }
        for m in messages
    ]
