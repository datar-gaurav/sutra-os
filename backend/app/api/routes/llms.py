"""LLM provider management routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import LLMProviderCreate, LLMProviderResponse, LLMProviderUpdate, OllamaModel, GroqModel
from app.core.llm_registry import llm_registry
from app.core.vault import decrypt_secret, encrypt_secret
from app.db.session import get_db
from app.models.llm_provider import LLMProvider

router = APIRouter(prefix="/llms", tags=["llms"])


@router.get("/", response_model=list[LLMProviderResponse])
async def list_providers(db: AsyncSession = Depends(get_db)):
    """List all configured LLM providers."""
    result = await db.execute(select(LLMProvider).order_by(LLMProvider.name))
    providers = result.scalars().all()

    response = []
    for p in providers:
        data = LLMProviderResponse.model_validate(p)
        data.has_api_key = bool(p.api_key_encrypted)
        response.append(data)
    return response


@router.post("/", response_model=LLMProviderResponse, status_code=201)
async def create_provider(payload: LLMProviderCreate, db: AsyncSession = Depends(get_db)):
    """Create a new LLM provider."""
    provider = LLMProvider(
        name=payload.name,
        provider_type=payload.provider_type,
        base_url=payload.base_url,
        api_key_encrypted=encrypt_secret(payload.api_key) if payload.api_key else "",
        is_default=payload.is_default,
        supports_tool_calling=payload.supports_tool_calling,
    )
    db.add(provider)
    try:
        await db.flush()
        await db.refresh(provider)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Provider with this name already exists")

    # Register in the LLM registry (pass plaintext key — it was already stored encrypted)
    llm_registry.register_provider(
        name=provider.provider_type,
        provider_type=provider.provider_type,
        api_key=payload.api_key or "",
        base_url=provider.base_url or "",
        supports_tool_calling=provider.supports_tool_calling,
    )

    data = LLMProviderResponse.model_validate(provider)
    data.has_api_key = bool(provider.api_key_encrypted)
    return data


@router.put("/{provider_id}", response_model=LLMProviderResponse)
async def update_provider(
    provider_id: str, payload: LLMProviderUpdate, db: AsyncSession = Depends(get_db)
):
    """Update an LLM provider."""
    provider = await db.get(LLMProvider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if payload.name is not None:
        provider.name = payload.name
    if payload.base_url is not None:
        provider.base_url = payload.base_url
    if payload.api_key is not None:
        provider.api_key_encrypted = encrypt_secret(payload.api_key) if payload.api_key else ""
    if payload.is_enabled is not None:
        provider.is_enabled = payload.is_enabled
    if payload.is_default is not None:
        provider.is_default = payload.is_default
    if payload.supports_tool_calling is not None:
        provider.supports_tool_calling = payload.supports_tool_calling

    await db.flush()
    await db.refresh(provider)

    # Re-register in the LLM registry so the updated key/url takes effect immediately
    if payload.api_key is not None:
        from app.core.vault import decrypt_secret as _dec
        plain_key = payload.api_key or (
            _dec(provider.api_key_encrypted) if provider.api_key_encrypted else ""
        )
        llm_registry.register_provider(
            name=provider.provider_type,
            provider_type=provider.provider_type,
            api_key=plain_key,
            base_url=provider.base_url or "",
            supports_tool_calling=provider.supports_tool_calling,
        )

    data = LLMProviderResponse.model_validate(provider)
    data.has_api_key = bool(provider.api_key_encrypted)
    return data


@router.delete("/{provider_id}", status_code=204)
async def delete_provider(provider_id: str, db: AsyncSession = Depends(get_db)):
    """Delete an LLM provider."""
    provider = await db.get(LLMProvider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    await db.delete(provider)


# ─── Ollama Discovery ─────────────────────────────────────────────────────────

@router.get("/ollama/models", response_model=list[OllamaModel])
async def list_ollama_models():
    """List locally available Ollama models."""
    models = await llm_registry.discover_ollama_models()
    return models


@router.get("/ollama/status")
async def ollama_status():
    """Check Ollama connection status."""
    connected = await llm_registry.check_ollama_connection()
    return {"connected": connected}


# ─── OpenRouter Discovery ──────────────────────────────────────────────────────

@router.get("/openrouter/models")
async def list_openrouter_models():
    """Fetch available models from OpenRouter API."""
    models = await llm_registry.fetch_openrouter_models()
    return models


# ─── Google Gemini Discovery ───────────────────────────────────────────────────

@router.get("/google/models")
async def list_google_models():
    """Fetch available models from Google Gemini API."""
    models = await llm_registry.fetch_gemini_models()
    return models


# ─── Perplexity Discovery ──────────────────────────────────────────────────────

@router.get("/perplexity/models")
async def list_perplexity_models():
    """Fetch available models from Perplexity API."""
    models = await llm_registry.fetch_perplexity_models()
    return models


# ─── Groq Discovery ────────────────────────────────────────────────────────────

@router.get("/groq/models", response_model=list[GroqModel])
async def list_groq_models():
    """Fetch available models from Groq API."""
    models = await llm_registry.fetch_groq_models()
    return models


# ─── Clod.io Discovery ─────────────────────────────────────────────────────────

@router.get("/clod/models", response_model=list[GroqModel])
async def list_clod_models():
    """Fetch available models from Clod.io API."""
    models = await llm_registry.fetch_clod_models()
    return models


# ─── OpenRouter Quota ──────────────────────────────────────────────────────────

@router.get("/openrouter/quota")
async def openrouter_quota():
    """Fetch remaining credits/quota from OpenRouter."""
    quota = await llm_registry.fetch_openrouter_quota()
    return quota


# ─── Anthropic Discovery ───────────────────────────────────────────────────────

@router.get("/anthropic/models")
async def list_anthropic_models():
    """Fetch available models from the Anthropic API."""
    return await llm_registry.fetch_anthropic_models()


# ─── OpenAI Discovery ──────────────────────────────────────────────────────────

@router.get("/openai/models")
async def list_openai_models():
    """Fetch available chat-capable models from the OpenAI API."""
    return await llm_registry.fetch_openai_models()


# ─── NVIDIA NIM Discovery ──────────────────────────────────────────────────────

@router.get("/nvidia_nim/models", response_model=list[GroqModel])
async def list_nvidia_nim_models():
    """Fetch available models from the NVIDIA NIM API."""
    models = await llm_registry.fetch_nvidia_nim_models()
    return models
