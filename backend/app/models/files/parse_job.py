from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDPkMixin

ACTIVE_JOB_STATUSES = ("queued", "running")


class ParseJob(UUIDPkMixin, TimestampMixin, Base):
    """持久化解析任务队列；同一工程最多一个排队/执行中的任务。"""

    __tablename__ = "fls_parse_jobs"
    __table_args__ = (
        Index(
            "uq_parse_jobs_active_project",
            "project_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
            sqlite_where=text("status IN ('queued', 'running')"),
        ),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("fls_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # queued | running | succeeded | failed
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False, index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
