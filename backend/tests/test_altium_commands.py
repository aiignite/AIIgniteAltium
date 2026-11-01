import asyncio
from uuid import UUID

import pytest
from sqlalchemy import select

from app.models.ai.conversation import Conversation, Message
from app.models.altium.audit import AltiumCommandAudit
from app.models.altium.connection import ConnectionGrant, GatewayConnection
from app.models.files.uploaded_project import UploadedProject
from app.services.altium.gateway_client import GatewayClient
from conftest import auth

pytestmark = pytest.mark.integration
PREFIX = "/api/v1"


async def _connection(db, name="gateway"):
    conn = GatewayConnection(name=name, base_url="http://127.0.0.1:3296", api_token="")
    db.add(conn)
    await db.commit()
    return conn


async def test_write_command_audit_idempotency_and_undo(api, actors, db, monkeypatch):
    conn = await _connection(db)
    calls: list[tuple[str, dict]] = []
    state = {"x": 1000, "y": 800, "rotation": 0}

    async def command(self, name, params=None):
        calls.append((name, dict(params or {})))
        payload = params or {}
        if name == "altium_move_component" and payload.get("dry_run"):
            return {
                "ok": True, "command": name, "dryRun": True, "preview": "移动 U1",
                "current": {"designator": "U1", **state},
            }
        if name == "altium_move_component":
            state.update(x=payload.get("x"), y=payload.get("y"))
            return {"ok": True, "command": name, "designator": "U1", "x": payload.get("x"), "y": payload.get("y")}
        if name == "altium_get_pcb_stats":
            return {"ok": True, "components": 5}
        return {"ok": False, "error": "unexpected"}

    monkeypatch.setattr(GatewayClient, "command", command)
    admin = auth(actors["admin"])
    base = f"{PREFIX}/altium/connections/{conn.id}"
    body = {
        "name": "altium_move_component",
        "params": {"designator": "U1", "x": 1200, "y": 900, "confirmed": True, "requestId": "req-1"},
    }
    first = await api.post(base + "/command", json=body, headers=admin)
    assert first.status_code == 200
    data = first.json()
    assert data["ok"] is True and data["auditId"]
    # 写后即查：执行成功后再读回一次，确认状态真的落地
    assert data["verification"]["checked"] is True and data["verification"]["ok"] is True
    assert calls == [
        ("altium_move_component", {"designator": "U1", "x": 1200, "y": 900, "dry_run": True}),
        ("altium_move_component", {"designator": "U1", "x": 1200, "y": 900, "confirmed": True}),
        ("altium_move_component", {"designator": "U1", "x": 1200, "y": 900, "dry_run": True}),
    ]

    replay = await api.post(base + "/command", json=body, headers=admin)
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    assert len(calls) == 3

    listing = await api.get(base + "/commands/audit", headers=admin)
    items = listing.json()
    assert len(items) == 1
    assert items[0]["requestId"] == "req-1" and items[0]["canUndo"] is True
    assert items[0]["verified"] is True and items[0]["verifyFailed"] is False
    assert "requestId" not in items[0]["params"]

    undo = await api.post(base + f"/commands/audit/{items[0]['id']}/undo", headers=admin)
    assert undo.status_code == 200 and undo.json()["ok"] is True
    assert state == {"x": 1000, "y": 800, "rotation": 0}
    assert (
        "altium_move_component", {"designator": "U1", "x": 1000, "y": 800, "confirmed": True},
    ) in calls
    rows = (await db.execute(select(AltiumCommandAudit))).scalars().all()
    by_status = {row.status: row for row in rows}
    assert set(by_status) == {"undone", "executed"}
    assert by_status["executed"].undo_of_id == by_status["undone"].id

    again = await api.post(base + f"/commands/audit/{items[0]['id']}/undo", headers=admin)
    assert again.status_code == 409

    before_read = len(rows)
    read = await api.post(base + "/command", json={"name": "altium_get_pcb_stats", "params": {}}, headers=admin)
    assert read.status_code == 200 and read.json()["components"] == 5
    assert len((await db.execute(select(AltiumCommandAudit))).scalars().all()) == before_read

    # 未授权的普通用户既看不到审计也撤销不了
    denied = await api.get(base + "/commands/audit", headers=auth(actors["bob"]))
    assert denied.status_code == 404
    denied_undo = await api.post(base + f"/commands/audit/{items[0]['id']}/undo", headers=auth(actors["bob"]))
    assert denied_undo.status_code == 404


