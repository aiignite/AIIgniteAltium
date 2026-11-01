"""对话导出：把一段对话渲染为 Markdown（含技能、模型与工具调用记录）。"""

from __future__ import annotations

import json
from typing import Any

MAX_TOOL_RESULT = 1500


def _json_block(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2)
    if len(text) > MAX_TOOL_RESULT:
        text = text[:MAX_TOOL_RESULT] + "\n…（已截断）"
    return text


def _tool_lines(entries: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for entry in entries:
        name = entry.get("name") or "unknown"
        params = entry.get("params") or {}
        lines.append(f"- 工具 `{name}` 参数 `{json.dumps(params, ensure_ascii=False)}`")
        if entry.get("preview"):
            lines.append(f"  - 预览：{entry['preview']}")
        if "result" in entry:
            lines.append("  - 结果：")
            lines.append("")
            lines.append("    ```json")
            for row in _json_block(entry["result"]).splitlines():
                lines.append("    " + row)
            lines.append("    ```")
    return lines


def render_conversation(conversation, messages: list[Any]) -> str:
    lines: list[str] = [
        f"# {conversation.title}",
        "",
        f"- 对话 ID：`{conversation.id}`",
        f"- 消息数：{len(messages)}",
        f"- 创建时间：{conversation.created_at.isoformat()}",
        f"- 更新时间：{conversation.updated_at.isoformat()}",
    ]
    if conversation.project_id:
        lines.append(f"- 关联工程：`{conversation.project_id}`")
    if conversation.connection_id:
        lines.append(f"- 实时连接：`{conversation.connection_id}`")
    lines.append("")
    for message in messages:
        meta = message.meta or {}
        if message.role == "user":
            lines += ["## 用户", "", message.content, ""]
            continue
        heading = "## 助手"
        model_name = ((meta.get("model") or {}).get("modelName") or message.provider or "").strip()
        details = [part for part in (model_name, message.skill) if part]
        if details:
            heading += f"（{' · '.join(details)}）"
        lines += [heading, ""]
        lines += [message.content or "（无文本输出）", ""]
        usage = meta.get("usage") or {}
        if usage:
            lines += [
                f"> tokens：输入 {usage.get('promptTokens', 0)} / 输出 {usage.get('completionTokens', 0)}",
                "",
            ]
        if message.error:
            lines += [f"> 错误：{message.error}", ""]
        tool_entries = meta.get("toolLog") or []
        if tool_entries:
            lines += ["<details><summary>工具调用</summary>", ""]
            lines += _tool_lines(tool_entries)
            lines += ["", "</details>", ""]
        lines += ["---", ""]
    return "\n".join(lines).rstrip() + "\n"
