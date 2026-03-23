"""Google Calendar integration tools — list, create, and delete events."""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import tool

from app.config import settings
from app.core.vault import decrypt_secret

logger = logging.getLogger(__name__)

GCAL_TOOL_IDS = {
    "gcal_list_events",
    "gcal_create_event",
    "gcal_delete_event",
}


async def _get_gcal_credentials(agent_id: str):
    """Fetch and refresh Google Calendar OAuth credentials for the given agent."""
    from app.db.session import async_session_factory
    from app.models.integration import Integration
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from sqlalchemy import nullslast, select

    async with async_session_factory() as db:
        result = await db.execute(
            select(Integration)
            .where(Integration.type.in_(["google_calendar", "google_drive"]), Integration.is_active == True)
            .order_by(nullslast(Integration.agent_id.desc()))
        )
        rows = result.scalars().all()

    # Priority: agent-specific gcal > system-wide gcal > agent-specific gdrive > system-wide gdrive
    agent_gcal = next((r for r in rows if r.agent_id == agent_id and r.type == "google_calendar"), None)
    system_gcal = next((r for r in rows if r.agent_id is None and r.type == "google_calendar"), None)
    agent_gdrive = next((r for r in rows if r.agent_id == agent_id and r.type == "google_drive"), None)
    system_gdrive = next((r for r in rows if r.agent_id is None and r.type == "google_drive"), None)
    
    row = agent_gcal or system_gcal or agent_gdrive or system_gdrive

    if not row or not row.credentials_enc:
        raise ValueError(
            "No active Google Calendar or Google Drive integration found. "
            "Connect Google Calendar via Settings → Integrations."
        )

    creds_data = json.loads(decrypt_secret(row.credentials_enc))
    refresh_token = creds_data.get("refresh_token")
    if not refresh_token:
        raise ValueError("Google OAuth refresh token missing. Please reconnect.")

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
    )
    creds.refresh(Request())
    return creds


async def _build_calendar_service(agent_id: str):
    """Build a Google Calendar API service client."""
    from googleapiclient.discovery import build
    creds = await _get_gcal_credentials(agent_id)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def create_google_calendar_tools(agent_id: str):

    @tool
    async def gcal_list_events(time_min: str = None, time_max: str = None, max_results: int = 20) -> str:
        """List upcoming events from the primary Google Calendar.

        Args:
            time_min: Lower bound (exclusive) for an event's end time (ISO 8601, e.g., '2024-03-19T10:00:00Z').
            time_max: Upper bound (exclusive) for an event's start time (ISO 8601).
            max_results: Max results to return (default 20).
        """
        try:
            service = await _build_calendar_service(agent_id)
            events_result = service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])

            if not events:
                return "No upcoming events found."

            lines = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                lines.append(f"- {event['summary']} ({start}) [ID: {event['id']}]")
            return "\n".join(lines)
        except Exception as e:
            logger.error("gcal_list_events error: %s", e)
            return f"Error listing Google Calendar events: {e}"

    @tool
    async def gcal_create_event(
        summary: str,
        start_time: str,
        end_time: str,
        description: str = None,
        location: str = None,
        recurrence: list[str] = None,
    ) -> str:
        """Create a new event in Google Calendar.

        Args:
            summary: Title of the event.
            start_time: Start time (ISO 8601, e.g., '2024-03-19T10:00:00Z').
            end_time: End time (ISO 8601).
            description: Optional detailed description.
            location: Optional physical location.
            recurrence: Optional list of RRULE strings for recurring events (e.g., ['RRULE:FREQ=DAILY;COUNT=5']).
        """
        try:
            service = await _build_calendar_service(agent_id)
            event_body = {
                'summary': summary,
                'location': location,
                'description': description,
                'start': {'dateTime': start_time},
                'end': {'dateTime': end_time},
            }
            if recurrence:
                event_body['recurrence'] = recurrence

            event = service.events().insert(calendarId='primary', body=event_body).execute()
            return f"Event created: '{event.get('summary')}' (ID: {event.get('id')}) | Link: {event.get('htmlLink')}"
        except Exception as e:
            logger.error("gcal_create_event error: %s", e)
            return f"Error creating Google Calendar event: {e}"

    @tool
    async def gcal_delete_event(event_id: str) -> str:
        """Delete an event from Google Calendar by its ID.

        Args:
            event_id: The ID of the event to delete.
        """
        try:
            service = await _build_calendar_service(agent_id)
            service.events().delete(calendarId='primary', eventId=event_id).execute()
            return f"Successfully deleted event {event_id}."
        except Exception as e:
            logger.error("gcal_delete_event error: %s", e)
            return f"Error deleting Google Calendar event: {e}"

    return [
        gcal_list_events,
        gcal_create_event,
        gcal_delete_event,
    ]
