"""Speech-to-text service.

Tries providers in order from `voice_registry.get_stt_chain(...)`. Each
provider implementation accepts raw audio bytes + mime/format hint and
returns a `Transcription` (text + metadata). Failures cascade to the next
provider; a final failure raises `STTError`.

Phase 1 uses a single full-utterance transcribe call per inbound voice
message. Phase 3 will add a streaming variant for the live web session.
"""

import io
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.voice_registry import voice_registry

logger = logging.getLogger(__name__)


class STTError(Exception):
    """Raised when no STT provider successfully transcribes the audio."""


@dataclass
class Transcription:
    text: str
    provider: str
    duration_seconds: float | None = None
    language: str | None = None


# Mime → file extension hint for multipart uploads. Whisper.cpp + cloud
# providers all accept these container formats.
_MIME_EXT = {
    "audio/ogg": "ogg",
    "audio/oga": "ogg",
    "audio/ogg;codecs=opus": "ogg",
    "audio/webm": "webm",
    "audio/webm;codecs=opus": "webm",
    "audio/mp4": "m4a",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/flac": "flac",
}


def _ext_for(mime: str) -> str:
    return _MIME_EXT.get(mime.lower(), "ogg")


async def transcribe(
    audio: bytes,
    mime: str = "audio/ogg",
    language: str = "en",
    provider_override: str | None = None,
    timeout: float = 30.0,
) -> Transcription:
    """Transcribe audio bytes. Returns the first successful result."""
    if not audio:
        raise STTError("empty audio buffer")

    chain = voice_registry.get_stt_chain(provider_override)
    if not chain:
        raise STTError("no STT providers registered")

    last_err: Exception | None = None
    for name in chain:
        cfg = voice_registry.get_stt_provider(name)
        if not cfg:
            continue
        try:
            text = await _dispatch(cfg, audio, mime, language, timeout)
            if text:
                logger.info("STT ok via %s (%d chars)", name, len(text))
                return Transcription(text=text.strip(), provider=name, language=language)
        except Exception as e:
            logger.warning("STT provider %s failed: %s", name, e)
            last_err = e
            continue
    raise STTError(f"all STT providers failed; last_err={last_err}")


async def _dispatch(
    cfg: dict[str, Any],
    audio: bytes,
    mime: str,
    language: str,
    timeout: float,
) -> str:
    ptype = cfg["type"]
    base_url = cfg["base_url"]
    api_key = cfg.get("api_key", "")
    ext = _ext_for(mime)
    fname = f"audio.{ext}"

    if ptype == "whisper_local":
        return await _whisper_local(base_url, audio, fname, mime, language, timeout)
    if ptype == "groq_whisper":
        return await _openai_compatible(
            base_url, api_key, audio, fname, mime, language, timeout,
            model="whisper-large-v3-turbo",
        )
    if ptype == "openai_whisper":
        return await _openai_compatible(
            base_url, api_key, audio, fname, mime, language, timeout,
            model="whisper-1",
        )
    raise STTError(f"unknown STT provider type: {ptype}")


async def _whisper_local(
    base_url: str,
    audio: bytes,
    fname: str,
    mime: str,
    language: str,
    timeout: float,
) -> str:
    """whisper.cpp server `/inference` endpoint.

    Reference: https://github.com/ggerganov/whisper.cpp/tree/master/examples/server
    Posts multipart with the audio file under `file`, language + response_format
    fields. Returns `{"text": "..."}`.
    """
    files = {"file": (fname, io.BytesIO(audio), mime)}
    data = {
        "language": language,
        "response_format": "json",
        "temperature": "0",
        # whisper.cpp ignores unknown fields, so it's safe to over-specify
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{base_url}/inference", files=files, data=data)
        resp.raise_for_status()
        body = resp.json()
        return body.get("text", "") or ""


async def _openai_compatible(
    base_url: str,
    api_key: str,
    audio: bytes,
    fname: str,
    mime: str,
    language: str,
    timeout: float,
    *,
    model: str,
) -> str:
    """Generic OpenAI-style /audio/transcriptions multipart POST.

    Works for OpenAI Whisper API and Groq Whisper API (OpenAI-compatible).
    """
    if not api_key:
        raise STTError("missing api_key")
    files = {"file": (fname, io.BytesIO(audio), mime)}
    data = {
        "model": model,
        "language": language,
        "response_format": "json",
        "temperature": "0",
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{base_url}/audio/transcriptions",
            files=files,
            data=data,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json().get("text", "") or ""
