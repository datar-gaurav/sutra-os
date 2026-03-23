"""Email configuration and whitelist management API."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    EmailConfigCreate,
    EmailConfigResponse,
    EmailConfigUpdate,
    EmailWhitelistCreate,
    EmailWhitelistResponse,
    EmailTestRequest,
)
from app.core.vault import encrypt_secret, decrypt_secret
from app.db.session import get_db
from app.models.email import EmailConfig, EmailWhitelist

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/email", tags=["email"])


# ─── Email Config ─────────────────────────────────────────────────────────────

@router.get("/configs", response_model=list[EmailConfigResponse])
async def list_email_configs(db: AsyncSession = Depends(get_db)):
    """List all email configurations (system default + per-agent)."""
    result = await db.execute(select(EmailConfig).order_by(EmailConfig.created_at))
    return result.scalars().all()


@router.get("/configs/{config_id}", response_model=EmailConfigResponse)
async def get_email_config(config_id: str, db: AsyncSession = Depends(get_db)):
    cfg = await db.get(EmailConfig, config_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Email config not found")
    return cfg


@router.get("/configs/agent/{agent_id}", response_model=EmailConfigResponse)
async def get_agent_email_config(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Get email config for a specific agent (falls back to system default if none)."""
    result = await db.execute(
        select(EmailConfig).where(EmailConfig.agent_id == agent_id)
    )
    cfg = result.scalars().first()
    if cfg is None:
        # Try system default
        result = await db.execute(
            select(EmailConfig).where(EmailConfig.agent_id == None)  # noqa: E711
        )
        cfg = result.scalars().first()
    if not cfg:
        raise HTTPException(status_code=404, detail="No email config found")
    return cfg


