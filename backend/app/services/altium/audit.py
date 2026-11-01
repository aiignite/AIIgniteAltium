"""Altium 写命令审计与撤销（ADR-001 目标态的审计/撤销部分）。

- 只对用户确认的写命令落审计；读命令与 dry-run 不记录
- requestId 作为幂等键：同一连接重复提交返回首次结果，不重复执行
- 撤销基于执行前状态生成确定性逆命令（move/rotate/highlight），并新增一条 undo 审计
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.altium.audit import AltiumCommandAudit

logger = logging.getLogger(__name__)

UNDOABLE_COMMANDS = frozenset(
    {"altium_move_component", "altium_rotate_component", "altium_highlight_net"}
)
_CONTROL_KEYS = frozenset({"dry_run", "dryRun", "confirmed", "confirm"})
_REQUEST_KEYS = ("requestId", "request_id")
_SENSITIVE = ("token", "secret", "apikey", "api_key", "password")


def split_request_id(params: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """剥离 requestId 控制参数（不下发给 gateway），返回清洗后的参数与幂等键。"""
    clean = {k: v for k, v in (params or {}).items() if k not in _REQUEST_KEYS}
    raw = next((v for k, v in (params or {}).items() if k in _REQUEST_KEYS and v), None)
    request_id = str(raw).strip()[:80] if raw is not None else ""
    return clean, request_id or None


def _safe_params(params: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in (params or {}).items()
        if not any(word in str(key).lower() for word in _SENSITIVE)
    }


def _confirmed(params: dict[str, Any]) -> bool:
    return bool(params.get("confirmed") or params.get("confirm"))


async def _find_by_request(
    db: AsyncSession, connection_id: UUID, request_id: str | None
) -> AltiumCommandAudit | None:
    if not request_id:
        return None
    result = await db.execute(
        select(AltiumCommandAudit).where(
            AltiumCommandAudit.connection_id == connection_id,
            AltiumCommandAudit.request_id == request_id,
        )
    )
    return result.scalars().first()


async def _capture_before(client, command: str, params: dict[str, Any]) -> dict[str, Any]:
    """执行前状态：move/rotate 通过 dry-run 获取当前位姿；highlight 记录请求模式。"""
    if command == "altium_highlight_net":
        mode = 1 if str(params.get("mode", 1)) != "0" else 0
        return {"mode": mode}
    if command not in UNDOABLE_COMMANDS:
        return {}
    try:
        preview = await client.command(
            command,
            {k: v for k, v in params.items() if k not in _CONTROL_KEYS} | {"dry_run": True},
        )
    except Exception:  # noqa: BLE001 —— 预查询失败不阻止执行，只是失去撤销依据
        logger.warning("command audit preview failed command=%s", command)
        return {}
    current = preview.get("current") if isinstance(preview, dict) else None
    return dict(current) if isinstance(current, dict) else {}


def inverse_command(audit: AltiumCommandAudit) -> tuple[str, dict[str, Any]] | None:
    params = audit.params or {}
    before = audit.before or {}
    if audit.command == "altium_move_component":
        if before.get("x") is None or before.get("y") is None:
            return None
        return audit.command, {
            "designator": params.get("designator", ""),
            "x": before["x"],
            "y": before["y"],
            "confirmed": True,
        }
    if audit.command == "altium_rotate_component":
        if before.get("rotation") is None:
            return None
        return audit.command, {
            "designator": params.get("designator", ""),
            "rotation": before["rotation"],
            "confirmed": True,
        }
    if audit.command == "altium_highlight_net":
        net = params.get("net")
        if not net:
            return None
        return audit.command, {
            "net": net,
            "mode": 0 if int(before.get("mode", 1)) else 1,
            "confirmed": True,
        }
    return None


def _payload_ok(payload: dict[str, Any]) -> bool:
    return isinstance(payload, dict) and payload.get("ok") is not False


def _expected_after(audit: AltiumCommandAudit) -> dict[str, Any]:
    """撤销前应当看到的状态（= 本次命令执行后的结果），用于检测其后是否又被改动。"""
    params = audit.params or {}
    if audit.command == "altium_move_component":
        return {k: params[k] for k in ("x", "y") if params.get(k) is not None}
    if audit.command == "altium_rotate_component":
        return {"rotation": params["rotation"]} if params.get("rotation") is not None else {}
    return {}


def _same_value(expected: Any, actual: Any) -> bool:
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(float(expected) - float(actual)) < 1e-3
    return str(expected).strip().lower() == str(actual).strip().lower()


def _drift_conflict(expected: dict[str, Any], current: dict[str, Any]) -> list[str]:
    if not expected or not current:
        return []
    return [
        f"{key}: 期望 {expected[key]}，实际 {current[key]}"
        for key, value in expected.items()
        if key in current and not _same_value(value, current[key])
    ]


def audit_out(audit: AltiumCommandAudit) -> dict[str, Any]:
    verification = (audit.result or {}).get("verification") or {}
    return {
        "id": str(audit.id),
        "command": audit.command,
        "params": audit.params or {},
        "before": audit.before or {},
        "status": audit.status,
        "requestId": audit.request_id or "",
        "undoOfId": str(audit.undo_of_id) if audit.undo_of_id else None,
        "error": audit.error,
        "verification": verification,
        "verified": bool(verification.get("checked")) and bool(verification.get("ok")),
        "verifyFailed": bool(verification.get("checked")) and not bool(verification.get("ok")),
        "canUndo": audit.status == "executed" and inverse_command(audit) is not None,
        "createdAt": audit.created_at.isoformat(),
        "undoneAt": audit.undone_at.isoformat() if audit.undone_at else None,
    }


async def execute_audited(
    db: AsyncSession,
    *,
    client,
    connection_id: UUID,
    user_id: UUID,
    name: str,
    params: dict[str, Any],
    request_id: str | None,
) -> dict[str, Any]:
    """执行命令；写命令落审计，requestId 命中时重放首次结果。"""
    if request_id:
        existing = await _find_by_request(db, connection_id, request_id)
        if existing is not None:
            return {**(existing.result or {}), "auditId": str(existing.id), "replayed": True}

    audited = _confirmed(params) and name.startswith("altium_")
    before = await _capture_before(client, name, params) if audited else {}
    payload = await client.command(name, params)
    if not isinstance(payload, dict):
        payload = {"ok": False, "error": "invalid_response"}

    if not audited:
        return payload

    ok = _payload_ok(payload)
    verification: dict[str, Any] = {}
    if ok:
        from app.services.altium.verification import verify_write

        verification = await verify_write(client, name, params)
        payload = {**payload, "verification": verification}
    audit = AltiumCommandAudit(
        user_id=user_id,
        connection_id=connection_id,
        command=name,
        params=_safe_params({k: v for k, v in params.items() if k not in _CONTROL_KEYS}),
        before=_safe_params(before),
        result=_safe_params(payload),
        status="executed" if ok else "failed",
        request_id=request_id,
        error="" if ok else str(payload.get("error") or "command_failed")[:2000],
    )
    db.add(audit)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await _find_by_request(db, connection_id, request_id)
        if existing is not None:
            return {**(existing.result or {}), "auditId": str(existing.id), "replayed": True}
        raise
    await db.refresh(audit)
    return {**payload, "auditId": str(audit.id)}


async def undo_audit(
    db: AsyncSession, *, client, connection_id: UUID, user_id: UUID, audit_id: UUID
) -> dict[str, Any]:
    audit = await db.get(AltiumCommandAudit, audit_id)
    if audit is None or audit.connection_id != connection_id:
        raise HTTPException(404, "审计记录不存在")
    if audit.status != "executed":
        raise HTTPException(409, "该记录不可撤销（已撤销或执行失败）")
    inverse = inverse_command(audit)
    if inverse is None:
        raise HTTPException(409, "该命令没有可用的撤销路径")
    name, params = inverse
    expected = _expected_after(audit)
    current = await _capture_before(client, audit.command, audit.params or {})
    conflicts = _drift_conflict(expected, current)
    if conflicts:
        raise HTTPException(409, "该命令之后设计又被改动，撤销会覆盖后续修改，请手动恢复到目标状态：" + "；".join(conflicts))
    payload = await client.command(name, params)
    if not isinstance(payload, dict):
        payload = {"ok": False, "error": "invalid_response"}
    ok = _payload_ok(payload)

    if ok:
        from app.services.altium.verification import verify_write

        # 撤销同样是写操作：读回确认已恢复到执行前位姿
        payload = {**payload, "verification": await verify_write(client, name, params)}

    now = datetime.now(timezone.utc)
    undo_row = AltiumCommandAudit(
        user_id=user_id,
        connection_id=connection_id,
        command=name,
        params=_safe_params({k: v for k, v in params.items() if k not in _CONTROL_KEYS}),
        before={"undoOf": str(audit.id), **(audit.params or {})},
        result=_safe_params(payload),
        status="executed" if ok else "failed",
        undo_of_id=audit.id,
        error="" if ok else str(payload.get("error") or "undo_failed")[:2000],
    )
    if ok:
        # 仅在逆命令成功时才标记已撤销，失败时原记录保持可再次撤销
        audit.status = "undone"
        audit.undone_by_id = user_id
        audit.undone_at = now
    db.add(undo_row)
    await db.commit()
    await db.refresh(undo_row)
    await db.refresh(audit)
    return {
        "ok": ok,
        "result": payload,
        "auditId": str(undo_row.id),
        "undone": audit_out(audit) if ok else None,
        "error": "" if ok else (undo_row.error or "undo_failed"),
    }
