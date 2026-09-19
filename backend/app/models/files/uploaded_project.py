from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class UploadedProject(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """上传的 Altium 工程（离线解析，第二步接入实时连接前的主数据通道）。"""

    __tablename__ = "fls_projects"

    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    storage_dir: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="uploaded", nullable=False, index=True)
    # uploaded | parsing | ready | failed
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    file_names: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # 归一化设计快照（aidrive.snapshot.v0），仅摘要与结构化数据
    snapshot: Mapped[dict] = mapped_column(JSON, default=None, nullable=True)
    svg_manifest: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    design_json_path: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    parse_duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    remark: Mapped[str] = mapped_column(String(500), default="", nullable=False)
