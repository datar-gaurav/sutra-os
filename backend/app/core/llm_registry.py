"""LLM Registry — unified interface for managing LLM providers."""

import logging
from typing import Any

import httpx
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

# Providers whose APIs reject requests that include a `tools` parameter
NO_TOOL_SUPPORT_PROVIDERS: frozenset[str] = frozenset({"perplexity"})


class LLMRegistry:
    """Registry that creates LangChain chat model instances from provider configs."""

    def __init__(self):
        self._providers: dict[str, dict[str, Any]] = {}

    def register_provider(
        self,
        name: str,
        provider_type: str,
        api_key: str = "",
        base_url: str = "",
        supports_tool_calling: bool = True,
    ):
        """Register a provider configuration."""
        self._providers[name] = {
            "type": provider_type,
            "api_key": api_key,
            "base_url": base_url,
            "supports_tool_calling": supports_tool_calling,
        }

    def provider_supports_tools(self, provider_type: str) -> bool:
        """Return True if the provider supports tool/function calling.

        Checks the in-memory registry first (populated from DB), then falls back
        to the static NO_TOOL_SUPPORT_PROVIDERS set for providers not yet registered.
        """
        if provider_type in self._providers:
            return self._providers[provider_type].get("supports_tool_calling", True)
        # Fallback for built-in providers that haven't been registered via DB
        return provider_type not in NO_TOOL_SUPPORT_PROVIDERS

    def get_chat_model(
        self,
        provider: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        streaming: bool = True,
    ):
        """Create a LangChain chat model instance for the given provider/model."""
        tags = [f"provider:{provider}", f"model:{model}"]

        if provider == "ollama":
            import os as _os
            ollama_url = _os.environ.get("OLLAMA_BASE_URL") or settings.ollama_base_url
            return ChatOllama(
                model=model,
                base_url=ollama_url,
                temperature=temperature,
                num_predict=max_tokens,
                keep_alive="1m",
                tags=tags,
            )
        elif provider == "openai":
            api_key = self._get_api_key(provider, settings.openai_api_key)
            return ChatOpenAI(
                model=model,
                api_key=api_key,
                temperature=temperature,
                max_tokens=max_tokens,
                streaming=streaming,
                tags=tags,
            )
        elif provider == "anthropic":
            api_key = self._get_api_key(provider, settings.anthropic_api_key)
            return ChatAnthropic(
                model=model,
                api_key=api_key,
                temperature=temperature,
                max_tokens=max_tokens,
                streaming=streaming,
                tags=tags,
            )
        elif provider == "google":
            api_key = self._get_api_key(provider, settings.google_api_key)
            return ChatGoogleGenerativeAI(
                model=model,
                google_api_key=api_key,
                temperature=temperature,
                max_output_tokens=max_tokens,
                tags=tags,
            )
        elif provider == "groq":
            api_key = self._get_api_key(provider, settings.groq_api_key)
            return ChatGroq(
                model=model,
                api_key=api_key,
                temperature=temperature,
                max_tokens=max_tokens,
                tags=tags,
            )
        elif provider == "openrouter":
            api_key = self._get_api_key(provider, settings.openrouter_api_key)
            return ChatOpenAI(
                model=model,
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                temperature=temperature,
                max_tokens=max_tokens,
                streaming=streaming,
                default_headers={
                    "HTTP-Referer": "https://sutra.local",
                    "X-Title": "Sutra AI Orchestrator",
                },
                tags=tags,
            )
        elif provider == "perplexity":
            api_key = self._get_api_key(provider, settings.perplexity_api_key)
            return ChatOpenAI(
                model=model,
                api_key=api_key,
                base_url="https://api.perplexity.ai",
                temperature=temperature,
                max_tokens=max_tokens,
                streaming=streaming,
                tags=tags,
            )
        elif provider == "clod":
            api_key = self._get_api_key(provider, settings.clod_api_key)
            return ChatOpenAI(
                model=model,
                api_key=api_key,
                base_url="https://api.clod.io/v1",
                temperature=temperature,
                max_tokens=max_tokens,
                streaming=streaming,
                tags=tags,
            )
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

    def _get_api_key(self, provider: str, fallback: str = "") -> str:
        """Get API key from registered providers, os.environ, or settings fallback."""
        import os as _os
        config = self._providers.get(provider, {})
        # 1. Registry (populated from LLMProvider DB table at startup)
        # 2. Live os.environ (catches runtime env changes for non-vault keys)
        # 3. settings fallback (from .env at startup)
        env_key = f"{provider.upper()}_API_KEY"
        key = config.get("api_key", "") or _os.environ.get(env_key, "") or fallback
        if not key:
            raise ValueError(
                f"No API key configured for provider '{provider}'. "
                "Set it via the UI or environment variable."
            )
        return key

    async def discover_ollama_models(self) -> list[dict]:
        """Query the local Ollama instance for available models."""
        import os as _os
        ollama_url = _os.environ.get("OLLAMA_BASE_URL") or settings.ollama_base_url
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{ollama_url}/api/tags")
                response.raise_for_status()
                data = response.json()
                models = []
                for m in data.get("models", []):
                    models.append({
                        "name": m["name"],
                        "size": self._format_size(m.get("size", 0)),
                        "modified_at": m.get("modified_at", ""),
                        "details": m.get("details"),
                    })
                return models
        except Exception as e:
            logger.warning(f"Failed to connect to Ollama: {e}")
            return []

    async def check_ollama_connection(self) -> bool:
        """Check if Ollama is reachable."""
        import os as _os
        ollama_url = _os.environ.get("OLLAMA_BASE_URL") or settings.ollama_base_url
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{ollama_url}/api/tags")
                return response.status_code == 200
        except Exception:
            return False

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format byte count to human-readable string."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"

    async def fetch_openrouter_models(self) -> list[dict]:
        """Fetch available models from the OpenRouter API."""
        import os as _os
        api_key = self._providers.get("openrouter", {}).get("api_key", "") or _os.environ.get("OPENROUTER_API_KEY", "") or settings.openrouter_api_key
        if not api_key:
            logger.warning("No OpenRouter API key configured — cannot fetch model list.")
            return []
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                response.raise_for_status()
                data = response.json()
                models = []
                for m in data.get("data", []):
                    ctx = m.get("context_length", 0)
                    models.append({
                        "id": m["id"],
                        "name": m.get("name", m["id"]),
                        "context_length": ctx,
                        "description": m.get("description", ""),
                        "pricing": m.get("pricing", {}),
                    })
                # Sort by name for readability
                models.sort(key=lambda x: x["name"].lower())
                return models
        except Exception as e:
            logger.warning(f"Failed to fetch OpenRouter models: {e}")
            return []

    async def fetch_gemini_models(self) -> list[dict]:
        """Fetch available models from the Google Gemini API."""
        import os as _os
        api_key = self._providers.get("google", {}).get("api_key", "") or _os.environ.get("GOOGLE_API_KEY", "") or settings.google_api_key
        if not api_key:
            logger.warning("No Google API key configured — cannot fetch model list.")
            return []
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    params={"key": api_key},
                )
                response.raise_for_status()
                data = response.json()
                models = []
                for m in data.get("models", []):
                    # Only include models that support content generation (chat)
                    methods = m.get("supportedGenerationMethods", [])
                    if "generateContent" not in methods:
                        continue
                    # Model name comes as "models/gemini-1.5-pro" — strip the prefix
                    model_id = m.get("name", "").removeprefix("models/")
                    models.append({
                        "id": model_id,
                        "name": m.get("displayName", model_id),
                        "description": m.get("description", ""),
                        "input_token_limit": m.get("inputTokenLimit", 0),
                        "output_token_limit": m.get("outputTokenLimit", 0),
                    })
                models.sort(key=lambda x: x["name"].lower())
                return models
        except Exception as e:
            logger.warning(f"Failed to fetch Google Gemini models: {e}")
            return []

    async def fetch_openrouter_quota(self) -> dict:
        """Fetch remaining quota/credits from the OpenRouter API."""
        import os as _os
        api_key = self._providers.get("openrouter", {}).get("api_key", "") or _os.environ.get("OPENROUTER_API_KEY", "") or settings.openrouter_api_key
        if not api_key:
            return {"error": "No OpenRouter API key configured"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://openrouter.ai/api/v1/key",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                response.raise_for_status()
                data = response.json().get("data", {})
                return {
                    "limit": data.get("limit"),
                    "limit_remaining": data.get("limit_remaining"),
                    "usage": data.get("usage"),
                    "usage_daily": data.get("usage_daily"),
                }
        except Exception as e:
            logger.warning(f"Failed to fetch OpenRouter quota: {e}")
            return {"error": str(e)}

    async def fetch_perplexity_models(self) -> list[dict]:
        """Return hardcoded available models from the Perplexity API."""
        return [
            {
                "id": "sonar-pro",
                "name": "Sonar Pro",
                "description": "Perplexity's most capable model for complex search and reasoning tasks.",
                "context_length": 200000,
            },
            {
                "id": "sonar",
                "name": "Sonar",
                "description": "Perplexity's fast, capable model for general search and everyday queries.",
                "context_length": 127000,
            },
            {
                "id": "sonar-reasoning-pro",
                "name": "Sonar Reasoning Pro",
                "description": "Perplexity's most advanced reasoning model.",
                "context_length": 127000,
            },
            {
                "id": "sonar-reasoning",
                "name": "Sonar Reasoning",
                "description": "Perplexity's advanced reasoning model.",
                "context_length": 127000,
            },
        ]

    async def fetch_clod_models(self) -> list[dict]:
        """Fetch available models from the Clod.io API."""
        import os as _os
        api_key = self._providers.get("clod", {}).get("api_key", "") or _os.environ.get("CLOD_API_KEY", "") or settings.clod_api_key
        if not api_key:
            logger.warning("No Clod.io API key configured — cannot fetch model list.")
            return []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://api.clod.io/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                response.raise_for_status()
                data = response.json()
                models = []
                for m in data.get("data", []):
                    models.append({
                        "id": m["id"],
                        "name": m.get("id", m["id"]),
                        "context_length": m.get("context_length", 0),
                        "description": m.get("description", ""),
                    })
                models.sort(key=lambda x: x["name"].lower())
                return models
        except Exception as e:
            logger.warning(f"Failed to fetch Clod.io models: {e}")
            return []

    async def fetch_groq_models(self) -> list[dict]:
        """Fetch available models from the Groq API."""
        import os as _os
        api_key = self._providers.get("groq", {}).get("api_key", "") or _os.environ.get("GROQ_API_KEY", "") or settings.groq_api_key
        if not api_key:
            logger.warning("No Groq API key configured — cannot fetch model list.")
            return []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                response.raise_for_status()
                data = response.json()
                models = []
                for m in data.get("data", []):
                    # Filter out purely audio models or internal ones if necessary
                    models.append({
                        "id": m["id"],
                        "name": m.get("id", m["id"]),
                        "context_length": m.get("context_window", 0),
                        "description": m.get("description", ""),
                    })
                models.sort(key=lambda x: x["name"].lower())
                return models
        except Exception as e:
            logger.warning(f"Failed to fetch Groq models: {e}")
            return []


# Global singleton
llm_registry = LLMRegistry()
