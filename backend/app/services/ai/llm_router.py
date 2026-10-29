"""LLM 路由：解析本次请求实际使用的模型配置（对齐 AIDriveNote LLMRouter）。

优先级：
    请求 modelConfigId
    → 会话绑定 modelConfigId
    → 助手绑定 modelConfigId
    → 系统默认（is_default）
    → 任一启用（按 sort_order）
    → 无可用 → NoAvailableModelError

每条候选都会校验：未软删、已启用、需要 Key 的 provider 必须已配置密钥（解密后非空）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai.ai_model import AIModelConfig
from app.models.ai.assistant import AIAssistant
from app.services.ai.providers import provider_meta, requires_api_key
from app.services.ai.secret_crypto import decrypt_secret

logger = logging.getLogger(__name__)


class NoAvailableModelError(RuntimeError):
    def __init__(self, message: str = "当前没有可用的 AI 模型，请先在「AI 配置 → 模型」中添加并测试连接") -> None:
        super().__init__(message)
        self.message = message


@dataclass(slots=True)
class ProviderResolution:
    config_id: str
    config_name: str
    provider: str
    model_name: str
    base_url: str
    api_key: str
    temperature: float
    max_tokens: int
    top_p: float
    supports_tools: bool
    resolution: str

    def summary(self) -> dict[str, object]:
        """可安全下发到前端/落库的摘要（不含密钥）。"""
        return {
            "configId": self.config_id,
            "configName": self.config_name,
            "provider": self.provider,
            "modelName": self.model_name,
            "supportsTools": self.supports_tools,
            "resolution": self.resolution,
        }


def effective_api_key(cfg: AIModelConfig) -> str:
    """密文优先后回退历史明文。"""
    return decrypt_secret(cfg.api_key_enc) or decrypt_secret(cfg.api_key)


def _usable(cfg: AIModelConfig | None) -> bool:
    if cfg is None or cfg.is_deleted or not cfg.enabled:
        return False
    if provider_meta(cfg.provider) is None:  # 未知/已下线的 provider 直接跳过
        return False
    if requires_api_key(cfg.provider) and not effective_api_key(cfg):
        return False
    return True


async def _get(db: AsyncSession, config_id: UUID | str | None) -> AIModelConfig | None:
    if config_id is None:
        return None
    try:
        key = config_id if isinstance(config_id, UUID) else UUID(str(config_id))
    except (ValueError, AttributeError):
        return None
    return await db.get(AIModelConfig, key)


async def resolve(
    db: AsyncSession,
    *,
    model_config_id: UUID | str | None = None,
    conversation=None,
    assistant: AIAssistant | None = None,
) -> ProviderResolution:
    candidates: list[tuple[UUID | str | None, str]] = [
        (model_config_id, "request"),
        (getattr(conversation, "model_config_id", None), "conversation"),
        (assistant.model_config_id if assistant is not None else None, "assistant"),
    ]

    cfg: AIModelConfig | None = None
    resolution = ""
    for candidate_id, label in candidates:
        if candidate_id is None:
            continue
        found = await _get(db, candidate_id)
        if _usable(found):
            cfg, resolution = found, label
            break

    if cfg is None:
        result = await db.execute(
            select(AIModelConfig)
            .where(
                AIModelConfig.is_deleted.is_(False),
                AIModelConfig.enabled.is_(True),
                AIModelConfig.is_default.is_(True),
            )
            .order_by(AIModelConfig.sort_order)
        )
        for found in result.scalars():
            if _usable(found):
                cfg, resolution = found, "default"
                break

    if cfg is None:
        result = await db.execute(
            select(AIModelConfig)
            .where(AIModelConfig.is_deleted.is_(False), AIModelConfig.enabled.is_(True))
            .order_by(AIModelConfig.sort_order, AIModelConfig.created_at)
        )
        for found in result.scalars():
            if _usable(found):
                cfg, resolution = found, "fallback"
                break

    if cfg is None:
        raise NoAvailableModelError()

    temperature = cfg.temperature
    max_tokens = cfg.max_tokens
    if assistant is not None:
        if assistant.temperature is not None:
            temperature = float(assistant.temperature)
        if assistant.max_tokens is not None:
            max_tokens = int(assistant.max_tokens)

    return ProviderResolution(
        config_id=str(cfg.id),
        config_name=cfg.name,
        provider=cfg.provider,
        model_name=cfg.model_name or "",
        base_url=cfg.base_url or "",
        api_key=effective_api_key(cfg),
        temperature=float(temperature),
        max_tokens=int(max_tokens),
        top_p=float(cfg.top_p),
        supports_tools=bool(cfg.supports_tools),
        resolution=resolution,
    )
