"""FleetJob model — tracks a single Gemini-CLI-driven repo task.

Sutra (in Docker) holds the queue and triages. The host-side worker
(outside Docker so it can use Gemini OAuth) claims jobs, runs the CLI
inside macOS Seatbelt sandbox, and reports back via /api/fleet/*.
"""

from enum import Enum

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, generate_uuid


class FleetStatus(str, Enum):
    queued = "queued"                  # waiting for a worker to claim
    claimed = "claimed"                # a host worker has it, hasn't started yet
    running = "running"                # gemini cli is executing
    pushing = "pushing"                # worker is committing + pushing
    pr_created = "pr_created"          # PR is open; terminal success
    failed = "failed"
    cancelled = "cancelled"


class FleetJob(Base, TimestampMixin):
    """A single fleet task — one repo, one issue (or freeform prompt), one PR."""

    __tablename__ = "fleet_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Target — "owner/repo"
    repo_url: Mapped[str] = mapped_column(String(300), nullable=False)

    # Optional GitHub issue this job addresses (kept as string so a non-issue
    # freeform task can use a synthetic label like "chore:cleanup").
    issue_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # The instruction we feed to Gemini CLI (-p flag)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)

    # Short human-readable title for the queue UI
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    # Branch the worker creates locally and pushes to origin
    branch_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Lifecycle
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=FleetStatus.queued.value
    )

    # Triage metadata — why this was picked, priority score, etc.
    triage: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Decisions / important info the worker accumulated — posted as a PR
    # comment after the PR is opened.
    decisions: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)

    # Streaming output from Gemini CLI — [{timestamp, stream, line}]
    run_log: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)

    # Host worker identity (so we can detect dead workers and re-queue)
    claimed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    claimed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)  # ISO-8601

    # PR info, set after pr_created
    pr_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Error details if status == failed
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Creator (None when enqueued by the triage scheduler)
    creator_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<FleetJob(id={self.id}, repo={self.repo_url}, status={self.status})>"
