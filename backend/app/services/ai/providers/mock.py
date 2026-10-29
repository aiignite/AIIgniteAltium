"""内置演示引擎（mock）：无 API Key 时的确定性回复，保证前端联调与截图可用。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.services.ai.providers.base import BaseProvider


class MockProvider(BaseProvider):
    id = "mock"
    name = "演示引擎（内置）"
    requires_api_key = False
    default_base_url = ""
    default_model = "mock-1"
    supports_tools = True
    group = "builtin"

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        context_section = ""
        marker = "【设计上下文】"
        if marker in system:
            context_section = system.split(marker, 1)[1].strip()

        write_keywords = ("移动", "move", "高亮", "highlight", "旋转", "rotate")
        tool_names = {t.get("function", {}).get("name", "") for t in (tools or [])}
        last_role = messages[-1].get("role") if messages else ""
        want_write = last_role == "user" and any(k in user.lower() for k in write_keywords)

        if want_write and tools:
            if "altium_move_component" in tool_names and ("移动" in user or "move" in user.lower()):
                yield {
                    "type": "tool_calls",
                    "calls": [
                        {
                            "id": "mock_call_1",
                            "name": "altium_move_component",
                            "arguments": {"designator": "U1", "x": 1000, "y": 2000},
                        }
                    ],
                }
            elif "altium_highlight_net" in tool_names:
                yield {
                    "type": "tool_calls",
                    "calls": [
                        {"id": "mock_call_2", "name": "altium_highlight_net", "arguments": {"net": "GND", "mode": 1}}
                    ],
                }
            return

        parts: list[str] = [f"收到，你的问题是：{user.strip()[:200] or '（空）'}\n"]
        if context_section:
            parts.append(
                "\n我已读取当前设计上下文，要点如下：\n\n" + context_section[:1500] + "\n"
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
        yield {
            "type": "usage",
            "promptTokens": max(1, len(system) + len(user)) // 4,
            "completionTokens": max(1, len(text)) // 4,
        }
