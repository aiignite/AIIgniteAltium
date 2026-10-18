"""Provider 抽象：统一配置对象与流式事件协议。

事件协议（与 orchestrator 约定）：
    {"type": "delta", "text": "..."}                       文本增量
    {"type": "usage", "promptTokens": int, "completionTokens": int}   用量（provider 支持时）
    {"type": "tool_calls", "calls": [{"id","name","arguments"}]}      工具调用（流末一次性）
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)


@dataclass(slots=True)
class ProviderConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.4
    max_tokens: int = 4096
    top_p: float = 1.0
    system: str = ""
    timeout: httpx.Timeout = field(default_factory=lambda: DEFAULT_TIMEOUT)


class BaseProvider:
    """Provider 基类：子类只需实现 stream()。"""

    id: str = ""
    name: str = ""
    requires_api_key: bool = True
    default_base_url: str = ""
    default_model: str = ""
    supports_tools: bool = True
    group: str = "cloud"

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    # ---- 供子类复用的工具方法 ----
    def base_url(self) -> str:
        return (self.config.base_url or self.default_base_url or "").rstrip("/")

    def model(self) -> str:
        return self.config.model or self.default_model

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        raise NotImplementedError

    # ---- 元数据（前端 /ai/models/providers 用） ----
    @classmethod
    def meta(cls) -> dict[str, Any]:
        return {
            "id": cls.id,
            "name": cls.name,
            "requiresApiKey": cls.requires_api_key,
            "defaultBaseUrl": cls.default_base_url,
            "defaultModel": cls.default_model,
            "supportsTools": cls.supports_tools,
            "group": cls.group,
        }
