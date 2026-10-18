"""模型连接测试（对齐 AIDriveNote /ai/models/test）。

设计要点：
- 真正发一次最小请求（max_tokens=1、非流式），同时验证 Base URL / 密钥 / 模型名
- OpenAI 兼容端点若 404，再回退 ``GET /models``（部分网关只实现列表接口）
- 失败按类归因（auth / network / timeout / model / rate / blocked / unknown），前端据此给建议
- 目标地址做基础 SSRF 校验：本地/私网地址仅允许 ollama / llama.cpp
"""

from __future__ import annotations

import ipaddress
import logging
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.services.ai.providers import default_base_url, provider_meta

logger = logging.getLogger(__name__)

LOCAL_PROVIDERS = {"ollama", "llamacpp"}
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "host.docker.internal"}

_ERROR_HINTS = {
    "auth": "密钥无效或权限不足，请检查 API Key",
    "network": "无法连接目标地址，请检查 Base URL 与网络/代理",
    "timeout": "请求超时，请检查网络或调大超时时间",
    "model": "模型名不可用，请确认该模型已开通（或名称拼写正确）",
    "rate": "触发限流，请稍后重试",
    "blocked": "目标地址不被允许",
    "config": "配置不完整",
    "unknown": "未知错误",
}


def _is_private_host(host: str) -> bool:
    if not host:
        return False
    lowered = host.lower()
    if lowered in _LOCAL_HOSTS or lowered.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(lowered.strip("[]"))
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def validate_target(provider: str, base_url: str) -> str | None:
    """返回错误文案；None 表示通过。"""
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https"):
        return "Base URL 必须以 http:// 或 https:// 开头"
    if not parsed.netloc:
        return "Base URL 缺少主机名"
    if not settings.ai_allow_private_model_hosts:
        return "当前配置禁止访问本地/私网地址"
    host = parsed.hostname or ""
    if _is_private_host(host) and provider not in LOCAL_PROVIDERS:
        return "本地/私网地址仅允许用于 ollama / llama.cpp；云端模型请填写公网 Base URL"
    return None


def _fail(category: str, detail: str, started: float, *, status_code: int | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "latencyMs": int((time.perf_counter() - started) * 1000),
        "category": category,
        "statusCode": status_code,
        "error": detail or _ERROR_HINTS.get(category, "未知错误"),
        "hint": _ERROR_HINTS.get(category, ""),
    }


def _extract_detail(body: str) -> str:
    text = body.strip()
    if not text:
        return ""
    return text[:300]


def _categorize(status_code: int, body: str) -> str:
    if status_code in (401, 403):
        return "auth"
    if status_code == 429:
        return "rate"
    if status_code == 404:
        return "model" if "model" in body.lower() else "unknown"
    if status_code == 400:
        lowered = body.lower()
        if "api key" in lowered or "unauthorized" in lowered:
            return "auth"
        return "model"
    return "unknown"


async def probe(
    *,
    provider: str,
    base_url: str = "",
    api_key: str = "",
    model: str = "",
    timeout: float | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    meta = provider_meta(provider)
    if meta is None:
        return _fail("config", f"未知 provider: {provider}", started)

    if provider == "mock":
        return {
            "ok": True,
            "latencyMs": int((time.perf_counter() - started) * 1000),
            "category": "ok",
            "statusCode": None,
            "error": "",
            "hint": "",
            "provider": provider,
            "model": model or meta["defaultModel"],
        }

    base = (base_url or str(meta["defaultBaseUrl"]) or "").rstrip("/")
    if not base:
        return _fail("config", "缺少 Base URL", started)
    target_error = validate_target(provider, base)
    if target_error:
        return _fail("blocked", target_error, started)
    if meta["requiresApiKey"] and not api_key:
        return _fail("auth", "未配置 API Key", started)

    use_model = model or str(meta["defaultModel"])
    limit = timeout if timeout is not None else settings.ai_model_test_timeout
    http_timeout = httpx.Timeout(connect=min(5.0, limit), read=limit, write=limit, pool=limit)

    try:
        async with httpx.AsyncClient(timeout=http_timeout) as client:
            if provider == "ollama":
                # 原生 /api/tags：最轻量的连通性探测（无需模型已拉取）
                root = base[: -len("/v1")] if base.endswith("/v1") else base
                resp = await client.get(f"{root}/api/tags")
            elif provider == "llamacpp":
                resp = await client.get(f"{base}/models")
            elif provider == "anthropic":
                resp = await client.post(
                    f"{base}/v1/messages",
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                    json={
                        "model": use_model,
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
            else:
                resp = await client.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
                    json={
                        "model": use_model,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1,
                        "stream": False,
                    },
                )
                if resp.status_code == 404:
                    # 回退：部分网关不实现补全但提供模型列表
                    listing = await client.get(
                        f"{base}/models",
                        headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
                    )
                    if listing.status_code < 400:
                        resp = listing
    except httpx.ConnectTimeout:
        return _fail("timeout", _ERROR_HINTS["timeout"], started)
    except httpx.ReadTimeout:
        return _fail("timeout", _ERROR_HINTS["timeout"], started)
    except httpx.HTTPError as exc:
        return _fail("network", f"{_ERROR_HINTS['network']}（{exc.__class__.__name__}: {exc}）", started)

    latency = int((time.perf_counter() - started) * 1000)
    if resp.status_code < 400:
        return {
            "ok": True,
            "latencyMs": latency,
            "category": "ok",
            "statusCode": resp.status_code,
            "error": "",
            "hint": "",
            "provider": provider,
            "model": use_model,
        }

    body = _extract_detail(resp.text)
    category = _categorize(resp.status_code, body)
    return {
        "ok": False,
        "latencyMs": latency,
        "category": category,
        "statusCode": resp.status_code,
        "error": body or _ERROR_HINTS.get(category, "未知错误"),
        "hint": _ERROR_HINTS.get(category, ""),
        "provider": provider,
        "model": use_model,
    }
