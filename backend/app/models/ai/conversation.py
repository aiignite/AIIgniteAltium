import uuid  # noqa: F401
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class Conversation(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "ai_conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sys_users.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="新对话", nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fls_projects.id"), nullable=True)
    model_config_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_model_configs.id"), nullable=True)
    assistant_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    skill: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Message(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "ai_messages"
    __table_args__ = (Index("ix_ai_messages_conversation", "conversation_id", "seq"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_conversations.id"), index=True, nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user | assistant | system
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    skill: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    model_config_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_model_configs.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(30), default="", nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
