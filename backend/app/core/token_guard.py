"""Token limit guard — prevents 413 errors by estimating and trimming message payloads.

Provides a fast, heuristic-based pre-request check that ensures assembled messages
fit within a model's context window before sending to the LLM provider.
"""

import logging
from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model context window registry
# ---------------------------------------------------------------------------

MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    # OpenRouter models
    "openrouter/moonshotai/kimi-k2-instruct": 131_072,
    # OpenAI
    "openai/gpt-4o": 128_000,
    "openai/gpt-4o-mini": 128_000,
    "openai/gpt-4-turbo": 128_000,
    "openai/gpt-3.5-turbo": 16_385,
    # Anthropic
    "anthropic/claude-opus-4-7": 200_000,
    "anthropic/claude-sonnet-4-6": 200_000,
    "anthropic/claude-haiku-4-5-20251001": 200_000,
    "anthropic/claude-3-5-sonnet-20241022": 200_000,
    # Google
    "google/gemini-1.5-pro": 1_048_576,
    "google/gemini-2.0-flash": 1_048_576,
    "google/gemini-1.5-flash": 1_048_576,
    # Groq
    "groq/llama-3.1-8b-instant": 131_072,
    "groq/llama-3.1-70b-versatile": 131_072,
    "groq/mixtral-8x7b-32768": 32_768,
    # Perplexity
    "perplexity/llama-3.1-sonar-large-128k-online": 127_072,
}

DEFAULT_CONTEXT_WINDOW = 32_768  # conservative fallback

# Reserve 20% for output tokens + overhead
CONTEXT_SAFETY_MARGIN = 0.80


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Fast token estimate. ~4 chars per token for English text."""
    if not text:
        return 0
    return len(text) // 4 + 1


def estimate_messages_tokens(messages: list[BaseMessage]) -> int:
    """Estimate total tokens across a list of messages."""
    total = 0
    for m in messages:
        if isinstance(m.content, str):
            total += estimate_tokens(m.content)
        elif isinstance(m.content, list):
            # Multimodal content blocks
            for block in m.content:
                if isinstance(block, dict) and block.get("type") == "text":
                    total += estimate_tokens(block.get("text", ""))
    return total


def get_context_limit(provider: str, model: str) -> int:
    """Return usable input token limit for a model (with safety margin applied)."""
    key = f"{provider}/{model}"
    window = MODEL_CONTEXT_WINDOWS.get(key, DEFAULT_CONTEXT_WINDOW)
    return int(window * CONTEXT_SAFETY_MARGIN)


# ---------------------------------------------------------------------------
# Message trimming
# ---------------------------------------------------------------------------

def trim_messages_to_fit(
    messages: list[BaseMessage],
    max_tokens: int,
) -> list[BaseMessage]:
    """Trim messages to fit within max_tokens.

    Strategy (most expendable first):
    1. Always keep: first SystemMessage (prompt/memory), last HumanMessage (user query)
    2. Remove oldest chat history messages one-by-one
    3. If still over: truncate the memory SystemMessage to 50%
    """
    if not messages:
        return messages

    # Identify protected messages
    first_system_idx = None
    last_human_idx = None
    for i, m in enumerate(messages):
        if first_system_idx is None and isinstance(m, SystemMessage):
            first_system_idx = i
        if isinstance(m, HumanMessage):
            last_human_idx = i

    # Work on a mutable copy
    result = list(messages)

    # Phase 1: Remove middle history messages (oldest first, skip protected)
    while estimate_messages_tokens(result) > max_tokens:
        # Find the oldest removable message (not the first system or last human)
        removed = False
        for i in range(len(result)):
            if i == first_system_idx:
                continue
            # Don't remove the last human message
            if i == len(result) - 1 and isinstance(result[i], HumanMessage):
                continue
            if isinstance(result[i], (HumanMessage, AIMessage)):
                result.pop(i)
                # Recalculate protected indices
                first_system_idx = None
                last_human_idx = None
                for j, m in enumerate(result):
                    if first_system_idx is None and isinstance(m, SystemMessage):
                        first_system_idx = j
                    if isinstance(m, HumanMessage):
                        last_human_idx = j
                removed = True
                break
        if not removed:
            break

    # Phase 2: Truncate the memory SystemMessage to 50%
    if estimate_messages_tokens(result) > max_tokens and first_system_idx is not None:
        sys_msg = result[first_system_idx]
        if isinstance(sys_msg.content, str) and len(sys_msg.content) > 200:
            # Keep first 50% of the content
            half = len(sys_msg.content) // 2
            result[first_system_idx] = SystemMessage(
                content=sys_msg.content[:half] + "\n\n[Memory context truncated to fit model limits]"
            )

    # Phase 3: If STILL over, aggressively truncate system message to just a stub
    if estimate_messages_tokens(result) > max_tokens and first_system_idx is not None:
        sys_msg = result[first_system_idx]
        if isinstance(sys_msg.content, str) and len(sys_msg.content) > 500:
            result[first_system_idx] = SystemMessage(
                content=sys_msg.content[:500] + "\n\n[Memory context heavily truncated to fit model limits]"
            )

    return result


def emergency_trim(messages: list[BaseMessage], max_history: int = 5) -> list[BaseMessage]:
    """Aggressive trim for 413 recovery: keep system prompt + last N history + user message."""
    system_msgs = [m for m in messages if isinstance(m, SystemMessage)]
    history = [m for m in messages if isinstance(m, (HumanMessage, AIMessage))]

    # Keep only the last user message and up to max_history preceding messages
    if history:
        last_human = history[-1] if isinstance(history[-1], HumanMessage) else None
        preceding = history[:-1] if last_human else history
        kept_history = preceding[-max_history:]
        if last_human:
            kept_history.append(last_human)
    else:
        kept_history = []

    # Keep only the first system message, truncated
    kept_system = []
    if system_msgs:
        content = system_msgs[0].content
        if isinstance(content, str) and len(content) > 2000:
            content = content[:2000] + "\n\n[Truncated for recovery]"
        kept_system = [SystemMessage(content=content)]

    return kept_system + kept_history
