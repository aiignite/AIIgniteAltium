"""Provider 包门面：对上层只暴露 stream_chat()，屏蔽各协议差异。

兼容旧调用签名（orchestrator 原先 `from app.services.ai import providers`）。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from app.services.ai.providers.base import BaseProvider, ProviderConfig
from app.services.ai.providers.factory import (
    PRESETS,
    PROVIDER_CLASSES,
    create_provider,
    default_base_url,
    list_providers,
    provider_meta,
    requires_api_key,
)

logger = logging.getLogger(__name__)

__all__ = [
    "PRESETS",
    "PROVIDER_CLASSES",
    "ProviderConfig",
    "create_provider",
    "default_base_url",
    "list_providers",
    "provider_meta",
    "requires_api_key",
    "stream_chat",
]


async def stream_chat(
    provider: str,
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    system: str = "",
    tools: list[dict[str, Any]] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    top_p: float | None = None,
) -> AsyncIterator[dict[str, Any]]:
    config = ProviderConfig(
        base_url=base_url or "",
        api_key=api_key or "",
        model=model or "",
        temperature=0.4 if temperature is None else float(temperature),
        max_tokens=4096 if max_tokens is None else int(max_tokens),
        top_p=1.0 if top_p is None else float(top_p),
        system=system or "",
    )
    impl: BaseProvider = create_provider(provider, config)
    async for event in impl.stream(messages, tools):
        yield event