async def test_undo_blocked_when_design_changed_after_execution(api, actors, db, monkeypatch):
    """执行后设计又被改动时，撤销会覆盖后续修改，必须拒绝并保持记录可处理。"""
    conn = await _connection(db)
    state = {"x": 1000, "y": 800, "rotation": 0}

    async def command(self, name, params=None):
        payload = params or {}
        if name == "altium_move_component" and payload.get("dry_run"):
            return {"ok": True, "current": {"designator": "U1", **state}}
        if name == "altium_move_component":
            state.update(x=payload.get("x"), y=payload.get("y"))
            return {"ok": True, "designator": "U1", "x": payload.get("x"), "y": payload.get("y")}
        return {"ok": False, "error": "unexpected"}

    monkeypatch.setattr(GatewayClient, "command", command)
    admin = auth(actors["admin"])
    base = f"{PREFIX}/altium/connections/{conn.id}"
    executed = await api.post(base + "/command", json={
        "name": "altium_move_component",
        "params": {"designator": "U1", "x": 1200, "y": 900, "confirmed": True},
    }, headers=admin)
    audit_id = executed.json()["auditId"]

    state.update(x=1500, y=700)  # 用户在 Altium 里又手动挪了一次
    blocked = await api.post(base + f"/commands/audit/{audit_id}/undo", headers=admin)
    assert blocked.status_code == 409
    assert "又被改动" in blocked.json()["detail"]
    assert state == {"x": 1500, "y": 700, "rotation": 0}

    row = await db.get(AltiumCommandAudit, UUID(audit_id))
    assert row.status == "executed"


async def test_undo_failure_keeps_record_undoable(api, actors, db, monkeypatch):
    conn = await _connection(db)
    calls: list[dict] = []
    state = {"x": 1000, "y": 800, "rotation": 0}

    async def command(self, name, params=None):
        payload = params or {}
        calls.append(payload)
        if payload.get("dry_run"):
            return {"ok": True, "current": {"designator": "U1", **state}}
        if payload.get("confirmed"):
            target = {"x": payload.get("x"), "y": payload.get("y")}
            if target == {"x": 1000, "y": 800}:  # 逆命令在桥上失败
                return {"ok": False, "error": "bridge timeout"}
            state.update(target)
            return {"ok": True, "designator": "U1", **target}
        return {"ok": False, "error": "unexpected"}

    monkeypatch.setattr(GatewayClient, "command", command)
    admin = auth(actors["admin"])
    base = f"{PREFIX}/altium/connections/{conn.id}"
    executed = await api.post(base + "/command", json={
        "name": "altium_move_component",
        "params": {"designator": "U1", "x": 1200, "y": 900, "confirmed": True},
    }, headers=admin)
    audit_id = executed.json()["auditId"]

    failed = await api.post(base + f"/commands/audit/{audit_id}/undo", headers=admin)
    assert failed.status_code == 200
    body = failed.json()
    assert body["ok"] is False and body["undone"] is None and body["error"] == "bridge timeout"

    listing = await api.get(base + "/commands/audit", headers=admin)
    rows = listing.json()
    original = next(r for r in rows if r["id"] == audit_id)
    assert original["status"] == "executed" and original["canUndo"] is True
    assert any(r["status"] == "failed" and r["undoOfId"] == audit_id for r in rows)


