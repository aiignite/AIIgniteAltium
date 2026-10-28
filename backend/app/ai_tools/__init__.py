"""AI 工具注册中心（沿 AIIgnitePLM plm-ai-assistant-integration 约定）。

- 本地业务工具：直接注册 handler
- gateway MCP/REST 工具：sync_gateway_tools() 从已连接 gateway 拉取清单并包装注册

工具执行统一返回 {"success": True/False, ...} 信封。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

Handler = Callable[..., Awaitable[dict[str, Any]]]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, dict[str, Any]] = {}

    def register(
        self,
        name: str,
        description: str,
        category: str,
        handler: Handler,
        *,
        requires_confirmation: bool = False,
        params_schema: dict[str, Any] | None = None,
    ) -> None:
        self._tools[name] = {
            "name": name,
            "description": description,
            "category": category,
            "handler": handler,
            "requires_confirmation": requires_confirmation,
            "params_schema": params_schema or {},
        }

    def get(self, name: str) -> dict[str, Any] | None:
        return self._tools.get(name)

    def get_tools_by_category(self, category: str) -> list[dict[str, Any]]:
        return [t for t in self._tools.values() if t["category"] == category]

    def list_all(self) -> list[dict[str, Any]]:
        return list(self._tools.values())

    async def execute(self, name: str, **params: Any) -> dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            return {"success": False, "error": f"未知工具: {name}"}
        try:
            return await tool["handler"](**params)
        except Exception as exc:  # noqa: BLE001 —— 工具错误以信封返回，不中断编排
            logger.warning("tool failed category=%s", type(exc).__name__)
            return {"success": False, "error": "tool_unavailable"}


registry = ToolRegistry()


async def get_live_design_summary(*, user_id: str, connection_id: str) -> dict[str, Any]:
    from uuid import UUID

    from app.database import async_session_maker
    from app.services.altium.access import get_accessible_connection
    from app.services.altium.gateway_client import GatewayClient

    async with async_session_maker() as db:
        conn = await get_accessible_connection(db, UUID(connection_id), UUID(user_id))
        summary = await GatewayClient(conn.base_url, conn.api_token).live_summary()
    return {**summary, "success": bool(summary.get("ok"))}


def register_default_tools() -> None:
    if registry.get("get_live_design_summary") is None:
        registry.register(
            name="get_live_design_summary",
            description="获取 Altium 当前打开工程的实时摘要（工程名/PCB统计/原理图元件与网络）",
            category="altium",
            handler=get_live_design_summary,
        )


register_default_tools()
