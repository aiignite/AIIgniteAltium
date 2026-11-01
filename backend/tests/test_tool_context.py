"""S0 工具执行上下文 + S1 离线快照查询工具 + 上下文预算裁剪。

覆盖：不存在隐式默认连接、网关工具按连接隔离、快照语义查询的所有者边界、
以及「概览 + 命中项 + 预算」的上下文构建。
"""

from contextlib import asynccontextmanager

import pytest

import app.database
from app.ai_tools import ToolContext, registry, reset_tool_context, set_tool_context, sync_gateway_tools, tool_definitions
from app.models.altium.connection import ConnectionGrant, GatewayConnection
from app.models.files.uploaded_project import UploadedProject
from app.services.ai.design_context import MAX_CONTEXT_CHARS, build_design_context, intent_terms
from app.services.altium.gateway_client import GatewayClient
from conftest import auth

pytestmark = pytest.mark.integration
PREFIX = "/api/v1"

SNAPSHOT = {
    "project": {"name": "主控板"},
    "stats": {"componentCount": 3, "netCount": 3, "bomRowCount": 3},
    "components": [
        {"designator": "U1", "value": "STM32F103", "footprint": "LQFP48"},
        {"designator": "C12", "value": "100n", "footprint": "0402"},
        {"designator": "R7", "value": "", "footprint": ""},
    ],
    "nets": [
        {"name": "VCC_3V3", "terminalCount": 2, "terminals": [
            {"designator": "U1", "pin": "48", "pinName": "VDD", "pinType": "power"},
            {"designator": "C12", "pin": "1", "pinName": "1", "pinType": "passive"}]},
        {"name": "GND", "terminalCount": 2, "terminals": [
            {"designator": "U1", "pin": "8", "pinName": "VSS", "pinType": "power"},
            {"designator": "C12", "pin": "2", "pinName": "2", "pinType": "passive"}]},
        {"name": "SPI_MISO", "terminalCount": 1, "terminals": [{"designator": "U1", "pin": "23", "pinName": "MISO"}]},
    ],
    "bom": [
        {"designator": "U1", "value": "STM32F103", "footprint": "LQFP48", "dnp": False},
        {"designator": "C12", "value": "100n", "footprint": "0402", "dnp": False},
        {"designator": "R7", "value": "", "footprint": "", "dnp": True},
    ],
    "warnings": ["BOM 导出降级"],
}


@pytest.fixture
def shared_db(db, monkeypatch):
    """工具 handler 自带会话工厂，这里把它指向测试事务。"""

    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(app.database, "async_session_maker", session)
    return db


async def _connection(db, name="A", base_url="http://127.0.0.1:3296", status="connected"):
    conn = GatewayConnection(name=name, base_url=base_url, status=status)
    db.add(conn)
    await db.commit()
    return conn


async def _grant(db, conn, user_id):
    db.add(ConnectionGrant(connection_id=conn.id, user_id=user_id))
    await db.commit()


async def _project(db, user_id, name="主控板", snapshot=None):
    project = UploadedProject(name=name, user_id=str(user_id), status="ready", current_version=1,
                              snapshot=snapshot if snapshot is not None else SNAPSHOT)
    db.add(project)
    await db.commit()
    return project


async def test_no_implicit_connection_and_per_connection_scoping(shared_db, actors, monkeypatch):
    alice, admin = actors["alice"], actors["admin"]
    conn_a = await _connection(shared_db, "A")
    conn_b = await _connection(shared_db, "B", "http://localhost:3296")
    await _grant(shared_db, conn_a, alice.id)

    seen: list[str] = []

    async def tools(self):
        return [{"name": "altium_probe", "description": "探测", "category": "query",
                 "requiresConfirmation": False, "paramsSchema": {}}]

    async def command(self, name, params=None):
        seen.append(str(self.base_url))
        return {"ok": True, "command": name}

    monkeypatch.setattr(GatewayClient, "tools", tools)
    monkeypatch.setattr(GatewayClient, "command", command)
    try:
        assert await sync_gateway_tools(ToolContext(user_id=alice.id, connection_id=conn_a.id)) == 1
        ctx_a = ToolContext(user_id=alice.id, connection_id=conn_a.id)
        assert "altium_probe" in {d["function"]["name"] for d in tool_definitions(ctx_a)}

        # 其他连接的会话看不到这个工具（工具目录不会跨连接串用）
        ctx_b = ToolContext(user_id=admin.id, connection_id=conn_b.id)
        assert "altium_probe" not in {d["function"]["name"] for d in tool_definitions(ctx_b)}

        token = set_tool_context(ctx_a)
        try:
            executed = await registry.execute("altium_probe")
            assert executed["success"] is True
            assert seen == ["http://127.0.0.1:3296"]

            # 未关联连接的会话：拒绝执行，而不是挑一条在线连接
            stray = set_tool_context(ToolContext(user_id=alice.id))
            try:
                blocked = await registry.execute("altium_probe")
            finally:
                reset_tool_context(stray)
            assert blocked["success"] is False and "未关联" in blocked["error"]
        finally:
            reset_tool_context(token)
    finally:
        registry.drop_connection(conn_a.id)
        registry.drop_connection(conn_b.id)


