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
            logger.exception("tool %s failed", name)
            return {"success": False, "error": str(exc)}


registry = ToolRegistry()


async def get_live_design_summary(connection_id: str = "", base_url: str = "", token: str = "") -> dict[str, Any]:
    """拉取 gateway 聚合实时摘要。参数为空时使用第一条 connected 连接。"""
    from sqlalchemy import select

    from app.database import async_session_maker
    from app.models.altium.connection import GatewayConnection
    from app.services.altium.gateway_client import GatewayClient

    async with async_session_maker() as db:
        if connection_id:
            conn = await db.get(GatewayConnection, connection_id)
        else:
            result = await db.execute(
                select(GatewayConnection)
                .where(GatewayConnection.status == "connected", GatewayConnection.is_deleted.is_(False))
                .order_by(GatewayConnection.created_at)
                .limit(1)
            )
            conn = result.scalars().first()
    if conn is None and not base_url:
        return {"success": False, "error": "无已连接的 Altium 网关"}
    client = GatewayClient(base_url or conn.base_url, token or (conn.api_token if conn else ""))
    summary = await client.live_summary()
    return {"success": bool(summary.get("ok")), **summary}


def register_default_tools() -> None:
    if registry.get("get_live_design_summary") is None:
        registry.register(
            name="get_live_design_summary",
            description="获取 Altium 当前打开工程的实时摘要（工程名/PCB统计/原理图元件与网络）",
            category="altium",
            handler=get_live_design_summary,
        )


register_default_tools()
