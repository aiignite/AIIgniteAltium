import json
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app.models import AIModelConfig, AIAssistant, AISkill, Conversation, Message, UploadedProject
from app.models.altium.connection import ConnectionGrant, GatewayConnection
from app.services.ai import llm_router, orchestrator
from app.services.altium.gateway_client import GatewayClient
from conftest import auth

pytestmark = pytest.mark.integration
PREFIX = "/api/v1"


async def test_inactive_old_jwt(api, actors):
    response = await api.get(PREFIX + "/auth/me", headers=auth(actors["inactive"]))
    assert response.status_code == 401
    assert (await api.get(PREFIX + "/auth/users/options", headers=auth(actors["alice"]))).status_code == 403
    options = await api.get(PREFIX + "/auth/users/options", headers=auth(actors["admin"]))
    assert options.status_code == 200 and len(options.json()) == 3
    assert all(set(u) == {"id", "email", "displayName"} for u in options.json())


@pytest.mark.parametrize("resource,body", [
    ("models", {"name": "new", "provider": "mock"}),
    ("assistants", {"name": "new"}),
    ("skills", {"code": "new", "name": "new"}),
])
async def test_admin_writes_and_user_reads(api, actors, resource, body):
    path = PREFIX + "/ai/" + resource
    assert (await api.get(path, headers=auth(actors["alice"]))).status_code == 200
    assert (await api.post(path, headers=auth(actors["alice"]), json=body)).status_code == 403
    created = await api.post(path, headers=auth(actors["admin"]), json=body)
    assert created.status_code == 200
    item = path + "/" + created.json()["id"]
    for method in ("put", "delete"):
        kwargs = {"json": body} if method == "put" else {}
        assert (await api.request(method, item, headers=auth(actors["alice"]), **kwargs)).status_code == 403
    if resource == "assistants":
        assert (await api.post(item + "/default", headers=auth(actors["alice"]))).status_code == 403
        assert (await api.post(item + "/default", headers=auth(actors["admin"]))).status_code == 200
    assert (await api.put(item, headers=auth(actors["admin"]), json=body)).status_code == 200
    assert (await api.delete(item, headers=auth(actors["admin"]))).status_code == 200


async def test_private_resources_preflight_no_side_effects(api, actors, db, monkeypatch):
    project = UploadedProject(name="private", user_id=str(actors["alice"].id), snapshot={"project": {"name": "private-secret"}})
    db.add(project)
    await db.flush()
    conv = Conversation(user_id=actors["alice"].id, project_id=project.id)
    db.add(conv)
    await db.commit()
    provider = AsyncMock(side_effect=AssertionError("must not call provider"))
    monkeypatch.setattr(orchestrator.providers, "stream_chat", provider)
    gateway = AsyncMock(side_effect=AssertionError("must not call gateway"))
    monkeypatch.setattr(GatewayClient, "live_summary", gateway)
    ids = (project.id, conv.id)
    for actor in ("bob", "admin"):
        for body in ({"projectId": str(ids[0])}, {"conversationId": str(ids[1])}):
            response = await api.post(PREFIX + "/ai/chat/stream", headers=auth(actors[actor]), json={"content": "hi", **body})
            assert response.status_code == 404
            assert response.headers["content-type"].startswith("application/json")
        assert (await api.get(PREFIX + f"/ai/conversations/{ids[1]}/messages", headers=auth(actors[actor]))).status_code == 404
        events = [e async for e in orchestrator.stream_reply(db, user_id=actors[actor].id, content="hi", conversation_id=ids[1], project_id=None)]
        assert events[0]["type"] == "error"
    assert (await db.scalar(select(func.count()).select_from(Message))) == 0
    assert (await db.scalar(select(func.count()).select_from(Conversation))) == 1
    provider.assert_not_called()
    gateway.assert_not_called()