async def test_live_drift_endpoint(api, actors, db, monkeypatch):
    alice = actors["alice"]
    project = UploadedProject(
        name="电源板", user_id=str(alice.id), status="ready", current_version=3,
        snapshot={
            "components": [
                {"designator": "U1", "value": "MCU", "footprint": "LQFP"},
                {"designator": "R1", "value": "10k", "footprint": "0603"},
            ],
            "nets": [{"name": "VCC", "count": 4}, {"name": "GND", "count": 6}],
        },
    )
    conn = await _connection(db)
    db.add_all([project, ConnectionGrant(connection_id=conn.id, user_id=alice.id)])
    await db.commit()

    async def command(self, name, params=None):
        if name == "altium_get_schematic_components":
            return {
                "ok": True,
                "items": [
                    {"designator": "U1", "value": "MCU", "footprint": "LQFP32"},
                    {"designator": "C1", "value": "100n", "footprint": "0402"},
                ],
            }
        if name == "altium_get_schematic_nets":
            return {"ok": True, "items": [{"name": "VCC", "count": 4}, {"name": "USB_DP", "count": 2}]}
        return {"ok": False, "error": "unexpected"}

    monkeypatch.setattr(GatewayClient, "command", command)
    url = f"{PREFIX}/altium/connections/{conn.id}/drift?projectId={project.id}"
    response = await api.get(url, headers=auth(alice))
    assert response.status_code == 200
    data = response.json()
    assert data["drifted"] is True and data["snapshotVersion"] == 3 and data["projectName"] == "电源板"
    assert data["components"]["onlyInLive"] == ["C1"]
    assert data["components"]["onlyInSnapshot"] == ["R1"]
    assert data["components"]["changed"] == [
        {"designator": "U1", "fields": {"footprint": {"live": "LQFP32", "snapshot": "LQFP"}}}
    ]
    assert data["nets"]["onlyInLive"] == ["USB_DP"]
    assert data["nets"]["onlyInSnapshot"] == ["GND"]
    assert (await api.get(url, headers=auth(actors["bob"]))).status_code == 404


async def test_conversation_export_and_history_tool_log(api, actors, db):
    alice = actors["alice"]
    conversation = Conversation(user_id=alice.id, title="电源设计评审", message_count=2)
    db.add(conversation)
    await db.flush()
    db.add_all([
        Message(conversation_id=conversation.id, seq=1, role="user", content="检查电源网络"),
        Message(
            conversation_id=conversation.id, seq=2, role="assistant", content="已检查", provider="mock",
            meta={"toolLog": [{"name": "get_live_design_summary", "params": {"connectionId": "x"}, "result": {"success": True}}]},
        ),
    ])
    await db.commit()

    response = await api.get(f"{PREFIX}/ai/conversations/{conversation.id}/export.md", headers=auth(alice))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    text = response.text
    assert "电源设计评审" in text and "检查电源网络" in text and "get_live_design_summary" in text
    assert (await api.get(
        f"{PREFIX}/ai/conversations/{conversation.id}/export.md", headers=auth(actors["bob"])
    )).status_code == 404

    messages = await api.get(f"{PREFIX}/ai/conversations/{conversation.id}/messages", headers=auth(alice))
    assert messages.status_code == 200
    assert messages.json()[1]["toolLog"][0]["name"] == "get_live_design_summary"


async def test_readonly_tools_run_in_parallel_and_persist(api, actors, db, monkeypatch):
    from app.ai_tools import registry
    from app.services.ai import orchestrator

    state = {"a": False, "b": False}

    async def tool_a(**_kwargs):
        state["a"] = True
        for _ in range(100):
            if state["b"]:
                break
            await asyncio.sleep(0.01)
        return {"success": state["b"], "tool": "a"}

    async def tool_b(**_kwargs):
        state["b"] = True
        for _ in range(100):
            if state["a"]:
                break
            await asyncio.sleep(0.01)
        return {"success": state["a"], "tool": "b"}

    registry.register("test_read_a", "test a", "test", tool_a)
    registry.register("test_read_b", "test b", "test", tool_b)
    rounds = 0

    async def provider(*_args, **_kwargs):
        nonlocal rounds
        rounds += 1
        if rounds == 1:
            yield {
                "type": "tool_calls",
                "calls": [
                    {"id": "c1", "name": "test_read_a", "arguments": {}},
                    {"id": "c2", "name": "test_read_b", "arguments": {}},
                ],
            }
        else:
            yield {"type": "delta", "text": "完成"}

    try:
        monkeypatch.setattr(orchestrator.providers, "stream_chat", provider)
        response = await api.post(f"{PREFIX}/ai/chat/stream", headers=auth(actors["alice"]), json={"content": "go"})
        assert response.status_code == 200 and "完成" in response.text
        assert state == {"a": True, "b": True}
        assert response.text.count('"type": "tool_result"') == 2
        row = (
            await db.execute(
                select(Message).where(Message.role == "assistant").order_by(Message.created_at.desc())
            )
        ).scalars().first()
        assert [entry["name"] for entry in row.meta["toolLog"]] == ["test_read_a", "test_read_b"]
        messages = await api.get(
            f"{PREFIX}/ai/conversations/{row.conversation_id}/messages", headers=auth(actors["alice"])
        )
        assert messages.json()[-1]["toolLog"][0]["name"] == "test_read_a"
    finally:
        registry.unregister("test_read_a")
        registry.unregister("test_read_b")


