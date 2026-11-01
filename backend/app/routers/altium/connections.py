from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.ai_tools import registry
from app.models.altium.audit import AltiumCommandAudit
from app.models.altium.connection import ConnectionGrant, GatewayConnection
from app.models.system.user import User
from app.schemas import CamelModel
from app.security import get_current_user, require_admin
from app.services.altium.access import get_accessible_connection, visible_connections
from app.services.altium.audit import audit_out, execute_audited, split_request_id, undo_audit
from app.services.altium.drift import compare_drift
from app.services.altium.gateway_client import GatewayClient, GatewayError
from app.services.files.access import get_owned_project
from app.services.system.credentials import encrypt_credential
from app.services.system.outbound import display_base_url, validate_outbound_url

router = APIRouter(prefix="/altium/connections", tags=["altium"])


class ConnectionIn(CamelModel):
    name: str = Field(min_length=1, max_length=100)
    base_url: str = Field(max_length=500)
    api_token: str | None = None
    remark: str = Field(default="", max_length=500)


class ConnectionOut(CamelModel):
    id: str
    name: str
    base_url: str
    has_token: bool
    remark: str
    status: str
    last_error: str
    info: dict = {}
    last_checked_at: str | None = None
    created_at: str


class GrantsIn(CamelModel):
    user_ids: list[UUID]


class GrantsOut(GrantsIn):
    connection_id: UUID


class CommandIn(CamelModel):
    name: str = Field(min_length=1, max_length=100)
    params: dict = {}


def _out(c: GatewayConnection) -> ConnectionOut:
    return ConnectionOut(
        id=str(c.id), name=c.name, base_url=display_base_url(c.base_url), has_token=bool(c.api_token),
        status=c.status, last_error="gateway_unavailable" if c.last_error else "",
        info=({"mode": "mock" if c.info.get("mode") == "mock" else "live",
               "altiumOnline": bool(c.info.get("altiumOnline"))} if isinstance(c.info, dict) and c.info else {}),
        last_checked_at=c.last_checked_at.isoformat() if c.last_checked_at else None,
        remark=c.remark, created_at=c.created_at.isoformat(),
    )


async def _values(body: ConnectionIn) -> dict:
    values = body.model_dump(exclude={"api_token"})
    values["base_url"] = await validate_outbound_url(body.base_url)
    if body.api_token is not None:
        values["api_token"] = encrypt_credential(body.api_token)
    return values


