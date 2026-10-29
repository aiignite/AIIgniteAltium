"""OpenAI 兼容协议（OpenAI / DeepSeek / 硅基流动 / Moonshot / 智谱 / vLLM …）。

关键点：
- ``stream_options.include_usage`` 用于拿 token 用量；部分兼容端点会 400，此时自动去掉重试一次
- tool_calls 在流中分片到达，按 index 累积后于流末一次性下发
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.services.ai.providers.base import BaseProvider, ProviderError

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(BaseProvider):
    id = "openai"
    name = "OpenAI 兼容"
    requires_api_key = True
    default_base_url = "https://api.openai.com/v1"
    default_model = "gpt-4o-mini"
    supports_tools = True
    group = "cloud"

    def _headers(self) -> dict[str, str]:
        if not self.config.api_key:
            return {}
        return {"Authorization": f"Bearer {self.config.api_key}"}

    def _payload(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None, with_usage: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model(),
            "messages": messages,
            "stream": True,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "top_p": self.config.top_p,
        }
        if with_usage:
            payload["stream_options"] = {"include_usage": True}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        return payload

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        url = f"{self.base_url()}/chat/completions"
        with_usage = True
        async with httpx.AsyncClient(timeout=self.config.timeout, follow_redirects=False) as client:
            while True:
                calls: dict[int, dict[str, Any]] = {}
                usage: dict[str, Any] | None = None
                retry_without_usage = False
                async with client.stream(
                    "POST", url, json=self._payload(messages, tools, with_usage), headers=self._headers()
                ) as resp:
                    if not 200 <= resp.status_code < 300:
                        body = (await resp.aread()).decode(errors="replace")[:800]
                        if with_usage and resp.status_code == 400 and "stream_options" in body:
                            retry_without_usage = True
                        else:
                            raise ProviderError("http", resp.status_code)
                    else:
                        async for line in resp.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                            except json.JSONDecodeError:
                                continue
                            if chunk.get("usage"):
                                usage = chunk["usage"]
                            choices = chunk.get("choices") or []
                            delta = (choices[0] if choices else {}).get("delta") or {}
                            text = delta.get("content")
                            if text:
                                yield {"type": "delta", "text": text}
                            for tc in delta.get("tool_calls") or []:
                                idx = tc.get("index", 0)
                                call = calls.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                                if tc.get("id"):
                                    call["id"] = tc["id"]
                                fn = tc.get("function") or {}
                                if fn.get("name"):
                                    call["name"] = fn["name"]
                                if fn.get("arguments"):
                                    call["arguments"] += fn["arguments"]
                if retry_without_usage:
                    with_usage = False
                    continue
                if usage:
                    yield {
                        "type": "usage",
                        "promptTokens": int(usage.get("prompt_tokens") or 0),
                        "completionTokens": int(usage.get("completion_tokens") or 0),
                    }
                if calls:
                    yield {"type": "tool_calls", "calls": _parse_calls(calls)}
                return


def _parse_calls(calls: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for idx in sorted(calls):
        c = calls[idx]
        try:
            args = json.loads(c["arguments"]) if c["arguments"] else {}
        except json.JSONDecodeError:
            args = {}
        parsed.append({"id": c["id"] or f"call_{idx}", "name": c["name"], "arguments": args})
    return parsed
