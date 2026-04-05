"""Telegram tools — send proactive messages to a Telegram chat.

Agents can use these tools to push summaries, alerts, or any content
to a preconfigured Telegram chat/user ID without needing an inbound
message to trigger the response.
"""

from __future__ import annotations

import logging

from langchain_core.tools import tool

from app.config import settings

logger = logging.getLogger(__name__)

TELEGRAM_TOOL_IDS = {"send_telegram_message"}


def create_telegram_tools():
    @tool
    async def send_telegram_message(
        message: str,
        chat_id: str = "",
    ) -> str:
        """Send a message to a Telegram chat or user.

        Use this to proactively deliver summaries, alerts, or status updates
        to a Telegram user or group without waiting for them to ask.

        Args:
            message: The text content to send (plain text, no Markdown needed).
            chat_id: Telegram chat ID or username (e.g. '123456789' or '@mychannel').
                     If unknown, ask the user for it before calling this tool.
                     Leave empty only if TELEGRAM_DEFAULT_CHAT_ID is already configured.
        """
        from app.integrations.telegram_bot import get_telegram_bot_token
        token = await get_telegram_bot_token()
        if not token:
            return "Error: Telegram bot is not configured (TELEGRAM_BOT_TOKEN not set)."

        import os
        default_chat_id = os.environ.get("TELEGRAM_DEFAULT_CHAT_ID", "") or settings.telegram_default_chat_id
        target_chat_id = chat_id.strip() or default_chat_id.strip()
        if not target_chat_id:
            return "Error: chat_id is required. Ask the user for their Telegram chat ID (a number like 123456789) and retry with it."

        try:
            from app.integrations.telegram_bot import send_telegram_message as _send
            await _send(chat_id=target_chat_id, text=message)
            return f"Message sent to Telegram chat {target_chat_id}."
        except Exception as e:
            logger.error(f"Telegram send_telegram_message tool error: {e}")
            return f"Error sending Telegram message: {e}"

    return [send_telegram_message]
