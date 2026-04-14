"""Tool exposed to agents (Resume Builder) to update a job application row."""

import logging
from datetime import datetime, timezone

from langchain_core.tools import tool

from app.db.session import async_session_factory
from app.models.job_application import JOB_STATUSES, JobApplication

logger = logging.getLogger(__name__)


@tool
async def update_job_application(
    application_id: str,
    resume_drive_url: str | None = None,
    resume_drive_file_id: str | None = None,
    analysis_drive_url: str | None = None,
    fit_score: int | None = None,
    status: str | None = None,
    notes: str | None = None,
) -> str:
    """Patch an existing job_application row after tailoring a resume.

    Use this after saving a tailored resume to Google Drive so the job dashboard
    reflects the generated artifacts.

    Args:
        application_id: The UUID passed into the agent trigger payload as `application_id`.
        resume_drive_url: Public/shareable URL of the tailored resume on Google Drive.
        resume_drive_file_id: Drive file ID of the tailored resume.
        analysis_drive_url: URL of the fit-analysis.md written alongside the resume.
        fit_score: Integer 0-100 from your analysis.
        status: Optional new status (e.g. "resume_generated"). Must be one of the
            allowed statuses or this field is ignored.
        notes: Free-form markdown notes to append/save on the application.

    Returns:
        Human-readable confirmation or an error string.
    """
    async with async_session_factory() as db:
        row = await db.get(JobApplication, application_id)
        if not row:
            return f"No job_application found with id {application_id}"

        if resume_drive_url is not None:
            row.resume_drive_url = resume_drive_url
        if resume_drive_file_id is not None:
            row.resume_drive_file_id = resume_drive_file_id
        if analysis_drive_url is not None:
            row.analysis_drive_url = analysis_drive_url
        if fit_score is not None:
            row.fit_score = int(fit_score)
        if notes is not None:
            row.notes = notes
        if status and status in JOB_STATUSES and status != row.status:
            row.status = status
            row.last_status_change_at = datetime.now(timezone.utc)
        elif status and resume_drive_url and row.status == "captured":
            # Auto-advance when a resume shows up
            row.status = "resume_generated"
            row.last_status_change_at = datetime.now(timezone.utc)

        # If resume added but no explicit status given, advance to resume_generated
        if resume_drive_url and row.status == "captured" and not status:
            row.status = "resume_generated"
            row.last_status_change_at = datetime.now(timezone.utc)

        await db.commit()
        return (
            f"Updated job_application {application_id}: status={row.status}, "
            f"resume_drive_url={'set' if row.resume_drive_url else 'unset'}"
        )
