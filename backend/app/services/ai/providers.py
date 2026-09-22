"""多 provider 流式聊天引擎：mock / openai 兼容（含 ollama）/ anthropic。

统一接口：`stream_chat(provider, *, base_url, api_key, model, messages, system, tools)`
异步生成器，逐段产出事件 dict：
    {"type": "delta", "text": "..."}                    文本增量
    {"type": "tool_calls", "calls": [...]}              模型请求的工具调用（流结束时一次性给出）
        calls: [{"id": str, "name": str, "arguments": dict}]
代理说明：外网 API 走系统代理（httpx trust_env），本地 ollama 因 no_proxy=localhost 直连。
"""

import json
import logging
from collections.abc import AsyncGenerator

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)


def _anthropic_messages(messages: list[dict]) -> list[dict]:
    """把 OpenAI 风格消息（含 tool_calls / role=tool）转成 Anthropic 格式。"""
    out: list[dict] = []
    for m in messages:
        role = m.get("role")
        if role == "system":
            continue
        if role == "assistant" and m.get("tool_calls"):
            content: list[dict] = []
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


async def stream_openai_compatible(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    tools: list[dict] | None = None,
) -> AsyncGenerator[dict, None]:
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    payload: dict = {"model": model, "messages": messages, "stream": True}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    calls: dict[int, dict] = {}
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            if resp.status_code >= 400:
                body = (await resp.aread()).decode(errors="replace")[:500]
                raise RuntimeError(f"provider HTTP {resp.status_code}: {body}")
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
                delta = (chunk.get("choices") or [{}])[0].get("delta", {})
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
    if calls:
        parsed = []
        for idx in sorted(calls):
            c = calls[idx]
            try:
                args = json.loads(c["arguments"]) if c["arguments"] else {}
            except json.JSONDecodeError:
                args = {}
            parsed.append({"id": c["id"] or f"call_{idx}", "name": c["name"], "arguments": args})
        yield {"type": "tool_calls", "calls": parsed}


async def stream_anthropic(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    system: str,
    tools: list[dict] | None = None,
) -> AsyncGenerator[dict, None]:
    url = f"{base_url.rstrip('/')}/v1/messages"
    payload: dict = {
        "model": model,
        "max_tokens": 4096,
        "messages": _anthropic_messages(messages),
        "stream": True,
    }
    if system:
        payload["system"] = system
    if tools:
        payload["tools"] = tools
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    active_calls: dict[str, dict] = {}
    order: list[str] = []
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            if resp.status_code >= 400:
                body = (await resp.aread()).decode(errors="replace")[:500]
                raise RuntimeError(f"provider HTTP {resp.status_code}: {body}")
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                try:
                    event = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
                etype = event.get("type")
                if etype == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta" and delta.get("text"):
                        yield {"type": "delta", "text": delta["text"]}
                    elif delta.get("type") == "input_json_delta" and delta.get("partial_json"):
                        call = active_calls.get(event.get("index"))
                        if call is not None:
                            call["arguments"] += delta["partial_json"]
                elif etype == "content_block_start":
                    block = event.get("content_block", {})
                    if block.get("type") == "tool_use":
                        call = {"id": block.get("id", ""), "name": block.get("name", ""), "arguments": ""}
                        idx = event.get("index")
                        active_calls[idx] = call
                        order.append(idx)
    if order:
        parsed = []
        for idx in order:
            c = active_calls[idx]
            try:
                args = json.loads(c["arguments"]) if c["arguments"] else {}
            except json.JSONDecodeError:
                args = {}
            parsed.append({"id": c["id"] or f"call_{idx}", "name": c["name"], "arguments": args})
        yield {"type": "tool_calls", "calls": parsed}


async def stream_mock(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    tools: list[dict] | None = None,
) -> AsyncGenerator[dict, None]:
    """无 API Key 时的确定性演示引擎：基于设计上下文生成结构化回复；给出 tools 时演示工具调用循环。"""
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    context_section = ""
    marker = "【设计上下文】"
    if marker in system:
        context_section = system.split(marker, 1)[1].strip()

    write_keywords = {"移动", "move", "高亮", "highlight", "旋转", "rotate"}
    tool_names = {t.get("function", {}).get("name", "") for t in (tools or [])}
    last_role = messages[-1].get("role") if messages else ""
    want_write = last_role == "user" and any(k in user.lower() for k in write_keywords)

    if want_write and tools:
        if "altium_move_component" in tool_names and ("移动" in user or "move" in user.lower()):
            yield {"type": "tool_calls", "calls": [{"id": "mock_call_1", "name": "altium_move_component", "arguments": {"designator": "U1", "x": 1000, "y": 2000}}]}
        elif "altium_highlight_net" in tool_names:
            yield {"type": "tool_calls", "calls": [{"id": "mock_call_2", "name": "altium_highlight_net", "arguments": {"net": "GND", "mode": 1}}]}
        return

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
        yield {"type": "delta", "text": text[i : i + 24]}


async def stream_chat(
    provider: str,
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    system: str = "",
    tools: list[dict] | None = None,
) -> AsyncGenerator[dict, None]:
    if provider == "mock":
        async for event in stream_mock(base_url, api_key, model, messages, tools):
            yield event
    elif provider == "openai":
        async for event in stream_openai_compatible(base_url, api_key, model, messages, tools):
            yield event
    elif provider == "anthropic":
        async for event in stream_anthropic(base_url, api_key, model, messages, system, tools):
            yield event
    else:
        raise RuntimeError(f"未知 provider: {provider}")
