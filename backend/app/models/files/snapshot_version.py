from uuid import UUID

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDPkMixin


class SnapshotVersion(UUIDPkMixin, TimestampMixin, Base):
    """只追加的工程快照版本；每个版本保存完整解析结果，历史版本不被覆盖。"""

    __tablename__ = "fls_snapshots"
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_fls_snapshots_project_version"),)

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("fls_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    svg_manifest: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    design_json_path: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    parse_duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
