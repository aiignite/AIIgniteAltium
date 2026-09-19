from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class GatewayConnection(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Altium 实时连接配置（第二步启用：DelphiScript 桥 + gateway MCP server）。"""

    __tablename__ = "alt_connections"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), default="http://localhost:3296", nullable=False)
    api_token: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="unreachable", nullable=False)
    # unreachable | connected | disabled（第一步恒为 unreachable/unconfigured）
    remark: Mapped[str] = mapped_column(String(500), default="", nullable=False)