async def test_source_switch_cannot_bypass_old_project(api, actors, db):
    owned = UploadedProject(name="own", user_id=str(actors["alice"].id))
    other = UploadedProject(name="other", user_id=str(actors["bob"].id))
    db.add_all([owned, other])
    await db.flush()
    conv = Conversation(user_id=actors["alice"].id, project_id=other.id)
    db.add(conv)
    await db.commit()
    response = await api.post(PREFIX + "/ai/chat/stream", headers=auth(actors["alice"]),
                              json={"content": "hi", "conversationId": str(conv.id), "projectId": str(owned.id)})
    assert response.status_code == 404
    conv.project_id = owned.id
    await db.commit()
    another = UploadedProject(name="own2", user_id=str(actors["alice"].id))
    db.add(another)
    await db.commit()
    response = await api.post(PREFIX + "/ai/chat/stream", headers=auth(actors["alice"]),
                              json={"content": "hi", "conversationId": str(conv.id), "projectId": str(another.id)})
    assert response.status_code == 409


async def test_connections_grants_revocation_and_binding(api, actors, db, monkeypatch):
    path = PREFIX + "/altium/connections"
    body = {"name": "gateway", "baseUrl": "http://127.0.0.1:3296", "apiToken": "secret"}
    assert (await api.post(path, json=body, headers=auth(actors["alice"]))).status_code == 403
    created = await api.post(path, json=body, headers=auth(actors["admin"]))
    assert created.status_code == 200
    cid = created.json()["id"]
    item = path + "/" + cid
    assert (await api.get(path, headers=auth(actors["alice"]))).json() == []
    assert (await api.put(item, json=body, headers=auth(actors["alice"]))).status_code == 403
    assert (await api.delete(item, headers=auth(actors["alice"]))).status_code == 403
    for suffix, method in (("/test", "post"), ("/live/summary", "get"), ("/screenshot", "get")):
        assert (await api.request(method, item + suffix, headers=auth(actors["alice"]))).status_code == 404
    for method in ("get", "put"):
        kwargs = {"json": {"userIds": []}} if method == "put" else {}
        assert (await api.request(method, item + "/grants", headers=auth(actors["alice"]), **kwargs)).status_code == 403
    assert (await api.put(item + "/grants", json={"userIds": [str(actors["inactive"].id)]}, headers=auth(actors["admin"]))).status_code == 400
    grants = await api.put(item + "/grants", json={"userIds": [str(actors["alice"].id)] * 2}, headers=auth(actors["admin"]))
    assert grants.json() == {"connectionId": cid, "userIds": [str(actors["alice"].id)]}
    assert (await api.get(item + "/grants", headers=auth(actors["admin"]))).json() == grants.json()
    assert len((await api.get(path, headers=auth(actors["alice"]))).json()) == 1
    assert (await api.get(path, headers=auth(actors["bob"]))).json() == []
    monkeypatch.setattr(GatewayClient, "health", AsyncMock(return_value={"altiumOnline": True, "mode": "live"}))
    summary = AsyncMock(return_value={"ok": True, "project": "live-board"})
    monkeypatch.setattr(GatewayClient, "live_summary", summary)
    monkeypatch.setattr(GatewayClient, "screenshot", AsyncMock(return_value=(b"image", "image/png")))
    for suffix, method in (("/test", "post"), ("/live/summary", "get"), ("/screenshot", "get")):
        assert (await api.request(method, item + suffix, headers=auth(actors["alice"]))).status_code == 200
    result = await api.post(PREFIX + "/ai/chat/stream", headers=auth(actors["alice"]), json={"content": "hi", "connectionId": cid})
    assert result.status_code == 200 and "live-board" in result.text
    events = [json.loads(line[6:]) for line in result.text.splitlines() if line.startswith("data: ")]
    conv_id = events[0]["conversationId"]
    restored = (await api.get(PREFIX + "/ai/conversations", headers=auth(actors["alice"]))).json()[0]
    assert restored["connectionId"] == cid and restored["projectId"] is None
    await api.put(item + "/grants", json={"userIds": []}, headers=auth(actors["admin"]))
    alternate = GatewayConnection(name="alternate", base_url="http://127.0.0.1:3296")
    own_project = UploadedProject(name="own", user_id=str(actors["alice"].id))
    db.add_all([alternate, own_project])
    await db.flush()
    db.add(ConnectionGrant(connection_id=alternate.id, user_id=actors["alice"].id))
    await db.commit()
    summary.reset_mock()
    for body in ({"connectionId": cid}, {"conversationId": conv_id},
                 {"conversationId": conv_id, "connectionId": str(alternate.id)},
                 {"conversationId": conv_id, "projectId": str(own_project.id)}):
        denied = await api.post(PREFIX + "/ai/chat/stream", headers=auth(actors["alice"]), json={"content": "hi", **body})
        assert denied.status_code == 404
    assert (await api.get(PREFIX + f"/ai/conversations/{conv_id}/messages", headers=auth(actors["alice"]))).status_code == 404
    summary.assert_not_called()
    assert (await api.get(item + "/live/summary", headers=auth(actors["admin"]))).status_code == 200
    both = await api.post(PREFIX + "/ai/chat/stream", headers=auth(actors["alice"]),
                          json={"content": "hi", "projectId": str(own_project.id), "connectionId": str(alternate.id)})
    assert both.status_code == 422


