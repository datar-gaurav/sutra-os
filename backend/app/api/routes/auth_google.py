"""Google OAuth 2.0 routes — Gmail and Google Drive integration."""

import json
import logging
from urllib.parse import urlencode, urlparse

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
    from app.core.env_utils import get_config, get_secret
    client_id = get_config("GOOGLE_CLIENT_ID", settings.google_client_id)
    client_secret = await get_secret("GOOGLE_CLIENT_SECRET", settings.google_client_secret)
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth credentials are not configured in the backend (.env)",
        )

    redirect_uri = str(request.base_url).rstrip("/") + "/api/auth/google/callback"
    # Capture the frontend origin from the Referer header so the callback can redirect back
    # to the correct host/port (e.g. localhost:3001 vs localhost:3000).
    referer = request.headers.get("referer", "")
    if referer:
        parsed = urlparse(referer)
        frontend_origin = f"{parsed.scheme}://{parsed.netloc}"
    else:
        frontend_origin = settings.cors_origins_list[0] if settings.cors_origins_list else "http://localhost:3000"

    # Encode agent_id, service, and frontend origin into state so the callback can route correctly.
    # Format: "<agent_id>:<service>:<frontend_origin>"  — agent_id may be empty string.
    state = f"{agent_id or ''}:{service}:{frontend_origin}"

    if service == "drive":
        scopes = _DRIVE_SCOPES
    elif service == "calendar":
        scopes = _CALENDAR_SCOPES
    else:
        scopes = _GMAIL_SCOPES

    params = {
        "client_id": client_id,
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

    # Parse state — format: "<agent_id>:<service>:<frontend_origin>"
    # Also supports legacy formats: "<agent_id>:<service>" and "<agent_id>"
    parts = state.split(":", 2) if state else []
    if len(parts) >= 3:
        agent_id_part, service, frontend_origin = parts[0], parts[1], parts[2]
    elif len(parts) == 2:
        agent_id_part, service, frontend_origin = parts[0], parts[1], ""
    else:
        agent_id_part, service, frontend_origin = state, "gmail", ""
    agent_id = agent_id_part or None

    from app.core.env_utils import get_config, get_secret
    client_id = get_config("GOOGLE_CLIENT_ID", settings.google_client_id)
    client_secret = await get_secret("GOOGLE_CLIENT_SECRET", settings.google_client_secret)

    async with httpx.AsyncClient() as client:
        # 1. Exchange code for tokens
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
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

    frontend_url = frontend_origin or (settings.cors_origins_list[0] if settings.cors_origins_list else "http://localhost:3000")

    if service == "drive":
        await _save_drive_integration(db, agent_id, email_address, refresh_token)
        return RedirectResponse(f"{frontend_url}/google-drive")
    elif service == "calendar":
        await _save_calendar_integration(db, agent_id, email_address, refresh_token)
        return RedirectResponse(f"{frontend_url}/integrations")
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
