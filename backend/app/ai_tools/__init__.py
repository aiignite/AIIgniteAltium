"""AI 工具注册中心（沿 AIIgnitePLM plm-ai-assistant-integration 约定）。

- 本地业务工具：直接注册 handler（离线快照查询、实时摘要）
- gateway REST 工具：``sync_gateway_tools()`` 按连接拉取 /tools 并包装注册

执行上下文（``ToolContext``）由编排器在每轮对话前设置，决定工具能看到/操作哪台
网关与哪个工程：不存在「取第一条在线连接」这类隐式路由，连接与工程一律按所有者/
授权校验。工具执行统一返回 ``{"success": bool, ...}`` 信封。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from functools import partial
from typing import Any
from uuid import UUID

from fastapi import HTTPException

from app.services.altium.gateway_client import GatewayClient, GatewayError

logger = logging.getLogger(__name__)

Handler = Callable[..., Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ToolContext:
    """本轮对话的工具可见范围与执行目标。"""

    user_id: UUID | None = None
    connection_id: UUID | None = None
    project_id: UUID | None = None


_tool_context: ContextVar[ToolContext] = ContextVar("aidrive_tool_context", default=ToolContext())


def current_tool_context() -> ToolContext:
    return _tool_context.get()


def set_tool_context(context: ToolContext) -> Token[ToolContext]:
    return _tool_context.set(context)


def reset_tool_context(token: Token[ToolContext]) -> None:
    _tool_context.reset(token)


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
        connection_id: str | None = None,
    ) -> None:
        self._tools[name] = {
            "name": name,
            "description": description,
            "category": category,
            "handler": handler,
            "requires_confirmation": requires_confirmation,
            "params_schema": params_schema or {},
            "connection_id": connection_id,
        }

    def get(self, name: str) -> dict[str, Any] | None:
        return self._tools.get(name)

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get_tools_by_category(self, category: str) -> list[dict[str, Any]]:
        return [t for t in self._tools.values() if t["category"] == category]

    def list_all(self) -> list[dict[str, Any]]:
        return list(self._tools.values())

    def visible(self, context: ToolContext | None = None) -> list[dict[str, Any]]:
        """本地工具恒可见；网关工具只在同一连接的会话中可见（避免跨连接串用）。"""
        ctx = context or current_tool_context()
        target = str(ctx.connection_id) if ctx.connection_id else None
        return [t for t in self._tools.values() if t["connection_id"] is None or t["connection_id"] == target]

    def replace_connection_tools(self, connection_id: UUID, tools: list[dict[str, Any]]) -> int:
        """用最新清单替换该连接的网关工具（命令增删或连接失效后不留残留）。"""
        marker = str(connection_id)
        stale = [name for name, t in self._tools.items() if t["connection_id"] == marker]
        for name in stale:
            self.unregister(name)
        count = 0
        for t in tools:
            name = t.get("name")
            if not name or self.get(name) is not None:
                continue
            self.register(
                name=name,
                description=t.get("description", ""),
                category=t.get("category", "altium"),
                handler=partial(_gateway_tool_handler, name),
                requires_confirmation=bool(t.get("requiresConfirmation")),
                params_schema=t.get("paramsSchema") or {},
                connection_id=marker,
            )
            count += 1
        return count

    def drop_connection(self, connection_id: UUID) -> int:
        marker = str(connection_id)
        names = [name for name, t in self._tools.items() if t["connection_id"] == marker]
        for name in names:
            self.unregister(name)
        return len(names)

    async def execute(self, tool_name: str, /, **params: Any) -> dict[str, Any]:
        tool = self._tools.get(tool_name)
        if tool is None:
            return {"success": False, "error": f"未知工具: {tool_name}"}
        ctx = current_tool_context()
        if tool["connection_id"] is not None and tool["connection_id"] != (str(ctx.connection_id) if ctx.connection_id else None):
            return {"success": False, "error": "该工具属于其他 Altium 连接，当前对话未关联此连接"}
        try:
            return await tool["handler"](**params)
        except Exception as exc:  # noqa: BLE001 —— 工具错误以信封返回，不中断编排
            logger.warning("tool failed tool=%s category=%s error=%s", tool_name, type(exc).__name__, exc)
            return {"success": False, "error": "tool_unavailable"}


registry = ToolRegistry()


async def _available_connections(context: ToolContext) -> list[UUID]:
    """工具可用的连接：会话指定则仅此连接，否则该用户可见且在线的连接。"""
    from sqlalchemy import select

    from app.database import async_session_maker
    from app.models.altium.connection import GatewayConnection
    from app.services.altium.access import active_user, get_accessible_connection, visible_connections

    async with async_session_maker() as db:
        if context.connection_id is not None:
            try:
                conn = await get_accessible_connection(db, context.connection_id, context.user_id)
            except HTTPException:
                return []
            return [conn.id]
        if context.user_id is None:
            return []
        try:
            user = await active_user(db, context.user_id)
        except HTTPException:
            return []
        statement = visible_connections(user).where(
            GatewayConnection.status == "connected"
        ).order_by(GatewayConnection.created_at).limit(5)
        return [c.id for c in (await db.execute(statement)).scalars()]


async def _connection_client(connection_id: UUID, user_id: UUID | None):
    from app.database import async_session_maker
    from app.services.altium.access import get_accessible_connection

    async with async_session_maker() as db:
        try:
            conn = await get_accessible_connection(db, connection_id, user_id)
        except HTTPException as exc:
            return None, f"当前对话关联的 Altium 连接不可用：{exc.detail}"
    return GatewayClient(conn.base_url, conn.api_token), ""


async def _gateway_tool_handler(name: str, **params: Any) -> dict[str, Any]:
    """网关工具统一 handler：仅在会话关联的连接上执行（含 dry_run/confirmed 控制参数）。"""
    context = current_tool_context()
    if context.connection_id is None:
        return {"success": False, "error": "当前对话未关联 Altium 实时连接，无法执行该命令"}
    client, error = await _connection_client(context.connection_id, context.user_id)
    if client is None:
        return {"success": False, "error": error}
    try:
        payload = await client.command(name, params)
    except GatewayError as exc:
        return {"success": False, "error": str(exc)}
    return {"success": True, **payload}


async def get_live_design_summary(**_ignored: Any) -> dict[str, Any]:
    """实时摘要：只读会话关联的连接，模型无法指定地址或令牌。"""
    context = current_tool_context()
    if context.connection_id is None:
        return {"success": False, "error": "当前对话未关联 Altium 实时连接"}
    client, error = await _connection_client(context.connection_id, context.user_id)
    if client is None:
        return {"success": False, "error": error}
    try:
        summary = await client.live_summary()
    except GatewayError as exc:
        return {"success": False, "error": str(exc)}
    return {**summary, "success": bool(summary.get("ok"))}


async def sync_gateway_tools(context: ToolContext | None = None) -> int:
    """按上下文可用连接刷新网关工具（幂等；无上下文连接时不引入任何隐式默认）。"""
    ctx = context or current_tool_context()
    total = 0
    for connection_id in await _available_connections(ctx):
        client, _error = await _connection_client(connection_id, ctx.user_id)
        if client is None:
            registry.drop_connection(connection_id)
            continue
        try:
            tools = await client.tools()
        except Exception as exc:  # noqa: BLE001 —— 同步失败不影响主流程
            logger.info("sync_gateway_tools skipped connection=%s error=%s", connection_id, exc)
            continue
        total += registry.replace_connection_tools(connection_id, tools)
    return total


_TYPE_MAP = {"str": "string", "int": "integer", "float": "number", "bool": "boolean"}


def _definition(t: dict[str, Any]) -> dict[str, Any]:
    name = t["name"]
    desc = t["description"]
    if t["requires_confirmation"]:
        desc += "（写操作：先调用获取预览，用户明确同意后带 confirmed=true 再调用执行）"
    props: dict[str, Any] = {}
    required: list[str] = []
    for key, spec in (t.get("params_schema") or {}).items():
        if isinstance(spec, dict):
            kind = spec.get("type", "str")
            item = {"type": _TYPE_MAP.get(str(kind), str(kind) if str(kind) in ("object", "array") else "string")}
            if spec.get("description"):
                item["description"] = spec["description"]
            if spec.get("enum"):
                item["enum"] = spec["enum"]
            optional = bool(spec.get("required", True) is False)
        else:
            item = {"type": _TYPE_MAP.get(str(spec), "string")}
            optional = False
        props[key] = item
        if not optional:
            required.append(key)
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required},
        },
    }


def tool_definitions(context: ToolContext | None = None) -> list[dict[str, Any]]:
    """把注册表中当前上下文可见的工具转成 OpenAI/Anthropic 兼容的 tools 参数。"""
    return [_definition(t) for t in registry.visible(context)]


def register_default_tools() -> None:
    from app.ai_tools.design_tools import register_design_tools

    if registry.get("get_live_design_summary") is None:
        registry.register(
            name="get_live_design_summary",
            description="获取本对话关联的 Altium 实时设计摘要（工程名/PCB统计/原理图元件与网络）",
            category="altium",
            handler=get_live_design_summary,
        )
    register_design_tools(registry)


register_default_tools()
