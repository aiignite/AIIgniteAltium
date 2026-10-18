import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class AIModelConfig(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """大模型配置（对齐 AIDriveNote ai_models 的字段语义）。

    provider: mock | openai | ollama | llamacpp | anthropic
    - ollama / llamacpp 复用 OpenAI 兼容协议（/v1/chat/completions），免 Key
    - anthropic 为 legacy 兼容分支
    """

    __tablename__ = "ai_model_configs"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    base_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)

    # 历史明文列：新写入一律走 api_key_enc，随后把本列置空（保留作回滚安全网）
    api_key: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # enc:v1:<fernet token>
    api_key_enc: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # 掩码尾号，列表展示用，避免解密
    key_hint: Mapped[str] = mapped_column(String(20), default="", nullable=False)

    model_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)

    temperature: Mapped[float] = mapped_column(Float, default=0.4, nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096, nullable=False)
    top_p: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    context_window: Mapped[str] = mapped_column(String(20), default="", nullable=False)

    supports_tools: Mapped[bool] = mapped_column(default=True, nullable=False)
    supports_image: Mapped[bool] = mapped_column(default=False, nullable=False)

    speed: Mapped[str] = mapped_column(String(20), default="Fast", nullable=False)
    cost: Mapped[str] = mapped_column(String(20), default="$", nullable=False)

    is_system: Mapped[bool] = mapped_column(default=False, nullable=False)

    test_status: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    test_latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)

    is_default: Mapped[bool] = mapped_column(default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    remark: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ---- 便捷方法 ----
    @property
    def has_key(self) -> bool:
        return bool(self.api_key_enc or self.api_key)

    def bind_key(self, plain: str) -> None:
        """写入密钥：加密存 api_key_enc，记录掩码，清空明文列。"""
        from app.services.ai.secret_crypto import encrypt_secret, mask_secret

        self.api_key_enc = encrypt_secret(plain)
        self.key_hint = mask_secret(plain)
        self.api_key = ""

    def clear_key(self) -> None:
        self.api_key_enc = ""
        self.key_hint = ""
        self.api_key = ""
