import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class GatewayConnection(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "alt_connections"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    api_token: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="unreachable", nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    info: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    remark: Mapped[str] = mapped_column(String(500), default="", nullable=False)


class ConnectionGrant(Base):
    __tablename__ = "alt_connection_grants"

    connection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("alt_connections.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sys_users.id", ondelete="CASCADE"), primary_key=True, index=True)
