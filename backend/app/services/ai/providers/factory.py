"""Provider 工厂与注册表（对齐 AIDriveNote ai_providers/factory.py）。"""

from __future__ import annotations

from typing import Any

from app.services.ai.providers.anthropic import AnthropicProvider
from app.services.ai.providers.base import BaseProvider, ProviderConfig
from app.services.ai.providers.llamacpp import LlamaCppProvider
from app.services.ai.providers.mock import MockProvider
from app.services.ai.providers.ollama import OllamaProvider
from app.services.ai.providers.openai_compat import OpenAICompatibleProvider

PROVIDER_CLASSES: dict[str, type[BaseProvider]] = {
    cls.id: cls
    for cls in (
        MockProvider,
        OpenAICompatibleProvider,
        OllamaProvider,
        LlamaCppProvider,
        AnthropicProvider,
    )
}

FALLBACK_PROVIDER = "openai"

# 一键填充模板（前端"快速模板"用；provider 决定协议与默认值）
PRESETS: list[dict[str, Any]] = [
    {
        "id": "openai-gpt-4o-mini",
        "name": "OpenAI GPT-4o mini",
        "provider": "openai",
        "baseUrl": "https://api.openai.com/v1",
        "modelName": "gpt-4o-mini",
        "contextWindow": "128K",
        "supportsTools": True,
        "speed": "Fast",
        "cost": "$",
    },
    {
        "id": "deepseek-chat",
        "name": "DeepSeek Chat",
        "provider": "openai",
        "baseUrl": "https://api.deepseek.com/v1",
        "modelName": "deepseek-chat",
        "contextWindow": "64K",
        "supportsTools": True,
        "speed": "Medium",
        "cost": "$",
    },
    {
        "id": "deepseek-reasoner",
        "name": "DeepSeek Reasoner",
        "provider": "openai",
        "baseUrl": "https://api.deepseek.com/v1",
        "modelName": "deepseek-reasoner",
        "contextWindow": "64K",
        "supportsTools": False,
        "speed": "Slow",
        "cost": "$$",
    },
    {
        "id": "siliconflow-qwen",
        "name": "硅基流动 Qwen2.5-72B",
        "provider": "openai",
        "baseUrl": "https://api.siliconflow.cn/v1",
        "modelName": "Qwen/Qwen2.5-72B-Instruct",
        "contextWindow": "32K",
        "supportsTools": True,
        "speed": "Fast",
        "cost": "$",
    },
    {
        "id": "moonshot-v1",
        "name": "Moonshot v1-8k",
        "provider": "openai",
        "baseUrl": "https://api.moonshot.cn/v1",
        "modelName": "moonshot-v1-8k",
        "contextWindow": "8K",
        "supportsTools": True,
        "speed": "Medium",
        "cost": "$",
    },
    {
        "id": "zhipu-glm-4",
        "name": "智谱 GLM-4-Plus",
        "provider": "openai",
        "baseUrl": "https://open.bigmodel.cn/api/paas/v4",
        "modelName": "glm-4-plus",
        "contextWindow": "128K",
        "supportsTools": True,
        "speed": "Medium",
        "cost": "$$",
    },
    {
        "id": "ollama-qwen",
        "name": "Ollama Qwen2.5（本地）",
        "provider": "ollama",
        "baseUrl": "http://localhost:11434",
        "modelName": "qwen2.5:7b",
        "contextWindow": "32K",
        "supportsTools": True,
        "speed": "Medium",
        "cost": "local",
    },
    {
        "id": "llamacpp-local",
        "name": "llama.cpp（本地）",
        "provider": "llamacpp",
        "baseUrl": "http://localhost:8080/v1",
        "modelName": "local-model",
        "contextWindow": "",
        "supportsTools": False,
        "speed": "Slow",
        "cost": "local",
    },
]


def create_provider(provider: str, config: ProviderConfig) -> BaseProvider:
    cls = PROVIDER_CLASSES.get((provider or FALLBACK_PROVIDER).lower())
    if cls is None:
        raise ValueError(f"未知 provider: {provider}")
    return cls(config)


def provider_meta(provider: str) -> dict[str, Any] | None:
    cls = PROVIDER_CLASSES.get((provider or "").lower())
    return cls.meta() if cls else None


def list_providers() -> list[dict[str, Any]]:
    order = ["mock", "openai", "ollama", "llamacpp", "anthropic"]
    metas = [PROVIDER_CLASSES[p].meta() for p in order if p in PROVIDER_CLASSES]
    return metas


def requires_api_key(provider: str) -> bool:
    meta = provider_meta(provider)
    return bool(meta and meta["requiresApiKey"])


def default_base_url(provider: str) -> str:
    meta = provider_meta(provider)
    return str(meta["defaultBaseUrl"]) if meta else ""
