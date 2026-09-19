import uuid
from sqlalchemy import JSON, Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class AISkill(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """技能：可复用的任务级提示词模板（对齐 AIIgnitePLM ai_skills）。"""

    __tablename__ = "ai_skills"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="business", nullable=False)
    icon: Mapped[str] = mapped_column(String(30), default="sparkles", nullable=False)
    prompt_template: Mapped[str] = mapped_column(Text, default="", nullable=False)
    keywords: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class AIAssistant(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """助手：角色人设 + 系统提示词 + 绑定技能（对齐 AIIgnitePLM ai_assistants）。"""

    __tablename__ = "ai_assistants"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    avatar: Mapped[str] = mapped_column(String(30), default="bot", nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="General", nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    skill_codes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # 推荐技能 code 列表
    model_config_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
