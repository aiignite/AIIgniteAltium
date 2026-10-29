"""Anthropic Messages API（legacy 兼容分支，保留既有能力）。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.services.ai.providers.base import BaseProvider, ProviderError


def _anthropic_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把 OpenAI 风格消息（含 tool_calls / role=tool）转成 Anthropic 格式。"""
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        if role == "system":
            continue
        if role == "assistant" and m.get("tool_calls"):
            content: list[dict[str, Any]] = []
            if m.get("content"):
                content.append({"type": "text", "text": m["content"]})
            for tc in m["tool_calls"]:
                try:
                    args = json.loads(tc["function"]["arguments"])
                except (KeyError, json.JSONDecodeError):
                    args = {}
                content.append(
                    {"type": "tool_use", "id": tc["id"], "name": tc["function"]["name"], "input": args}
                )
            out.append({"role": "assistant", "content": content})
        elif role == "tool":
            block = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}
            if out and out[-1]["role"] == "user" and isinstance(out[-1].get("content"), list):
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
        else:
            out.append({"role": role, "content": m.get("content")})
    return out


class AnthropicProvider(BaseProvider):
    id = "anthropic"
    name = "Anthropic（兼容保留）"
    requires_api_key = True
    default_base_url = "https://api.anthropic.com"
    default_model = "claude-3-5-sonnet-latest"
    supports_tools = True
    group = "legacy"

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        payload: dict[str, Any] = {
            "model": self.model(),
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "messages": _anthropic_messages(messages),
            "stream": True,
        }
        if self.config.system:
            payload["system"] = self.config.system
        if tools:
            payload["tools"] = tools
        headers = {"x-api-key": self.config.api_key, "anthropic-version": "2023-06-01"}
        active_calls: dict[Any, dict[str, Any]] = {}
        order: list[Any] = []
        usage: dict[str, Any] | None = None

        async with httpx.AsyncClient(timeout=self.config.timeout, follow_redirects=False) as client:
            async with client.stream(
                "POST", f"{self.base_url()}/v1/messages", json=payload, headers=headers
            ) as resp:
                if not 200 <= resp.status_code < 300:
                    await resp.aread()
                    raise ProviderError("http", resp.status_code)
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        event = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    etype = event.get("type")
                    if etype == "message_start":
                        u = (event.get("message") or {}).get("usage") or {}
                        if u:
                            usage = {
                                "prompt_tokens": u.get("input_tokens", 0),
                                "completion_tokens": u.get("output_tokens", 0),
                            }
                    elif etype == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("text"):
                            yield {"type": "delta", "text": delta["text"]}
                        elif delta.get("type") == "input_json_delta" and delta.get("partial_json"):
                            call = active_calls.get(event.get("index"))
                            if call is not None:
                                call["arguments"] += delta["partial_json"]
                    elif etype == "content_block_start":
                        block = event.get("content_block") or {}
                        if block.get("type") == "tool_use":
                            idx = event.get("index")
                            active_calls[idx] = {
                                "id": block.get("id", ""),
                                "name": block.get("name", ""),
                                "arguments": "",
                            }
                            order.append(idx)
                    elif etype == "message_delta":
                        u = event.get("usage") or {}
                        if u and usage is not None:
                            usage["completion_tokens"] = u.get("output_tokens", usage["completion_tokens"])
        if usage:
            yield {
                "type": "usage",
                "promptTokens": int(usage.get("prompt_tokens") or 0),
                "completionTokens": int(usage.get("completion_tokens") or 0),
            }
        if order:
            calls: list[dict[str, Any]] = []
            for idx in order:
                c = active_calls[idx]
                try:
                    args = json.loads(c["arguments"]) if c["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                calls.append({"id": c["id"] or f"call_{idx}", "name": c["name"], "arguments": args})
            yield {"type": "tool_calls", "calls": calls}