@router.post("/configs", response_model=EmailConfigResponse, status_code=201)
async def create_email_config(payload: EmailConfigCreate, db: AsyncSession = Depends(get_db)):
    """Create an email configuration. Set agent_id=null for the system default."""
    # Enforce uniqueness per agent_id (including null for system)
    existing = await db.execute(
        select(EmailConfig).where(EmailConfig.agent_id == payload.agent_id)
    )
    if existing.scalars().first():
        scope = f"agent '{payload.agent_id}'" if payload.agent_id else "system default"
        raise HTTPException(status_code=409, detail=f"Email config already exists for {scope}. Use PUT to update.")

    cfg = EmailConfig(
        agent_id=payload.agent_id,
        label=payload.label,
        smtp_host=payload.smtp_host,
        smtp_port=payload.smtp_port,
        smtp_username=payload.smtp_username,
        smtp_password=encrypt_secret(payload.smtp_password),
        smtp_from_email=payload.smtp_from_email,
        smtp_from_name=payload.smtp_from_name,
        smtp_use_tls=payload.smtp_use_tls,
        smtp_use_ssl=payload.smtp_use_ssl,
        imap_host=payload.imap_host,
        imap_port=payload.imap_port,
        imap_username=payload.imap_username,
        imap_password=encrypt_secret(payload.imap_password) if payload.imap_password else None,
        imap_use_ssl=payload.imap_use_ssl,
        imap_folder=payload.imap_folder,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    logger.info(f"Created email config {cfg.id} for agent_id={cfg.agent_id}")
    return cfg


@router.put("/configs/{config_id}", response_model=EmailConfigResponse)
async def update_email_config(
    config_id: str, payload: EmailConfigUpdate, db: AsyncSession = Depends(get_db)
):
    cfg = await db.get(EmailConfig, config_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Email config not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "smtp_password" and value:
            value = encrypt_secret(value)
        elif field == "imap_password" and value:
            value = encrypt_secret(value)
        setattr(cfg, field, value)

    await db.commit()
    await db.refresh(cfg)
    return cfg


@router.delete("/configs/{config_id}", status_code=204)
async def delete_email_config(config_id: str, db: AsyncSession = Depends(get_db)):
    cfg = await db.get(EmailConfig, config_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Email config not found")
    await db.delete(cfg)
    await db.commit()


@router.post("/configs/{config_id}/test")
async def test_email_config(
    config_id: str, payload: EmailTestRequest, db: AsyncSession = Depends(get_db)
):
    """Send a test email using the specified config to verify it works."""
    import asyncio
    import smtplib
    import ssl
    from email.mime.text import MIMEText

    cfg = await db.get(EmailConfig, config_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Email config not found")

    smtp_password = decrypt_secret(cfg.smtp_password) if cfg.provider != "GMAIL" else None

    msg = MIMEText("This is a test email from Sutra. Your email configuration is working correctly.", "plain", "utf-8")
    msg["Subject"] = "Sutra Email Config Test"
    
    if cfg.provider == "GMAIL":
        msg["From"] = cfg.google_email
    else:
        msg["From"] = cfg.smtp_from_email
        
    msg["To"] = payload.to

    def _send():
        if cfg.provider == "GMAIL":
            import base64
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from app.config import settings

            if_refresh = decrypt_secret(cfg.google_refresh_token) if cfg.google_refresh_token else None
            if not if_refresh:
                raise Exception("Google refresh token is missing. Please reconnect your account.")

            creds = Credentials(
                token=None,
                refresh_token=if_refresh,
                client_id=settings.google_client_id,
                client_secret=settings.google_client_secret,
                token_uri="https://oauth2.googleapis.com/token",
            )
            service = build("gmail", "v1", credentials=creds)
            encoded_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            create_message = {"raw": encoded_message}
            service.users().messages().send(userId="me", body=create_message).execute()
            return
            
        ctx = ssl.create_default_context()
        if cfg.smtp_use_ssl:
            with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, context=ctx) as server:
                server.login(cfg.smtp_username, smtp_password)
                server.sendmail(cfg.smtp_from_email, [payload.to], msg.as_string())
        else:
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port) as server:
                if cfg.smtp_use_tls:
                    server.starttls(context=ctx)
                server.login(cfg.smtp_username, smtp_password)
                server.sendmail(cfg.smtp_from_email, [payload.to], msg.as_string())

    try:
        await asyncio.get_event_loop().run_in_executor(None, _send)
        return {"status": "ok", "message": f"Test email sent to {payload.to}"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"SMTP error: {exc}")


# ─── Email Whitelist ───────────────────────────────────────────────────────────

@router.get("/whitelist", response_model=list[EmailWhitelistResponse])
async def list_whitelist(agent_id: str | None = None, db: AsyncSession = Depends(get_db)):
    """List whitelist entries. Pass agent_id to filter by agent (or null for global entries)."""
    q = select(EmailWhitelist).order_by(EmailWhitelist.email_address)
    if agent_id is not None:
        q = q.where(EmailWhitelist.agent_id == agent_id)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/whitelist", response_model=EmailWhitelistResponse, status_code=201)
async def add_whitelist_entry(payload: EmailWhitelistCreate, db: AsyncSession = Depends(get_db)):
    """Add an email address to the whitelist for an agent (or globally if agent_id=null)."""
    # Check for duplicate
    existing = await db.execute(
        select(EmailWhitelist).where(
            EmailWhitelist.agent_id == payload.agent_id,
            EmailWhitelist.email_address == payload.email_address.lower(),
        )
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="This email is already whitelisted for this agent.")

    entry = EmailWhitelist(
        agent_id=payload.agent_id,
        email_address=payload.email_address.lower(),
        label=payload.label,
        is_active=payload.is_active,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    logger.info(f"Whitelisted {entry.email_address} for agent_id={entry.agent_id}")
    return entry


@router.put("/whitelist/{entry_id}", response_model=EmailWhitelistResponse)
async def update_whitelist_entry(
    entry_id: str,
    payload: EmailWhitelistCreate,
    db: AsyncSession = Depends(get_db),
):
    entry = await db.get(EmailWhitelist, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Whitelist entry not found")
    entry.email_address = payload.email_address.lower()
    entry.label = payload.label
    entry.is_active = payload.is_active
    await db.commit()
    await db.refresh(entry)
    return entry


@router.delete("/whitelist/{entry_id}", status_code=204)
async def remove_whitelist_entry(entry_id: str, db: AsyncSession = Depends(get_db)):
    entry = await db.get(EmailWhitelist, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Whitelist entry not found")
    await db.delete(entry)
    await db.commit()
