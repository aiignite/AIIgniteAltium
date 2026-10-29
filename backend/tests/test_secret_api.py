from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.config import settings
from app.models import AIModelConfig
from app.models.altium.connection import GatewayConnection
from app.services.system.credentials import CredentialError, decrypt_credential, encrypt_credential, migrate_credentials
from conftest import auth

pytestmark = pytest.mark.integration
PREFIX = "/api/v1"


@pytest.mark.parametrize("resource,field,flag,model,column,body,clear_body,empty_token", [
    ("ai/models", "apiKey", "hasKey", AIModelConfig, "api_key_enc", {"name": "secret-model", "provider": "mock"}, {"clearApiKey": True}, ""),
    ("altium/connections", "apiToken", "hasToken", GatewayConnection, "api_token", {"name": "secret-gateway", "baseUrl": "http://127.0.0.1:3296"}, {"apiToken": ""}, None),
])
async def test_secret_contract(api, actors, db, resource, field, flag, model, column, body, clear_body, empty_token, monkeypatch):
    path = PREFIX + "/" + resource
    admin = auth(actors["admin"])
    created = await api.post(path, json={**body, field: "original-secret"}, headers=admin)
    assert created.status_code == 200 and created.json()[flag] is True
    item_id = UUID(created.json()["id"])
    row = await db.get(model, item_id)
    encrypted = getattr(row, column)
    assert decrypt_credential(encrypted) == "original-secret" and encrypted.startswith("enc:v1:")
    item = path + "/" + str(item_id)
    untouched = [body, {**body, field: empty_token}]
    for payload in untouched:
        response = await api.put(item, json=payload, headers=admin)
        assert response.status_code == 200 and response.json()[flag] is True
        await db.refresh(row)
        assert getattr(row, column) == encrypted
    responses = [created, response, await api.get(path, headers=admin)]
    replaced = await api.put(item, json={**body, field: "replacement-secret"}, headers=admin)
    responses.append(replaced)
    await db.refresh(row)
    assert decrypt_credential(getattr(row, column)) == "replacement-secret" and getattr(row, column) != encrypted
    for response in responses:
        for secret in ("original-secret", "replacement-secret", encrypted, "enc:v1:", f'"{field}"'):
            assert secret not in response.text
    invalid = await api.put(item, json={**body, field: {"key": "validation-secret"}}, headers=admin)
    assert invalid.status_code == 422 and "validation-secret" not in invalid.text
    monkeypatch.setattr(settings, "credential_encryption_key", "")
    failed = await api.put(item, json={**body, field: "failed-secret"}, headers=admin)
    assert failed.status_code == 503 and "failed-secret" not in failed.text
    cleared = await api.put(item, json={**body, **clear_body}, headers=admin)
    assert cleared.status_code == 200 and cleared.json()[flag] is False
    await db.refresh(row)
    assert getattr(row, column) == ""
    empty = await api.post(path, json={**body, "name": "empty"}, headers=admin)
    assert empty.status_code == 200 and empty.json()[flag] is False


async def test_credentials_migration_idempotent_and_rollback(db, monkeypatch):
    key = settings.credential_encryption_key
    model = AIModelConfig(name="legacy", provider="openai", api_key="old-plaintext", is_deleted=True)
    conn = GatewayConnection(name="legacy", base_url="http://127.0.0.1:3296", api_token="old-token")
    db.add_all([model, conn])
    await db.commit()
    model_id, conn_id = model.id, conn.id
    assert await migrate_credentials(db) == 2
    first = model.api_key
    assert decrypt_credential(first) == "old-plaintext"
    assert decrypt_credential(conn.api_token) == "old-token"
    assert await migrate_credentials(db) == 0
    assert model.api_key == first
    conn.api_token = "another-plaintext"
    await db.commit()
    monkeypatch.setattr(settings, "credential_encryption_key", Fernet.generate_key().decode())
    with pytest.raises(CredentialError):
        await migrate_credentials(db)
    await db.refresh(model)
    await db.refresh(conn)
    assert model.api_key == first and conn.api_token == "another-plaintext"
    monkeypatch.setattr(settings, "credential_encryption_key", key)
    assert await migrate_credentials(db) == 1
    model.api_key = "yet-another-plaintext"
    conn.api_token = "enc:v1:broken"
    await db.commit()
    with pytest.raises(CredentialError):
        await migrate_credentials(db)
    await db.refresh(model)
    await db.refresh(conn)
    assert model.api_key == "yet-another-plaintext" and conn.api_token == "enc:v1:broken"


async def test_bad_key_preflight_does_not_create_messages(api, actors, db, monkeypatch):
    from sqlalchemy import func
    from app.models import Message, Conversation

    model = AIModelConfig(name="real", provider="openai", base_url="http://127.0.0.1:3296", api_key=encrypt_credential("provider-secret"))
    db.add(model)
    await db.commit()
    monkeypatch.setattr(settings, "credential_encryption_key", Fernet.generate_key().decode())
    response = await api.post(PREFIX + "/ai/chat/stream", headers=auth(actors["alice"]), json={"content": "hi", "modelConfigId": str(model.id)})
    assert response.status_code == 503 and "provider-secret" not in response.text and "enc:v1:" not in response.text
    assert await db.scalar(select(func.count()).select_from(Message)) == 0
    assert await db.scalar(select(func.count()).select_from(Conversation)) == 0


async def test_saving_unapproved_url_and_legacy_error_redaction(api, actors, db):
    admin = auth(actors["admin"])
    for path, body in (("ai/models", {"name": "bad", "provider": "openai", "apiKey": "never-save"}),
                       ("altium/connections", {"name": "bad", "apiToken": "never-save"})):
        response = await api.post(PREFIX + "/" + path, headers=admin, json={**body, "baseUrl": "http://169.254.169.254/private-secret"})
        assert response.status_code == 400
        assert "private-secret" not in response.text and "never-save" not in response.text
    conn = GatewayConnection(name="legacy-error", base_url="http://127.0.0.1:3296", api_token="old-token",
                             last_error="upstream secret full-body", info={"token": "secret"})
    db.add(conn)
    await db.commit()
    response = await api.get(PREFIX + "/altium/connections", headers=admin)
    assert "full-body" not in response.text and "old-token" not in response.text and "secret" not in response.text
