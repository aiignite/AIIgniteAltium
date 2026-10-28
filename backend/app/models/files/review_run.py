from uuid import UUID

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDPkMixin


class ReviewRun(UUIDPkMixin, TimestampMixin, Base):
    """设计审查结果：绑定到具体快照版本，规则确定性可复现。"""

    __tablename__ = "fls_review_runs"

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("fls_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("sys_users.id"), nullable=False)
    snapshot_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False)
    ruleset_version: Mapped[str] = mapped_column(String(20), nullable=False)
    counts: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    findings: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
