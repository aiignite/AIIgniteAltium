"""Altium 实时连接：配置 CRUD + 连接测试 + 实时摘要 + 截图代理。

gateway 部署在局域网 Windows 机（已装 Altium）上，本路由经 REST 调用。
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.altium.connection import GatewayConnection
from app.schemas import CamelModel
from app.security import get_current_user
from app.services.altium.gateway_client import GatewayClient, GatewayError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/altium/connections", tags=["altium"])


class ConnectionIn(CamelModel):
    name: str = Field(min_length=1, max_length=100)
    base_url: str = "http://192.168.1.14:3296"
    api_token: str = ""
    remark: str = ""


class ConnectionOut(ConnectionIn):
    id: str
    status: str
    last_error: str
    info: dict = {}
    last_checked_at: str | None = None
    created_at: str


class CommandIn(CamelModel):
    name: str = Field(min_length=1, max_length=100)
    params: dict = {}


def _out(c: GatewayConnection) -> ConnectionOut:
    return ConnectionOut(
        id=str(c.id),
        name=c.name,
        base_url=c.base_url,
        api_token=c.api_token,
        status=c.status,
        last_error=c.last_error,
        info=c.info or {},
        last_checked_at=c.last_checked_at.isoformat() if c.last_checked_at else None,
        remark=c.remark,
        created_at=c.created_at.isoformat(),
    )


async def _get_connection(db: AsyncSession, connection_id: UUID) -> GatewayConnection:
    conn = await db.get(GatewayConnection, connection_id)
    if conn is None or conn.is_deleted:
        raise HTTPException(status_code=404, detail="连接不存在")
    return conn


def _client(conn: GatewayConnection) -> GatewayClient:
    return GatewayClient(conn.base_url, conn.api_token)


@router.get("", response_model=list[ConnectionOut])
async def list_connections(
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> list[ConnectionOut]:
    result = await db.execute(
        select(GatewayConnection)
        .where(GatewayConnection.is_deleted.is_(False))
        .order_by(GatewayConnection.created_at)
    )
    return [_out(c) for c in result.scalars()]


@router.post("", response_model=ConnectionOut)
async def create_connection(
    body: ConnectionIn,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> ConnectionOut:
    conn = GatewayConnection(**body.model_dump(), status="unreachable")
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return _out(conn)


@router.post("/{connection_id}/test", response_model=ConnectionOut)
async def test_connection(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> ConnectionOut:
    conn = await _get_connection(db, connection_id)
    client = _client(conn)
    conn.last_checked_at = datetime.now(timezone.utc)
    try:
        health = await client.health()
        conn.status = "connected" if health.get("altiumOnline") else "unreachable"
        conn.info = {
            "mode": health.get("mode"),
            "altiumOnline": health.get("altiumOnline"),
            "commands": health.get("commands"),
            "bridgeDir": health.get("bridgeDir"),
        }
        if not health.get("altiumOnline"):
            conn.last_error = "gateway 在线但 Altium 桥未就绪（检查 AIDriveBridge 脚本是否运行）"
        else:
            conn.last_error = ""
    except GatewayError as exc:
        conn.status = "unreachable"
        conn.last_error = str(exc)[:1000]
        conn.info = {}
    await db.commit()
    await db.refresh(conn)
    return _out(conn)


@router.post("/{connection_id}/command")
async def run_command(
    connection_id: UUID,
    body: CommandIn,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> dict:
    """执行 gateway 命令（读命令直接执行；写命令需带 dry_run/confirmed 参数）。"""
    conn = await _get_connection(db, connection_id)
    try:
        return await _client(conn).command(body.name, body.params)
    except GatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/{connection_id}/live/summary")
async def live_summary(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> dict:
    conn = await _get_connection(db, connection_id)
    try:
        return await _client(conn).live_summary()
    except GatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/{connection_id}/screenshot")
async def screenshot(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> Response:
    conn = await _get_connection(db, connection_id)
    try:
        content, media_type = await _client(conn).screenshot()
    except GatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return Response(content=content, media_type=media_type)


@router.get("/first-connected")
async def first_connected(
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> dict:
    """供对话实时上下文使用：返回第一条 connected 连接，无则 {connected: false}。"""
    result = await db.execute(
        select(GatewayConnection)
        .where(GatewayConnection.status == "connected", GatewayConnection.is_deleted.is_(False))
        .order_by(GatewayConnection.created_at)
        .limit(1)
    )
    conn = result.scalars().first()
    if conn is None:
        return {"connected": False}
    return {"connected": True, "id": str(conn.id), "baseUrl": conn.base_url, "token": conn.api_token}


@router.delete("/{connection_id}")
async def delete_connection(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    conn = await _get_connection(db, connection_id)
    conn.is_deleted = True
    await db.commit()
    return {"ok": True}
