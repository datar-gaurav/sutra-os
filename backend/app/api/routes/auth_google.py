"""Google OAuth 2.0 routes — Gmail and Google Drive integration."""

import json
import logging
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.vault import encrypt_secret
from app.db.session import get_db
from app.models.email import EmailConfig
from app.models.integration import Integration

router = APIRouter(prefix="/auth/google", tags=["auth"])
logger = logging.getLogger(__name__)

_GMAIL_SCOPES = [
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/userinfo.email",
]
_DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/userinfo.email",
]
_CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/userinfo.email",
]


@router.get("/login")
async def google_login(request: Request, agent_id: str | None = None, service: str = "gmail"):
    """Redirect to Google consent screen for Gmail (service=gmail) or Drive (service=drive)."""
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth credentials are not configured in the backend (.env)",
        )

    redirect_uri = str(request.base_url).rstrip("/") + "/api/auth/google/callback"
    # Encode both agent_id and service into state so the callback can route correctly.
    # Format: "<agent_id>:<service>"  — agent_id may be empty string.
    state = f"{agent_id or ''}:{service}"

    if service == "drive":
        scopes = _DRIVE_SCOPES
    elif service == "calendar":
        scopes = _CALENDAR_SCOPES
    else:
        scopes = _GMAIL_SCOPES

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",  # force refresh token on every connect
        "state": state,
    }
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return RedirectResponse(url)


@router.get("/callback")
async def google_callback(
    request: Request,
    code: str,
    state: str = "",
    db: AsyncSession = Depends(get_db),
):
    """Exchange auth code for tokens and persist to the correct integration."""
    redirect_uri = str(request.base_url).rstrip("/") + "/api/auth/google/callback"

    # Parse state — new format: "<agent_id>:<service>"; old format: "<agent_id>" (Gmail only)
    if ":" in state:
        agent_id_part, service = state.rsplit(":", 1)
    else:
        agent_id_part, service = state, "gmail"
    agent_id = agent_id_part or None

    async with httpx.AsyncClient() as client:
        # 1. Exchange code for tokens
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )
        if token_resp.status_code != 200:
            logger.error("Google OAuth token error: %s", token_resp.text)
            raise HTTPException(status_code=400, detail="Failed to exchange authorization code")

        tokens = token_resp.json()
        access_token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token")

        if not refresh_token:
            logger.warning("No refresh token received during Google OAuth flow.")

        # 2. Get user email
        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        userinfo_resp.raise_for_status()
        email_address = userinfo_resp.json().get("email")

    if not email_address:
        raise HTTPException(status_code=400, detail="Could not retrieve email from Google")

    frontend_url = settings.cors_origins_list[0] if settings.cors_origins_list else "http://localhost:3000"

    if service == "drive":
        await _save_drive_integration(db, agent_id, email_address, refresh_token)
        return RedirectResponse(f"{frontend_url}/google-drive")
    elif service == "calendar":
        await _save_calendar_integration(db, agent_id, email_address, refresh_token)
        return RedirectResponse(f"{frontend_url}/google-calendar")
    else:
        await _save_gmail_config(db, agent_id, email_address, refresh_token)
        return RedirectResponse(f"{frontend_url}/email")


async def _save_gmail_config(
    db: AsyncSession,
    agent_id: str | None,
    email_address: str,
    refresh_token: str | None,
) -> None:
    result = await db.execute(select(EmailConfig).where(EmailConfig.agent_id == agent_id))
    cfg = result.scalars().first()

    if cfg:
        cfg.provider = "GMAIL"
        cfg.google_email = email_address
        if refresh_token:
            cfg.google_refresh_token = encrypt_secret(refresh_token)
    else:
        cfg = EmailConfig(
            agent_id=agent_id,
            provider="GMAIL",
            google_email=email_address,
            smtp_host=None,
            smtp_port=587,
            smtp_username=None,
            smtp_password=None,
            smtp_from_email=None,
            google_refresh_token=encrypt_secret(refresh_token) if refresh_token else None,
        )
        db.add(cfg)
    await db.commit()


async def _save_drive_integration(
    db: AsyncSession,
    agent_id: str | None,
    email_address: str,
    refresh_token: str | None,
) -> None:
    # Upsert: one Drive integration per agent_id (or system-wide when agent_id is None)
    result = await db.execute(
        select(Integration).where(
            Integration.type == "google_drive",
            Integration.agent_id == agent_id,
        )
    )
    row = result.scalars().first()

    creds_enc = encrypt_secret(json.dumps({"refresh_token": refresh_token})) if refresh_token else None

    if row:
        if creds_enc:
            row.credentials_enc = creds_enc
        row.extra_config = {**row.extra_config, "google_email": email_address}
        row.is_active = True
    else:
        row = Integration(
            type="google_drive",
            name=f"Google Drive ({email_address})",
            agent_id=agent_id,
            credentials_enc=creds_enc,
            extra_config={"google_email": email_address},
            is_active=True,
        )
        db.add(row)
    await db.commit()


async def _save_calendar_integration(
    db: AsyncSession,
    agent_id: str | None,
    email_address: str,
    refresh_token: str | None,
) -> None:
    # Upsert: one Calendar integration per agent_id (or system-wide when agent_id is None)
    result = await db.execute(
        select(Integration).where(
            Integration.type == "google_calendar",
            Integration.agent_id == agent_id,
        )
    )
    row = result.scalars().first()

    creds_enc = encrypt_secret(json.dumps({"refresh_token": refresh_token})) if refresh_token else None

    if row:
        if creds_enc:
            row.credentials_enc = creds_enc
        row.extra_config = {**row.extra_config, "google_email": email_address}
        row.is_active = True
    else:
        row = Integration(
            type="google_calendar",
            name=f"Google Calendar ({email_address})",
            agent_id=agent_id,
            credentials_enc=creds_enc,
            extra_config={"google_email": email_address},
            is_active=True,
        )
        db.add(row)
    await db.commit()
