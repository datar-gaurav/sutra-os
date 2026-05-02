"""Text-to-speech service.

Synthesizes audio from text using the first reachable provider in the
TTS fallback chain. Returns either a single buffer (`synthesize`) or an
async iterator of byte chunks (`synthesize_stream`) for incremental
playback (Phase 3 web streaming).

Output container format is provider-controlled. Defaults:
- kokoro_local → mp3 (good for Telegram voice notes)
- elevenlabs   → mp3
- openai_tts   → mp3
- xtts_local   → wav (re-encoded by caller if needed)
"""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings
from app.core.voice_registry import voice_registry

logger = logging.getLogger(__name__)


class TTSError(Exception):
    """Raised when no TTS provider successfully synthesizes the audio."""


@dataclass
class Synthesis:
    audio: bytes
    mime: str
    provider: str
    voice_id: str


# Cap on text length per request — prevents accidental megabyte-long inputs
# from blocking the queue. Long replies should be chunked at sentence
# boundaries by the caller.
MAX_TEXT_CHARS = 4000


def _voice_or_default(voice: str | None) -> str:
    return voice or settings.voice_default_voice_id


async def synthesize(
    text: str,
    voice: str | None = None,
    speed: float = 1.0,
    provider_override: str | None = None,
    output_format: str = "mp3",
    timeout: float = 60.0,
) -> Synthesis:
    """Synthesize the full text into one audio blob (Phase 1 batch path)."""
    if not text or not text.strip():
        raise TTSError("empty text")
    text = text[:MAX_TEXT_CHARS]
    voice_id = _voice_or_default(voice)

    chain = voice_registry.get_tts_chain(provider_override)
    if not chain:
        raise TTSError("no TTS providers registered")

    last_err: Exception | None = None
    for name in chain:
        cfg = voice_registry.get_tts_provider(name)
        if not cfg:
            continue
        try:
            audio, mime = await _dispatch(cfg, text, voice_id, speed, output_format, timeout)
            if audio:
                logger.info("TTS ok via %s (%d bytes)", name, len(audio))
                return Synthesis(audio=audio, mime=mime, provider=name, voice_id=voice_id)
        except Exception as e:
            logger.warning("TTS provider %s failed: %s", name, e)
            last_err = e
            continue
    raise TTSError(f"all TTS providers failed; last_err={last_err}")


async def synthesize_stream(
    text: str,
    voice: str | None = None,
    speed: float = 1.0,
    provider_override: str | None = None,
    output_format: str = "mp3",
    timeout: float = 60.0,
) -> AsyncIterator[bytes]:
    """Stream audio chunks as they're produced (Phase 3 hookup).

    Falls back to a single-shot fetch yielded as one chunk if the underlying
    provider doesn't expose a streaming endpoint.
    """
    text = text[:MAX_TEXT_CHARS]
    voice_id = _voice_or_default(voice)
    chain = voice_registry.get_tts_chain(provider_override)
    if not chain:
        raise TTSError("no TTS providers registered")

    last_err: Exception | None = None
    for name in chain:
        cfg = voice_registry.get_tts_provider(name)
        if not cfg:
            continue
        try:
            async for chunk in _dispatch_stream(cfg, text, voice_id, speed, output_format, timeout):
                yield chunk
            return
        except Exception as e:
            logger.warning("TTS streaming provider %s failed: %s", name, e)
            last_err = e
            continue
    raise TTSError(f"all TTS providers failed (stream); last_err={last_err}")


async def _dispatch(
    cfg: dict[str, Any],
    text: str,
    voice_id: str,
    speed: float,
    output_format: str,
    timeout: float,
) -> tuple[bytes, str]:
    ptype = cfg["type"]
    base_url = cfg["base_url"]
    api_key = cfg.get("api_key", "")

    if ptype == "kokoro_local":
        return await _kokoro(base_url, text, voice_id, speed, output_format, timeout)
    if ptype == "elevenlabs":
        return await _elevenlabs(base_url, api_key, text, voice_id, speed, output_format, timeout)
    if ptype == "openai_tts":
        return await _openai_tts(base_url, api_key, text, voice_id, speed, output_format, timeout)
    if ptype == "xtts_local":
        return await _xtts(base_url, text, voice_id, speed, timeout)
    raise TTSError(f"unknown TTS provider type: {ptype}")


