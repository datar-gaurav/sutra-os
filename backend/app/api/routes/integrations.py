"""Integration management routes — CRUD for third-party service credentials."""

import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import IntegrationCreate, IntegrationResponse, IntegrationUpdate
from app.core.vault import decrypt_secret, encrypt_secret
from app.db.session import get_db
from app.models.integration import INTEGRATION_TYPES, Integration

router = APIRouter(prefix="/integrations", tags=["integrations"])
logger = logging.getLogger(__name__)


def _to_response(row: Integration) -> IntegrationResponse:
    return IntegrationResponse(
        id=row.id,
        type=row.type,
        name=row.name,
        agent_id=row.agent_id,
        extra_config=row.extra_config or {},
        is_active=row.is_active,
        has_credentials=bool(row.credentials_enc),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/types")
async def list_integration_types():
    """Return the static list of supported integration types with their UI metadata."""
    return INTEGRATION_TYPES


@router.get("/", response_model=list[IntegrationResponse])
async def list_integrations(
    agent_id: str | None = None,
    type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(Integration).order_by(Integration.created_at.desc())
    if agent_id is not None:
        q = q.where(Integration.agent_id == agent_id)
    if type is not None:
        q = q.where(Integration.type == type)
    result = await db.execute(q)
    return [_to_response(r) for r in result.scalars().all()]


@router.post("/", response_model=IntegrationResponse, status_code=status.HTTP_201_CREATED)
async def create_integration(
    body: IntegrationCreate,
    db: AsyncSession = Depends(get_db),
):
    if body.type not in INTEGRATION_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown integration type: {body.type}")

    creds_enc: str | None = None
    if body.credentials:
        creds_enc = encrypt_secret(json.dumps(body.credentials))

    row = Integration(
        type=body.type,
        name=body.name,
        agent_id=body.agent_id,
        credentials_enc=creds_enc,
        extra_config=body.extra_config,
        is_active=body.is_active,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _to_response(row)


@router.get("/{integration_id}", response_model=IntegrationResponse)
async def get_integration(integration_id: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(Integration, integration_id)
    if not row:
        raise HTTPException(status_code=404, detail="Integration not found")
    return _to_response(row)


@router.put("/{integration_id}", response_model=IntegrationResponse)
async def update_integration(
    integration_id: str,
    body: IntegrationUpdate,
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(Integration, integration_id)
    if not row:
        raise HTTPException(status_code=404, detail="Integration not found")

    if body.name is not None:
        row.name = body.name
    if body.agent_id is not None:
        row.agent_id = body.agent_id
    if body.extra_config is not None:
        row.extra_config = body.extra_config
    if body.is_active is not None:
        row.is_active = body.is_active
    if body.credentials is not None:
        row.credentials_enc = encrypt_secret(json.dumps(body.credentials))

    await db.commit()
    await db.refresh(row)
    return _to_response(row)


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(integration_id: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(Integration, integration_id)
    if not row:
        raise HTTPException(status_code=404, detail="Integration not found")
    await db.delete(row)
    await db.commit()


@router.post("/{integration_id}/test")
async def test_integration(integration_id: str, db: AsyncSession = Depends(get_db)):
    """Test an integration by making a lightweight API call to verify the credentials."""
    row = await db.get(Integration, integration_id)
    if not row:
        raise HTTPException(status_code=404, detail="Integration not found")
    if not row.credentials_enc:
        raise HTTPException(status_code=400, detail="No credentials stored")

    creds = json.loads(decrypt_secret(row.credentials_enc))
    cfg = row.extra_config or {}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if row.type == "notion":
                resp = await client.get(
                    "https://api.notion.com/v1/users/me",
                    headers={"Authorization": f"Bearer {creds['api_key']}", "Notion-Version": "2022-06-28"},
                )
                resp.raise_for_status()
                data = resp.json()
                return {"ok": True, "detail": f"Connected as {data.get('name', data.get('id', 'unknown'))}"}

            elif row.type == "linear":
                resp = await client.post(
                    "https://api.linear.app/graphql",
                    headers={"Authorization": creds["api_key"], "Content-Type": "application/json"},
                    json={"query": "{ viewer { id name email } }"},
                )
                resp.raise_for_status()
                viewer = resp.json().get("data", {}).get("viewer", {})
                return {"ok": True, "detail": f"Connected as {viewer.get('name', viewer.get('email', 'unknown'))}"}

            elif row.type == "jira":
                base_url = cfg.get("base_url", "").rstrip("/")
                resp = await client.get(
                    f"{base_url}/rest/api/3/myself",
                    auth=(creds["email"], creds["api_token"]),
                    headers={"Accept": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
                return {"ok": True, "detail": f"Connected as {data.get('displayName', data.get('accountId', 'unknown'))}"}

            elif row.type == "slack":
                resp = await client.post(
                    "https://slack.com/api/auth.test",
                    headers={"Authorization": f"Bearer {creds['bot_token']}"},
                )
                resp.raise_for_status()
                data = resp.json()
                if not data.get("ok"):
                    return {"ok": False, "detail": data.get("error", "Auth failed")}
                return {"ok": True, "detail": f"Connected to {data.get('team')} as {data.get('user')}"}

            elif row.type == "gitlab":
                base_url = cfg.get("base_url", "https://gitlab.com").rstrip("/")
                resp = await client.get(
                    f"{base_url}/api/v4/user",
                    headers={"PRIVATE-TOKEN": creds["private_token"]},
                )
                resp.raise_for_status()
                data = resp.json()
                return {"ok": True, "detail": f"Connected as {data.get('username', data.get('name', 'unknown'))}"}

            elif row.type == "github":
                resp = await client.get(
                    "https://api.github.com/user",
                    headers={
                        "Authorization": f"token {creds['token']}",
                        "Accept": "application/vnd.github+json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return {"ok": True, "detail": f"Connected as {data.get('login', 'unknown')}"}

            elif row.type == "google_drive":
                from google.auth.transport.requests import Request
                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build
                from app.config import settings as _settings
                refresh_token = creds.get("refresh_token")
                if not refresh_token:
                    return {"ok": False, "detail": "No refresh token stored. Please reconnect."}
                drive_creds = Credentials(
                    token=None,
                    refresh_token=refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=_settings.google_client_id,
                    client_secret=_settings.google_client_secret,
                )
                drive_creds.refresh(Request())
                drive_service = build("drive", "v3", credentials=drive_creds, cache_discovery=False)
                about = drive_service.about().get(fields="user").execute()
                user = about.get("user", {})
                name = user.get("displayName") or user.get("emailAddress", "unknown")
                return {"ok": True, "detail": f"Connected as {name}"}

            elif row.type == "google_calendar":
                from google.auth.transport.requests import Request
                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build
                from app.config import settings as _settings
                refresh_token = creds.get("refresh_token")
                if not refresh_token:
                    return {"ok": False, "detail": "No refresh token stored. Please reconnect."}
                gcal_creds = Credentials(
                    token=None,
                    refresh_token=refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=_settings.google_client_id,
                    client_secret=_settings.google_client_secret,
                )
                gcal_creds.refresh(Request())
                calendar_service = build("calendar", "v3", credentials=gcal_creds, cache_discovery=False)
                # Just fetch the primary calendar metadata to test
                cal = calendar_service.calendars().get(calendarId="primary").execute()
                return {"ok": True, "detail": f"Connected to calendar: {cal.get('summary', 'primary')}"}

            else:
                return {"ok": False, "detail": f"No test available for type: {row.type}"}

    except httpx.HTTPStatusError as e:
        return {"ok": False, "detail": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        logger.warning("Integration test failed: %s", e)
        return {"ok": False, "detail": str(e)}
