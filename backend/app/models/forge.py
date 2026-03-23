"""ForgeRequest model — tracks autonomous feature implementation requests."""

from enum import Enum

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, generate_uuid


class ForgeStatus(str, Enum):
    queued = "queued"                          # waiting for the nightly scheduler
    planning = "planning"
    awaiting_plan_approval = "awaiting_plan_approval"
    coding = "coding"
    testing = "testing"
    pr_created = "pr_created"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class ForgeRequest(Base, TimestampMixin):
    """Tracks an autonomous feature implementation driven by any LLM provider."""

    __tablename__ = "forge_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # What to build
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Target repo — "owner/repo" format
    repo_url: Mapped[str] = mapped_column(String(300), nullable=False)

    # Branch created for this request: "forge/{slug}-{short_id}"
    branch_name: Mapped[str] = mapped_column(String(200), nullable=True)

    # Execution config — any LLM provider + model
    llm_provider: Mapped[str] = mapped_column(String(50), nullable=False, default="groq")
    llm_model: Mapped[str] = mapped_column(String(100), nullable=False, default="qwen/qwen3-32b")

    # Auto-approve plan (skip awaiting_plan_approval step)
    auto_approve_plan: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Lifecycle state
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ForgeStatus.planning.value
    )

    # Implementation plan — {summary: str, steps: [{file, action, description}]}
    plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Feedback rounds — [{round: int, feedback: str}]
    plan_feedback: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)

    # GitHub PR info (set after PR creation)
    pr_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pr_number: Mapped[int | None] = mapped_column(nullable=True)

    # Coding progress log — [{timestamp, event, detail}]
    coding_log: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)

    # Test results — {framework, exit_code, stdout, stderr, passed, failed, skipped}
    test_results: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Error details if status == failed
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Local workspace path for the cloned repo
    workspace_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Origin channel
    source_channel: Mapped[str] = mapped_column(String(20), nullable=False, default="ui")
    telegram_chat_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Creator
    creator_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<ForgeRequest(id={self.id}, title={self.title!r}, status={self.status})>"
