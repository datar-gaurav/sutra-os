"""Voice API — STT transcription, TTS synthesis, voice catalog.

These endpoints are used by the frontend voice mode (Phase 2 push-to-talk
first, Phase 3 streaming) and by internal services that need to
synthesise/transcribe outside the chat hot-path.
"""

import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.config import settings
from app.core.stt_service import STTError, transcribe
from app.core.tts_service import TTSError, synthesize
from app.core.voice_registry import voice_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


class TranscribeResponse(BaseModel):
    text: str
    provider: str
    language: str | None = None


class SynthesizeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    voice: str | None = None
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    provider: str | None = None
    format: str = Field(default="mp3", pattern="^(mp3|wav|ogg|flac|opus|pcm)$")


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_endpoint(
    file: UploadFile = File(...),
    language: str = Form(default="en"),
    provider: str | None = Form(default=None),
):
    """Transcribe an uploaded audio file. Tries the configured STT chain in order."""
    audio = await file.read()
    if not audio:
        raise HTTPException(status_code=400, detail="empty audio")
    if len(audio) > 25 * 1024 * 1024:  # 25 MB matches OpenAI Whisper limit
        raise HTTPException(status_code=413, detail="audio file too large (>25MB)")
    mime = file.content_type or "audio/ogg"
    try:
        result = await transcribe(audio, mime=mime, language=language, provider_override=provider)
    except STTError as e:
        logger.error("transcribe failed: %s", e)
        raise HTTPException(status_code=502, detail=f"transcription failed: {e}")
    return TranscribeResponse(text=result.text, provider=result.provider, language=result.language)


@router.post("/synthesize")
async def synthesize_endpoint(req: SynthesizeRequest):
    """Synthesise speech and return raw audio bytes with the appropriate Content-Type."""
    try:
        result = await synthesize(
            text=req.text,
            voice=req.voice,
            speed=req.speed,
            provider_override=req.provider,
            output_format=req.format,
        )
    except TTSError as e:
        logger.error("synthesize failed: %s", e)
        raise HTTPException(status_code=502, detail=f"synthesis failed: {e}")
    return Response(
        content=result.audio,
        media_type=result.mime,
        headers={
            "X-Voice-Provider": result.provider,
            "X-Voice-Id": result.voice_id,
        },
    )


@router.get("/voices")
async def list_voices(provider: str | None = None):
    """List available voices, grouped by TTS provider.

    Frontend uses this to populate the per-agent voice picker.
    """
    try:
        voices = await voice_registry.list_voices(provider=provider)
    except Exception as e:
        logger.warning("list_voices failed: %s", e)
        voices = {}
    return {
        "providers": {
            "stt": voice_registry.list_stt_providers(),
            "tts": voice_registry.list_tts_providers(),
        },
        "defaults": {
            "tts_provider": settings.voice_default_tts_provider,
            "stt_provider": settings.voice_default_stt_provider,
            "voice_id": settings.voice_default_voice_id,
        },
        "voices": voices,
    }


@router.get("/health")
async def voice_health():
    """Liveness summary for the voice subsystem — used by the Settings UI."""
    out = {"stt": {}, "tts": {}}
    for name in voice_registry.list_stt_providers():
        out["stt"][name] = await voice_registry.health_check(name, "stt")
    for name in voice_registry.list_tts_providers():
        out["tts"][name] = await voice_registry.health_check(name, "tts")
    return out
