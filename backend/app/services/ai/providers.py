"""多 provider 流式聊天引擎：mock / openai 兼容（含 ollama）/ anthropic。

统一接口：`stream_chat(provider, *, base_url, api_key, model, messages, system)` 
异步生成器，逐段产出文本增量。代理说明：外网 API 走系统代理（httpx trust_env），
本地 ollama 因 no_proxy=localhost 直连。
"""

import json
import logging
from collections.abc import AsyncGenerator

import httpx
from uuid import uuid4

from app.services.system.credentials import decrypt_credential
from app.services.system.outbound import validate_outbound_url

logger = logging.getLogger(__name__)


class ProviderError(RuntimeError):
    def __init__(self, category: str, status: int | None = None):
        self.category, self.status, self.request_id = category, status, uuid4().hex
        super().__init__(f"provider_{category}; status={status or 'none'}; requestId={self.request_id}")

DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)


async def stream_openai_compatible(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
) -> AsyncGenerator[str, None]:
    base_url = await validate_outbound_url(base_url)
    api_key = decrypt_credential(api_key)
    url = f"{base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    payload = {"model": model, "messages": messages, "stream": True}
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=False) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            if resp.status_code >= 300:
                raise ProviderError("redirect" if resp.status_code < 400 else "http", resp.status_code)
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = (chunk.get("choices") or [{}])[0].get("delta", {}).get("content")
                if delta:
                    yield delta


async def stream_anthropic(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    system: str,
) -> AsyncGenerator[str, None]:
    base_url = await validate_outbound_url(base_url)
    api_key = decrypt_credential(api_key)
    url = f"{base_url}/v1/messages"
    payload = {
        "model": model,
        "max_tokens": 4096,
        "messages": [m for m in messages if m["role"] != "system"],
        "stream": True,
    }
    if system:
        payload["system"] = system
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=False) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            if resp.status_code >= 300:
                raise ProviderError("redirect" if resp.status_code < 400 else "http", resp.status_code)
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                try:
                    event = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "content_block_delta":
                    text = event.get("delta", {}).get("text")
                    if text:
                        yield text


async def stream_mock(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
) -> AsyncGenerator[str, None]:
    """无 API Key 时的确定性演示引擎：基于设计上下文生成结构化回复。"""
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    context_section = ""
    marker = "【设计上下文】"
    if marker in system:
        context_section = system.split(marker, 1)[1].strip()

    parts: list[str] = [
        f"收到，你的问题是：{user.strip()[:200] or '（空）'}\n",
    ]
    if context_section:
        parts.append(
            "\n我已读取当前设计上下文，要点如下：\n\n"
            + context_section[:1500]
            + "\n"
        )
        parts.append(
            "\n基于以上信息，我可以继续帮你：\n"
            "1. 对元件清单做初步审查（缺封装、缺值、位号重复等）；\n"
            "2. 检查网络表中的悬空引脚与可疑连接；\n"
            "3. 对 BOM 做合并与替代料建议（第二步接入元件数据库后可用）；\n"
            "4. 解答原理图/PCB 中你指名的具体对象。\n"
            "（当前为 mock 引擎，配置真实模型后可进行专业级分析。）\n"
        )
    else:
        parts.append(
            "\n当前未关联设计文件。你可以先在「工程文件」页上传 Altium 工程"
            "（.PrjPcb/.SchDoc/.PcbDoc），解析完成后再回到对话，我就能基于真实设计数据回答。\n"
        )
    text = "".join(parts)
    for i in range(0, len(text), 24):
        yield text[i : i + 24]


async def stream_chat(
    provider: str,
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    system: str = "",
) -> AsyncGenerator[str, None]:
    system = system or "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    messages = [m for m in messages if m["role"] != "system"]
    if system:
        messages = [{"role": "system", "content": system}, *messages]
    try:
        if provider == "mock":
            stream = stream_mock(base_url, "", model, messages)
        elif provider == "openai":
            stream = stream_openai_compatible(base_url, api_key, model, messages)
        elif provider == "anthropic":
            stream = stream_anthropic(base_url, api_key, model, messages, system)
        else:
            raise ProviderError("unsupported")
        async for chunk in stream:
            yield chunk
    except httpx.HTTPError:
        raise ProviderError("transport") from None
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ProviderError("invalid_response") from None