async def test_sync_replaces_stale_gateway_tools(shared_db, actors, monkeypatch):
    alice = actors["admin"]
    conn = GatewayConnection(name="A", base_url="http://127.0.0.1:3296", status="connected")
    shared_db.add(conn)
    await shared_db.commit()
    ctx = ToolContext(user_id=alice.id, connection_id=conn.id)

    def tools_with(*names):
        async def tools(self):
            return [{"name": n, "description": n, "category": "query", "requiresConfirmation": False} for n in names]
        return tools

    monkeypatch.setattr(GatewayClient, "tools", tools_with("altium_alpha"))
    try:
        await sync_gateway_tools(ctx)
        assert registry.get("altium_alpha") is not None
        monkeypatch.setattr(GatewayClient, "tools", tools_with("altium_beta"))
        await sync_gateway_tools(ctx)
        assert registry.get("altium_alpha") is None
        assert registry.get("altium_beta") is not None
    finally:
        registry.drop_connection(conn.id)


async def test_design_query_tools_are_project_scoped(shared_db, actors):
    alice, bob = actors["alice"], actors["bob"]
    project = await _project(shared_db, alice.id)
    foreign = await _project(shared_db, bob.id, name="别人的板子")

    async def run(context, tool, **params):
        token = set_tool_context(context)
        try:
            return await registry.execute(tool, **params)
        finally:
            reset_tool_context(token)

    ctx = ToolContext(user_id=alice.id, project_id=project.id)

    found = await run(ctx, "find_components", designator="C")
    assert found["success"] is True and [i["designator"] for i in found["items"]] == ["C12"]

    incomplete = await run(ctx, "find_components", missing_footprint=True)
    assert [i["designator"] for i in incomplete["items"]] == ["R7"]

    one_pin = await run(ctx, "find_nets", max_terminals=1)
    assert [i["name"] for i in one_pin["items"]] == ["SPI_MISO"]

    net = await run(ctx, "get_net", name="vcc_3v3")
    assert net["success"] is True and net["terminalCount"] == 2
    assert {t["designator"] for t in net["terminals"]} == {"U1", "C12"}

    missing_net = await run(ctx, "get_net", name="VCC_1V8")
    assert missing_net["success"] is False and "VCC_3V3" in missing_net["error"]

    component = await run(ctx, "get_component", designator="C12")
    assert component["success"] is True
    assert {c["net"] for c in component["connections"]} == {"VCC_3V3", "GND"}
    assert component["bomRow"]["footprint"] == "0402"

    dnp = await run(ctx, "get_bom_rows", dnp_only=True)
    assert [i["designator"] for i in dnp["items"]] == ["R7"]

    findings = await run(ctx, "get_review_findings", rule="missing_footprint")
    assert findings["success"] is True and findings["source"] == "computed"
    assert findings["items"][0]["refs"] == ["R7"]

    # 边界：未关联工程 / 越权工程 / 模型伪造参数
    assert (await run(ToolContext(user_id=alice.id), "find_components"))["success"] is False
    overreaching = await run(ToolContext(user_id=alice.id, project_id=foreign.id), "find_components")
    assert overreaching["success"] is False
    assert "工程" in overreaching["error"]
    spoofed = await run(ctx, "find_components", projectId=str(foreign.id), designator="U")
    assert spoofed["success"] is True and [i["designator"] for i in spoofed["items"]] == ["U1"]


async def test_registry_endpoint_lists_only_visible_connections(api, actors, shared_db, monkeypatch):
    alice = actors["alice"]
    conn = await _connection(shared_db, "A")
    other = await _connection(shared_db, "B", "http://localhost:3296")
    await _grant(shared_db, conn, alice.id)

    async def tools(self):
        return [{"name": "altium_only_here", "description": "d", "category": "query",
                 "requiresConfirmation": False}]

    monkeypatch.setattr(GatewayClient, "tools", tools)
    try:
        listed = await api.get(f"{PREFIX}/ai/tools/registry", params={"connectionId": str(conn.id)}, headers=auth(alice))
        assert listed.status_code == 200
        names = {t["name"] for t in listed.json()}
        assert "altium_only_here" in names and "find_components" in names

        denied = await api.get(f"{PREFIX}/ai/tools/registry", params={"connectionId": str(other.id)}, headers=auth(alice))
        assert denied.status_code == 200
        assert "altium_only_here" not in {t["name"] for t in denied.json()}

        payload = await api.post(f"{PREFIX}/ai/chat/stream", headers=auth(alice), json={
            "content": "列出所有元件", "connection_id": str(conn.id),
        })
        assert payload.status_code == 200
    finally:
        registry.drop_connection(conn.id)
        registry.drop_connection(other.id)


def test_intent_terms_and_context_budget():
    designators, words = intent_terms("C12 与 VCC_3V3 的连接是否合理？")
    assert "C12" in designators and "VCC_3V3" in words

    big = {
        "project": {"name": "大板"},
        "stats": {"componentCount": 600, "netCount": 600, "bomRowCount": 600},
        "components": [{"designator": f"R{i}", "value": f"{i}k", "footprint": "0402"} for i in range(600)],
        "nets": [{"name": f"NET{i}", "terminalCount": 2} for i in range(600)],
        "bom": [{"designator": f"R{i}", "value": f"{i}k", "footprint": "0402"} for i in range(600)],
    }
    context = build_design_context(big, query="R42 的阻值", max_chars=4000)
    assert len(context) <= 4000
    assert "R42" in context
    assert "R43" not in context  # 只注入命中项，不做全量倾倒
    assert "find_components" in context


def test_context_falls_back_to_overview_without_query():
    context = build_design_context(SNAPSHOT)
    assert "主控板" in context and "U1" in context and "可疑单端网络(1): SPI_MISO" in context
    assert "BOM（前 3 行）" in context
