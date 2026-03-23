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
                     Leave empty to use the system-configured default chat ID
                     (TELEGRAM_DEFAULT_CHAT_ID env var).
        """
        if not settings.telegram_bot_token:
            return "Error: Telegram bot is not configured (TELEGRAM_BOT_TOKEN not set)."

        target_chat_id = chat_id.strip() or settings.telegram_default_chat_id.strip()
        if not target_chat_id:
            return (
                "Error: No chat_id provided and TELEGRAM_DEFAULT_CHAT_ID is not configured. "
                "Pass a chat_id explicitly or set the env var."
            )

        try:
            from app.integrations.telegram_bot import send_telegram_message as _send
            await _send(chat_id=target_chat_id, text=message)
            return f"Message sent to Telegram chat {target_chat_id}."
        except Exception as e:
            logger.error(f"Telegram send_telegram_message tool error: {e}")
            return f"Error sending Telegram message: {e}"

    return [send_telegram_message]
