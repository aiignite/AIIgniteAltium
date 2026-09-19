"""Altium 实时连接（第二步启用）：第一步仅提供连接配置 CRUD 与状态占位。"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.altium.connection import GatewayConnection
from app.schemas import CamelModel
from app.security import get_current_user

router = APIRouter(prefix="/altium/connections", tags=["altium"])


class ConnectionIn(CamelModel):
    name: str = Field(min_length=1, max_length=100)
    base_url: str = "http://localhost:3296"
    api_token: str = ""
    remark: str = ""


class ConnectionOut(ConnectionIn):
    id: str
    status: str
    created_at: str


def _out(c: GatewayConnection) -> ConnectionOut:
    return ConnectionOut(
        id=str(c.id),
        name=c.name,
        base_url=c.base_url,
        api_token=c.api_token,
        status=c.status,
        remark=c.remark,
        created_at=c.created_at.isoformat(),
    )


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


@router.delete("/{connection_id}")
async def delete_connection(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    conn = await db.get(GatewayConnection, connection_id)
    if conn is None or conn.is_deleted:
        raise HTTPException(status_code=404, detail="连接不存在")
    conn.is_deleted = True
    await db.commit()
    return {"ok": True}
