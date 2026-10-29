"""Provider 包门面：对上层只暴露 stream_chat()，屏蔽各协议差异。

安全边界（P0）：
- 出站前校验目标地址（云端走白名单；本地推理按 ai_allow_private_model_hosts 放行私网）
- 密钥支持 ``enc:v1:`` 密文，出站前解密，绝不把密文当 Key 发送
- 故障统一转 ``ProviderError``（仅分类/状态码/requestId，响应体与密钥不入日志与异常）
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.services.ai.providers.base import BaseProvider, ProviderConfig, ProviderError
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
    "ProviderError",
    "create_provider",
    "default_base_url",
    "list_providers",
    "provider_meta",
    "requires_api_key",
    "stream_chat",
    "validate_provider_base_url",
]


def _plain_key(value: str) -> str:
    if not value:
        return ""
    if value.startswith("enc:v1:"):
        from app.services.system.credentials import decrypt_credential

        return decrypt_credential(value)
    return value


def _provider_class(provider: str) -> type[BaseProvider]:
    cls = PROVIDER_CLASSES.get(provider)
    if cls is None:
        raise ProviderError("config")
    return cls


async def validate_provider_base_url(provider: str, base_url: str) -> str:
    """按 provider 类型校验出站地址；mock 无出站，直接返回空。"""
    from app.config import settings
    from app.services.system.outbound import validate_outbound_url

    if provider == "mock":
        return ""
    cls = _provider_class(provider)
    target = (base_url or cls.default_base_url or "").rstrip("/")
    return await validate_outbound_url(
        target, allow_private=settings.ai_allow_private_model_hosts and cls.group == "local"
    )


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
    cls = _provider_class(provider)
    resolved_url = (base_url or cls.default_base_url or "").rstrip("/")
    if provider != "mock":
        await validate_provider_base_url(provider, resolved_url)

    config = ProviderConfig(
        base_url=resolved_url,
        api_key=_plain_key(api_key),
        model=model or "",
        temperature=0.4 if temperature is None else float(temperature),
        max_tokens=4096 if max_tokens is None else int(max_tokens),
        top_p=1.0 if top_p is None else float(top_p),
        system=system or "",
    )
    impl: BaseProvider = create_provider(provider, config)
    normalized = messages
    if system:
        normalized = [{"role": "system", "content": system}] + [
            m for m in messages if m.get("role") != "system"
        ]
    try:
        async for event in impl.stream(normalized, tools):
            yield event
    except ProviderError:
        raise
    except httpx.HTTPError:
        raise ProviderError("transport") from None
