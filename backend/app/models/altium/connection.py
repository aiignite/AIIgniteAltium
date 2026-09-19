import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class GatewayConnection(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Altium 实时连接：指向局域网 Windows 机上的 altium-gateway(:3296)。"""

    __tablename__ = "alt_connections"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), default="http://192.168.1.14:3296", nullable=False)
    api_token: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="unreachable", nullable=False)
    # unreachable | connected | disabled
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    info: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    remark: Mapped[str] = mapped_column(String(500), default="", nullable=False)
