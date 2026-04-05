"""Authentication routes: register, login, refresh, logout, me, API keys."""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    ApiKeyCreate, ApiKeyCreatedResponse, ApiKeyResponse,
    LogoutRequest, RefreshRequest, TokenResponse, UserCreate, UserLogin, UserResponse,
)
from app.config import settings
from app.core.rate_limiter import limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.api_key import ApiKey
from app.models.user import User, UserRole

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
@limiter.limit(lambda: settings.rate_limit_auth_register)
async def register(request: Request, data: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    result2 = await db.execute(select(User).where(User.username == data.username))
    if result2.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already taken")

    # First registered user becomes owner
    count = (await db.execute(select(func.count()).select_from(User))).scalar()
    role = UserRole.owner if count == 0 else UserRole.operator

    user = User(
        email=data.email,
        username=data.username,
        hashed_password=hash_password(data.password),
        role=role,
        last_login=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    user_resp = UserResponse.model_validate(user)
    user_resp.is_first_login = True

    return TokenResponse(
        access_token=create_access_token(user.id, user.email, user.role.value),
        refresh_token=create_refresh_token(user.id),
        token_type="bearer",
        user=user_resp,
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit(lambda: settings.rate_limit_auth_login)
async def login(request: Request, data: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account disabled")

    is_first_login = user.last_login is None
    user.last_login = datetime.now(timezone.utc)
    await db.commit()

    user_resp = UserResponse.model_validate(user)
    user_resp.is_first_login = is_first_login

    return TokenResponse(
        access_token=create_access_token(user.id, user.email, user.role.value),
        refresh_token=create_refresh_token(user.id),
        token_type="bearer",
        user=user_resp,
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit(lambda: settings.rate_limit_auth_refresh)
async def refresh(request: Request, data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = await decode_refresh_token(data.refresh_token)

    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")

    # Blacklist the consumed refresh token
    jti = payload.get("jti")
    if jti:
        from app.core.token_blacklist import blacklist_token
        await blacklist_token(jti, int(payload["exp"]))

    return TokenResponse(
        access_token=create_access_token(user.id, user.email, user.role.value),
        refresh_token=create_refresh_token(user.id),
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.post("/logout", status_code=204)
async def logout(data: LogoutRequest):
    """Revoke a refresh token so it cannot be used again."""
    try:
        payload = decode_token(data.refresh_token)
        if payload.get("type") == "refresh":
            jti = payload.get("jti")
            if jti:
                from app.core.token_blacklist import blacklist_token
                await blacklist_token(jti, int(payload["exp"]))
    except Exception:
        pass  # Always return 204 — don't reveal token state


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


# ─── API Key Management ────────────────────────────────────────────────────────

@router.post("/api-keys", response_model=ApiKeyCreatedResponse, status_code=201)
async def create_api_key(
    data: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a new API key for the current user. The full key is shown only once."""
    raw_key = "sk-sutra_" + os.urandom(24).hex()
    key_prefix = raw_key[:16]
    key_hash = bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()

    expires_at = None
    if data.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=data.expires_in_days)

    api_key = ApiKey(
        user_id=current_user.id,
        name=data.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return ApiKeyCreatedResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        is_active=api_key.is_active,
        last_used_at=api_key.last_used_at,
        expires_at=api_key.expires_at,
        created_at=api_key.created_at,
        key=raw_key,
    )


@router.get("/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all API keys for the current user (prefix only, no raw key)."""
    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.user_id == current_user.id)
        .order_by(ApiKey.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke (deactivate) an API key by ID."""
    api_key = await db.get(ApiKey, key_id)
    if not api_key or api_key.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="API key not found")
    api_key.is_active = False
    await db.commit()