@router.get("", response_model=list[ConnectionOut])
async def list_connections(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    connections = (await db.execute(visible_connections(user).order_by(GatewayConnection.created_at))).scalars()
    return [_out(c) for c in connections]


@router.post("", response_model=ConnectionOut)
async def create_connection(body: ConnectionIn, db: AsyncSession = Depends(get_db), user=Depends(require_admin)):
    conn = GatewayConnection(**await _values(body), status="unreachable")
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return _out(conn)


@router.put("/{connection_id}", response_model=ConnectionOut)
async def update_connection(connection_id: UUID, body: ConnectionIn, db: AsyncSession = Depends(get_db), user=Depends(require_admin)):
    conn = await get_accessible_connection(db, connection_id, user.id)
    for key, value in (await _values(body)).items():
        setattr(conn, key, value)
    conn.status, conn.last_error, conn.info, conn.last_checked_at = "unreachable", "", {}, None
    await db.commit()
    await db.refresh(conn)
    registry.drop_connection(conn.id)
    return _out(conn)


@router.get("/{connection_id}/grants", response_model=GrantsOut)
async def get_grants(connection_id: UUID, db: AsyncSession = Depends(get_db), user=Depends(require_admin)):
    await get_accessible_connection(db, connection_id, user.id)
    ids = (await db.execute(select(ConnectionGrant.user_id).where(ConnectionGrant.connection_id == connection_id).order_by(ConnectionGrant.user_id))).scalars().all()
    return GrantsOut(connection_id=connection_id, user_ids=ids)


@router.put("/{connection_id}/grants", response_model=GrantsOut)
async def replace_grants(connection_id: UUID, body: GrantsIn, db: AsyncSession = Depends(get_db), user=Depends(require_admin)):
    await get_accessible_connection(db, connection_id, user.id)
    await db.execute(select(GatewayConnection).where(GatewayConnection.id == connection_id).with_for_update())
    ids = set(body.user_ids)
    valid = set((await db.execute(select(User.id).where(User.id.in_(ids), User.is_active.is_(True), User.is_deleted.is_(False)))).scalars())
    if ids != valid:
        raise HTTPException(400, "userIds must identify active users")
    await db.execute(delete(ConnectionGrant).where(ConnectionGrant.connection_id == connection_id))
    db.add_all([ConnectionGrant(connection_id=connection_id, user_id=uid) for uid in ids])
    await db.commit()
    return GrantsOut(connection_id=connection_id, user_ids=sorted(ids))


@router.post("/{connection_id}/test", response_model=ConnectionOut)
async def test_connection(connection_id: UUID, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    conn = await get_accessible_connection(db, connection_id, user.id)
    conn.last_checked_at = datetime.now(timezone.utc)
    try:
        health = await GatewayClient(conn.base_url, conn.api_token).health()
        conn.status = "connected" if health.get("altiumOnline") else "unreachable"
        conn.info = {"mode": "mock" if health.get("mode") == "mock" else "live", "altiumOnline": bool(health.get("altiumOnline"))}
        conn.last_error = "" if health.get("altiumOnline") else "gateway_unavailable"
    except GatewayError:
        conn.status, conn.last_error, conn.info = "unreachable", "gateway_unavailable", {}
    await db.commit()
    await db.refresh(conn)
    return _out(conn)


@router.post("/{connection_id}/command")
async def run_command(
    connection_id: UUID,
    body: CommandIn,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    """执行 gateway 命令（读命令直接执行；写命令需带 dry_run/confirmed 参数）。

    确认执行的写命令会落审计；请求体可带 ``requestId`` 作为幂等键。
    """
    conn = await get_accessible_connection(db, connection_id, user.id)
    params, request_id = split_request_id(body.params)
    client = GatewayClient(conn.base_url, conn.api_token)
    try:
        return await execute_audited(
            db,
            client=client,
            connection_id=conn.id,
            user_id=user.id,
            name=body.name,
            params=params,
            request_id=request_id,
        )
    except GatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/{connection_id}/commands/audit")
async def list_command_audit(
    connection_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
) -> list[dict]:
    conn = await get_accessible_connection(db, connection_id, user.id)
    rows = await db.execute(
        select(AltiumCommandAudit)
        .where(AltiumCommandAudit.connection_id == conn.id)
        .order_by(AltiumCommandAudit.created_at.desc())
        .limit(limit)
    )
    return [audit_out(row) for row in rows.scalars()]


@router.post("/{connection_id}/commands/audit/{audit_id}/undo")
async def undo_command(
    connection_id: UUID,
    audit_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    conn = await get_accessible_connection(db, connection_id, user.id)
    try:
        return await undo_audit(
            db,
            client=GatewayClient(conn.base_url, conn.api_token),
            connection_id=conn.id,
            user_id=user.id,
            audit_id=audit_id,
        )
    except GatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/{connection_id}/drift")
async def live_drift(
    connection_id: UUID,
    project_id: UUID = Query(alias="projectId"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    """实时 Altium 设计与离线快照的元件/网络漂移对比。"""
    conn = await get_accessible_connection(db, connection_id, user.id)
    project = await get_owned_project(db, project_id, user.id)
    client = GatewayClient(conn.base_url, conn.api_token)
    try:
        components = await client.command("altium_get_schematic_components")
        nets = await client.command("altium_get_schematic_nets")
    except GatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {
        "projectId": str(project.id),
        "projectName": project.name,
        "snapshotVersion": project.current_version,
        **compare_drift(
            components.get("items") or [] if isinstance(components, dict) else [],
            nets.get("items") or [] if isinstance(nets, dict) else [],
            project.snapshot or {},
        ),
    }


@router.get("/{connection_id}/live/summary")
async def live_summary(connection_id: UUID, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    conn = await get_accessible_connection(db, connection_id, user.id)
    try:
        return await GatewayClient(conn.base_url, conn.api_token).live_summary()
    except GatewayError as exc:
        raise HTTPException(502, str(exc)) from None


@router.get("/{connection_id}/screenshot")
async def screenshot(connection_id: UUID, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    conn = await get_accessible_connection(db, connection_id, user.id)
    try:
        content, media_type = await GatewayClient(conn.base_url, conn.api_token).screenshot()
    except GatewayError as exc:
        raise HTTPException(502, str(exc)) from None
    return Response(content=content, media_type=media_type)


@router.delete("/{connection_id}")
async def delete_connection(connection_id: UUID, db: AsyncSession = Depends(get_db), user=Depends(require_admin)):
    conn = await get_accessible_connection(db, connection_id, user.id)
    conn.is_deleted = True
    await db.execute(delete(ConnectionGrant).where(ConnectionGrant.connection_id == connection_id))
    await db.commit()
    registry.drop_connection(conn.id)
    return {"ok": True}
