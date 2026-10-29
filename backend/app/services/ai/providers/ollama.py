"""Ollama：使用原生 ``/api/chat``（NDJSON 流），对齐 AIDriveNote 的 OllamaProvider。

相比 OpenAI 兼容端点，原生接口支持 ``options.temperature/top_p/num_predict``、
``images`` 字段与稳定的 ``prompt_eval_count/eval_count`` 用量统计。
base_url 兼容两种写法：``http://host:11434`` 或 ``http://host:11434/v1``（自动去掉后缀）。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.services.ai.providers.base import BaseProvider, ProviderError


class OllamaProvider(BaseProvider):
    id = "ollama"
    name = "Ollama（本地）"
    requires_api_key = False
    default_base_url = "http://localhost:11434"
    default_model = "qwen2.5:7b"
    supports_tools = True
    group = "local"

    def root_url(self) -> str:
        base = self.base_url()
        if base.endswith("/v1"):
            base = base[: -len("/v1")]
        return base

    @staticmethod
    def _serialize_message(m: dict[str, Any]) -> dict[str, Any]:
        content = m.get("content")
        item: dict[str, Any] = {"role": m.get("role") or "user", "content": ""}
        if isinstance(content, list):
            texts: list[str] = []
            images: list[str] = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text" and part.get("text"):
                    texts.append(str(part["text"]))
                elif part.get("type") == "image" and part.get("data"):
                    data = str(part["data"])
                    images.append(data.split(",", 1)[-1] if data.startswith("data:") else data)
            item["content"] = "\n".join(texts)
            if images:
                item["images"] = images
        else:
            item["content"] = content or ""
        if m.get("role") == "tool" and m.get("tool_call_id"):
            item["tool_call_id"] = m["tool_call_id"]
        if m.get("tool_calls"):
            item["tool_calls"] = m["tool_calls"]
        return item

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        payload: dict[str, Any] = {
            "model": self.model(),
            "messages": [self._serialize_message(m) for m in messages],
            "stream": True,
            "options": {
                "temperature": self.config.temperature,
                "top_p": self.config.top_p,
                "num_predict": self.config.max_tokens,
            },
        }
        if tools:
            payload["tools"] = [
                {"type": "function", "function": t.get("function", t)} for t in tools
            ]

        calls: list[dict[str, Any]] = []
        usage: dict[str, Any] | None = None
        async with httpx.AsyncClient(timeout=self.config.timeout, follow_redirects=False) as client:
            async with client.stream("POST", f"{self.root_url()}/api/chat", json=payload) as resp:
                if not 200 <= resp.status_code < 300:
                    await resp.aread()
                    raise ProviderError("http", resp.status_code)
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    message = data.get("message") or {}
                    for tc in message.get("tool_calls") or []:
                        fn = tc.get("function") or {}
                        args = fn.get("arguments", {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {"raw": args}
                        calls.append(
                            {
                                "id": tc.get("id") or f"call_{len(calls) + 1}",
                                "name": fn.get("name", ""),
                                "arguments": args,
                            }
                        )
                    text = message.get("content")
                    if text:
                        yield {"type": "delta", "text": text}
                    if data.get("done"):
                        prompt_tokens = int(data.get("prompt_eval_count") or 0)
                        completion_tokens = int(data.get("eval_count") or 0)
                        if prompt_tokens or completion_tokens:
                            usage = {
                                "promptTokens": prompt_tokens,
                                "completionTokens": completion_tokens,
                            }
        if usage:
            yield {"type": "usage", **usage}
        if calls:
            yield {"type": "tool_calls", "calls": calls}