async def test_post_action_verification_flags_silent_failure(api, actors, db, monkeypatch):
    """gateway 返回 ok 但状态未落地时，写后即查必须标记失败；审计仍保持 executed 且可撤销。"""
    conn = await _connection(db)

    async def command(self, name, params=None):
        payload = params or {}
        if payload.get("dry_run"):  # 读回始终是旧位置，模拟「写没生效」
            return {"ok": True, "current": {"designator": "U1", "x": 1000, "y": 800}}
        if name == "altium_move_component":
            return {"ok": True, "designator": "U1", "x": payload.get("x"), "y": payload.get("y")}
        return {"ok": False, "error": "unexpected"}

    monkeypatch.setattr(GatewayClient, "command", command)
    admin = auth(actors["admin"])
    base = f"{PREFIX}/altium/connections/{conn.id}"
    response = await api.post(base + "/command", json={
        "name": "altium_move_component",
        "params": {"designator": "U1", "x": 5000, "y": 6000, "confirmed": True},
    }, headers=admin)
    assert response.status_code == 200
    verification = response.json()["verification"]
    assert verification["checked"] is True and verification["ok"] is False
    assert any("x:" in issue for issue in verification["issues"])

    rows = (await db.execute(select(AltiumCommandAudit))).scalars().all()
    assert rows[0].status == "executed"
    listing = await api.get(base + "/commands/audit", headers=admin)
    assert listing.json()[0]["verifyFailed"] is True and listing.json()[0]["canUndo"] is True


async def test_highlight_is_not_read_back(api, actors, db, monkeypatch):
    conn = await _connection(db)

    async def command(self, name, params=None):
        return {"ok": True, "net": (params or {}).get("net"), "mode": 1}

    monkeypatch.setattr(GatewayClient, "command", command)
    base = f"{PREFIX}/altium/connections/{conn.id}"
    response = await api.post(base + "/command", json={
        "name": "altium_highlight_net",
        "params": {"net": "GND", "confirmed": True},
    }, headers=auth(actors["admin"]))
    verification = response.json()["verification"]
    assert verification["checked"] is False and verification["ok"] is True
    listing = await api.get(base + "/commands/audit", headers=auth(actors["admin"]))
    row = listing.json()[0]
    assert row["verified"] is False and row["verifyFailed"] is False


async def test_failed_verification_is_fed_back_into_next_turn(db, actors):
    """写后核验未通过的记录应回喂到下一轮连接会话的系统上下文，驱动模型自我修正。"""
    from app.services.ai.orchestrator import _append_failed_verifications

    alice = actors["alice"]
    conn = GatewayConnection(name="gw", base_url="http://127.0.0.1:3296", api_token="")
    db.add(conn)
    await db.commit()
    conversation = Conversation(user_id=alice.id, title="t", connection_id=conn.id, message_count=0)
    db.add(conversation)
    await db.flush()
    db.add(AltiumCommandAudit(
        user_id=alice.id, connection_id=conn.id, command="altium_move_component",
        params={"designator": "U1", "x": 5000, "y": 6000}, before={},
        result={"ok": True, "verification": {"checked": True, "ok": False, "issues": ["x: 期望 5000，实际 1000"]}},
        status="executed",
    ))
    await db.commit()

    context = await _append_failed_verifications(db, conversation, "既有上下文")
    assert "写后即查" in context and "altium_move_component" in context and "x: 期望 5000" in context
    assert context.startswith("既有上下文")