async def test_no_implicit_connection_and_model_preflight(api, actors, db, monkeypatch):
    conn = GatewayConnection(name="global", base_url="http://127.0.0.1:3296", status="connected")
    db.add(conn)
    await db.commit()
    summary = AsyncMock(side_effect=AssertionError("No implicit live context"))
    monkeypatch.setattr(GatewayClient, "live_summary", summary)
    response = await api.post(PREFIX + "/ai/chat/stream", headers=auth(actors["alice"]), json={"content": "hi"})
    assert response.status_code == 200 and "未关联设计" in response.text
    summary.assert_not_called()
    removed_path = PREFIX + "/altium/connections/first-connected"
    # Dynamic PUT/DELETE routes can yield 405 for the removed GET route.
    assert (await api.get(removed_path, headers=auth(actors["admin"]))).status_code in (404, 405)
    openapi = await api.get("/openapi.json", headers=auth(actors["admin"]))
    assert openapi.status_code == 200
    assert removed_path not in openapi.json()["paths"]
    before = await db.scalar(select(func.count()).select_from(Conversation))
    actors["model"].enabled = False
    await db.commit()
    for model_id in (None, str(actors["model"].id), str(uuid4())):
        response = await api.post(PREFIX + "/ai/chat/stream", headers=auth(actors["alice"]), json={"content": "hi", "modelConfigId": model_id})
        assert response.status_code == 200
        assert "no_model" in response.text
    assert await db.scalar(select(func.count()).select_from(Conversation)) == before
    enabled = AIModelConfig(name="enabled", provider="mock", enabled=True)
    db.add(enabled)
    await db.commit()
    assert (await llm_router.resolve(db, model_config_id=None)).config_id == str(enabled.id)


async def test_system_reaches_provider_from_orchestrator(api, actors, db, monkeypatch):
    assistant = AIAssistant(name="custom", system_prompt="persona-marker")
    skill = AISkill(code="test", name="test", prompt_template="skill-marker")
    project = UploadedProject(name="design", user_id=str(actors["alice"].id), snapshot={"project": {"name": "design-marker"}})
    db.add_all([assistant, skill, project])
    await db.commit()
    captured = []

    async def provider(*args, **kwargs):
        captured.append(kwargs)
        yield "ok"

    monkeypatch.setattr(orchestrator.providers, "stream_chat", provider)
    response = await api.post(PREFIX + "/ai/chat/stream", headers=auth(actors["alice"]), json={
        "content": "hi", "assistantId": str(assistant.id), "skills": ["test"], "projectId": str(project.id)})
    assert response.status_code == 200
    system = captured[0]["messages"][0]
    assert system["role"] == "system"
    for marker in ("persona-marker", "skill-marker", "design-marker"):
        assert marker in system["content"]


async def test_tool_has_no_url_fallback(db, actors, monkeypatch):
    from app.ai_tools import get_live_design_summary, registry
    import app.database
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(app.database, "async_session_maker", session)
    conn = GatewayConnection(name="gateway", base_url="http://127.0.0.1:3296")
    db.add(conn)
    await db.commit()
    summary = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(GatewayClient, "live_summary", summary)
    denied = await registry.execute("get_live_design_summary", user_id=str(actors["alice"].id), connection_id=str(conn.id))
    assert denied["success"] is False
    arbitrary = await registry.execute("get_live_design_summary", base_url="http://127.0.0.1", token="secret")
    assert arbitrary["success"] is False
    summary.assert_not_called()
    allowed = await get_live_design_summary(user_id=str(actors["admin"].id), connection_id=str(conn.id))
    assert allowed["success"] is True
