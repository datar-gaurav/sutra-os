"""Voice Registry — unified registration + routing for STT and TTS providers.

Mirrors the structure of `app.core.llm_registry`. STT and TTS each have an
ordered list of provider names; callers ask for a chain (with optional
agent-level override) and try them in order until one succeeds.

Phase 1 keeps this minimal: no Redis-backed rate-limit accounting yet.
The chain is just (override → settings.voice_default_*_provider → registered
fallbacks). Phase 3 will add per-provider RPM/circuit-breaker like the LLM
registry once we're driving streaming sessions.
"""

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


# Built-in provider types we know about. New types can be added without
# code changes via register_*_provider — these are just the seeds.
BUILTIN_STT: tuple[str, ...] = ("whisper_local", "groq_whisper", "openai_whisper")
BUILTIN_TTS: tuple[str, ...] = ("kokoro_local", "elevenlabs", "openai_tts", "xtts_local")


class VoiceRegistry:
    """Registry of STT and TTS providers."""

    def __init__(self):
        self._stt: dict[str, dict[str, Any]] = {}
        self._tts: dict[str, dict[str, Any]] = {}
        self._stt_fallback_order: list[str] = []
        self._tts_fallback_order: list[str] = []

    # ── Registration ──────────────────────────────────────────────────────
    def register_stt(
        self,
        name: str,
        provider_type: str,
        api_key: str = "",
        base_url: str = "",
        priority: int = 100,
    ):
        self._stt[name] = {
            "type": provider_type,
            "api_key": api_key,
            "base_url": base_url,
            "priority": priority,
        }
        self._rebuild_stt_order()

    def register_tts(
        self,
        name: str,
        provider_type: str,
        api_key: str = "",
        base_url: str = "",
        priority: int = 100,
    ):
        self._tts[name] = {
            "type": provider_type,
            "api_key": api_key,
            "base_url": base_url,
            "priority": priority,
        }
        self._rebuild_tts_order()

    def _rebuild_stt_order(self):
        # Lower priority number = tried first
        self._stt_fallback_order = sorted(
            self._stt.keys(), key=lambda n: self._stt[n]["priority"]
        )

    def _rebuild_tts_order(self):
        self._tts_fallback_order = sorted(
            self._tts.keys(), key=lambda n: self._tts[n]["priority"]
        )

    def seed_defaults(self):
        """Seed the registry with the built-in local providers + cloud fallbacks
        based on settings. Idempotent — safe to call on every startup."""
        # Local STT (always available even without API key — host service ping is
        # checked at call time)
        self.register_stt(
            "whisper_local",
            "whisper_local",
            base_url=settings.whisper_local_url,
            priority=10,
        )
        # Cloud STT — only registered when key present
        if settings.groq_api_key:
            self.register_stt(
                "groq_whisper",
                "groq_whisper",
                api_key=settings.groq_api_key,
                base_url="https://api.groq.com/openai/v1",
                priority=20,
            )
        if settings.openai_api_key:
            self.register_stt(
                "openai_whisper",
                "openai_whisper",
                api_key=settings.openai_api_key,
                base_url="https://api.openai.com/v1",
                priority=30,
            )

        # Local TTS
        self.register_tts(
            "kokoro_local",
            "kokoro_local",
            base_url=settings.kokoro_local_url,
            priority=10,
        )
        # XTTS lazy-loaded; kept low priority so it isn't in the agent-default
        # chain unless explicitly requested (content pipeline only — D-decision).
        self.register_tts(
            "xtts_local",
            "xtts_local",
            base_url=settings.xtts_local_url,
            priority=200,
        )
        if settings.elevenlabs_api_key:
            self.register_tts(
                "elevenlabs",
                "elevenlabs",
                api_key=settings.elevenlabs_api_key,
                base_url="https://api.elevenlabs.io/v1",
                priority=20,
            )
        openai_tts_key = settings.openai_tts_api_key or settings.openai_api_key
        if openai_tts_key:
            self.register_tts(
                "openai_tts",
                "openai_tts",
                api_key=openai_tts_key,
                base_url="https://api.openai.com/v1",
                priority=30,
            )
        logger.info(
            "Voice registry seeded — STT=%s TTS=%s",
            self._stt_fallback_order,
            self._tts_fallback_order,
        )

    # ── Lookup ────────────────────────────────────────────────────────────
    def get_stt_provider(self, name: str) -> dict[str, Any] | None:
        return self._stt.get(name)

    def get_tts_provider(self, name: str) -> dict[str, Any] | None:
        return self._tts.get(name)

    def get_stt_chain(self, override: str | None = None) -> list[str]:
        """Return ordered list of STT provider names to try, override first."""
        chain: list[str] = []
        if override and override in self._stt:
            chain.append(override)
        # Default from settings
        default = settings.voice_default_stt_provider
        if default and default in self._stt and default not in chain:
            chain.append(default)
        # Then the rest in priority order
        for name in self._stt_fallback_order:
            if name not in chain:
                chain.append(name)
        return chain

    def get_tts_chain(self, override: str | None = None) -> list[str]:
        chain: list[str] = []
        if override and override in self._tts:
            chain.append(override)
        default = settings.voice_default_tts_provider
        if default and default in self._tts and default not in chain:
            chain.append(default)
        for name in self._tts_fallback_order:
            if name not in chain:
                # Skip XTTS in default chain — it's reserved for content pipeline
                # callers who request it explicitly.
                if name == "xtts_local" and override != "xtts_local":
                    continue
                chain.append(name)
        return chain

    def list_stt_providers(self) -> list[str]:
        return list(self._stt_fallback_order)

    def list_tts_providers(self) -> list[str]:
        return list(self._tts_fallback_order)

    # ── Voice catalog ────────────────────────────────────────────────────
    async def list_voices(self, provider: str | None = None) -> dict[str, list[dict]]:
        """Return available voices per TTS provider.

        Shape: {"kokoro_local": [{"id": "af_bella", "name": "Bella", "lang": "en"}, ...]}
        Only providers that are registered AND reachable are queried.
        """
        out: dict[str, list[dict]] = {}
        targets = [provider] if provider else self.list_tts_providers()
        for name in targets:
            cfg = self._tts.get(name)
            if not cfg:
                continue
            try:
                voices = await self._fetch_voices(name, cfg)
                out[name] = voices
            except Exception as e:
                logger.warning("list_voices failed for %s: %s", name, e)
                out[name] = []
        return out

    async def _fetch_voices(self, name: str, cfg: dict[str, Any]) -> list[dict]:
        ptype = cfg["type"]
        base_url = cfg["base_url"]
        api_key = cfg.get("api_key", "")

        async with httpx.AsyncClient(timeout=8.0) as client:
            if ptype == "kokoro_local":
                # kokoro-fastapi exposes /v1/audio/voices
                resp = await client.get(f"{base_url}/v1/audio/voices")
                resp.raise_for_status()
                data = resp.json()
                # Response is {"voices": ["af_bella", "af_sky", ...]}
                voices = data.get("voices", []) if isinstance(data, dict) else data
                return [
                    {"id": v, "name": _humanize_kokoro(v), "lang": v.split("_")[0]}
                    for v in voices
                ]
            if ptype == "elevenlabs":
                resp = await client.get(
                    f"{base_url}/voices",
                    headers={"xi-api-key": api_key},
                )
                resp.raise_for_status()
                return [
                    {"id": v["voice_id"], "name": v.get("name", v["voice_id"]), "lang": "en"}
                    for v in resp.json().get("voices", [])
                ]
            if ptype == "openai_tts":
                # OpenAI TTS voices are static
                return [
                    {"id": v, "name": v.title(), "lang": "en"}
                    for v in ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
                ]
            if ptype == "xtts_local":
                # Voice cloning service — voices are user-defined clones.
                resp = await client.get(f"{base_url}/clones")
                resp.raise_for_status()
                return [
                    {"id": c["id"], "name": c.get("name", c["id"]), "lang": c.get("lang", "en")}
                    for c in resp.json().get("clones", [])
                ]
        return []

    async def health_check(self, name: str, kind: str) -> bool:
        """Ping a provider to see if it's reachable. kind = 'stt' | 'tts'."""
        cfg = (self._stt if kind == "stt" else self._tts).get(name)
        if not cfg:
            return False
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(cfg["base_url"])
                return resp.status_code < 500
        except Exception:
            return False


def _humanize_kokoro(voice_id: str) -> str:
    """`af_bella` → `Bella (American Female)`."""
    parts = voice_id.split("_", 1)
    if len(parts) != 2:
        return voice_id
    code, name = parts
    accent_map = {"a": "American", "b": "British", "j": "Japanese", "z": "Chinese"}
    gender_map = {"f": "Female", "m": "Male"}
    accent = accent_map.get(code[0:1], "")
    gender = gender_map.get(code[1:2], "")
    label = f"{accent} {gender}".strip()
    return f"{name.title()} ({label})" if label else name.title()


# Global singleton
voice_registry = VoiceRegistry()
