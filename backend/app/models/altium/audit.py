import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDPkMixin


class AltiumCommandAudit(UUIDPkMixin, TimestampMixin, Base):
    """Altium 写命令审计：记录 before/after、请求幂等键与撤销关系。"""

    __tablename__ = "alt_command_audits"
    __table_args__ = (
        UniqueConstraint("connection_id", "request_id", name="uq_alt_command_audits_request"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sys_users.id"), nullable=False, index=True)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alt_connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    command: Mapped[str] = mapped_column(String(100), nullable=False)
    params: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # move/rotate 为执行前位姿；highlight 为请求的显示模式（撤销时取反）
    before: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # executed | failed | undone
    status: Mapped[str] = mapped_column(String(20), default="executed", nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    undo_of_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("alt_command_audits.id"), nullable=True)
    undone_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sys_users.id"), nullable=True)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