async def _dispatch_stream(
    cfg: dict[str, Any],
    text: str,
    voice_id: str,
    speed: float,
    output_format: str,
    timeout: float,
) -> AsyncIterator[bytes]:
    ptype = cfg["type"]
    base_url = cfg["base_url"]
    api_key = cfg.get("api_key", "")

    if ptype == "kokoro_local":
        async for chunk in _kokoro_stream(base_url, text, voice_id, speed, output_format, timeout):
            yield chunk
        return
    # Cloud providers — fall back to single-shot then yield once
    audio, _ = await _dispatch(cfg, text, voice_id, speed, output_format, timeout)
    yield audio


# ── Provider implementations ─────────────────────────────────────────────

async def _kokoro(
    base_url: str, text: str, voice_id: str, speed: float, fmt: str, timeout: float
) -> tuple[bytes, str]:
    """kokoro-fastapi exposes an OpenAI-compatible /v1/audio/speech endpoint."""
    payload = {
        "model": "kokoro",
        "input": text,
        "voice": voice_id,
        "response_format": fmt,
        "speed": speed,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{base_url}/v1/audio/speech", json=payload)
        resp.raise_for_status()
        return resp.content, _mime_for(fmt)


async def _kokoro_stream(
    base_url: str, text: str, voice_id: str, speed: float, fmt: str, timeout: float
) -> AsyncIterator[bytes]:
    payload = {
        "model": "kokoro",
        "input": text,
        "voice": voice_id,
        "response_format": fmt,
        "speed": speed,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", f"{base_url}/v1/audio/speech", json=payload) as resp:
            resp.raise_for_status()
            async for chunk in resp.aiter_bytes():
                if chunk:
                    yield chunk


async def _elevenlabs(
    base_url: str, api_key: str, text: str, voice_id: str, speed: float, fmt: str, timeout: float,
) -> tuple[bytes, str]:
    if not api_key:
        raise TTSError("missing elevenlabs api_key")
    output_format = "mp3_44100_128" if fmt == "mp3" else "pcm_24000"
    payload = {
        "text": text,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }
    headers = {"xi-api-key": api_key, "accept": "audio/mpeg"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{base_url}/text-to-speech/{voice_id}",
            json=payload,
            headers=headers,
            params={"output_format": output_format},
        )
        resp.raise_for_status()
        return resp.content, _mime_for(fmt)


async def _openai_tts(
    base_url: str, api_key: str, text: str, voice_id: str, speed: float, fmt: str, timeout: float,
) -> tuple[bytes, str]:
    if not api_key:
        raise TTSError("missing openai api_key")
    payload = {
        "model": "tts-1",
        "input": text,
        "voice": voice_id,
        "response_format": fmt,
        "speed": speed,
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{base_url}/audio/speech", json=payload, headers=headers)
        resp.raise_for_status()
        return resp.content, _mime_for(fmt)


async def _xtts(
    base_url: str, text: str, clone_id: str, speed: float, timeout: float,
) -> tuple[bytes, str]:
    """XTTS-v2 (content pipeline only — voice cloning).

    Expects an HTTP server with POST /tts that takes {text, clone_id, speed}
    and returns wav bytes. Phase 4 will harden this; for now it's a stub.
    """
    payload = {"text": text, "clone_id": clone_id, "speed": speed}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{base_url}/tts", json=payload)
        resp.raise_for_status()
        return resp.content, "audio/wav"


def _mime_for(fmt: str) -> str:
    return {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "ogg": "audio/ogg",
        "flac": "audio/flac",
        "opus": "audio/ogg;codecs=opus",
        "pcm": "audio/pcm",
    }.get(fmt, "application/octet-stream")
