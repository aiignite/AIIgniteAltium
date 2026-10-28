import os
from uuid import uuid4

os.environ["DATABASE_URL"] = "postgresql+asyncpg://unused:unused@127.0.0.1:1/never_connect"
os.environ["SECRET_KEY"] = "p0-tests-only-jwt-key-not-for-production"
os.environ["ADMIN_PASSWORD"] = "p0-tests-only-admin-password"
os.environ["CREDENTIAL_ENCRYPTION_KEY"] = ""

import httpx
import pytest
import pytest_asyncio
from alembic import command
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import get_db
from app.main import create_app
from app.models import AIModelConfig, User
from app.security import create_access_token
from app.services.system.migrations import migration_config


@pytest.fixture(autouse=True)
def secure_settings(monkeypatch):
    monkeypatch.setattr(settings, "secret_key", "p0-tests-only-jwt-key-not-for-production")
    monkeypatch.setattr(settings, "credential_encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "outbound_allowed_urls", ["http://127.0.0.1:3296", "http://localhost:3296", "http://[::1]:3296", "https://api.openai.com/v1", "https://api.anthropic.com"])
    original = httpx.AsyncClient

    def client(*args, **kwargs):
        if "transport" not in kwargs:
            raise AssertionError("Tests must mock outbound HTTP; no real network requests")
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)


@pytest_asyncio.fixture
async def pg_engine():
    value = os.environ.get("TEST_DATABASE_URL")
    if not value:
        pytest.fail("Set TEST_DATABASE_URL explicitly to an isolated local PostgreSQL database whose name contains 'test'")
    url = make_url(value)
    if url.drivername != "postgresql+asyncpg" or url.host not in {"127.0.0.1", "localhost", "::1"} or "test" not in (url.database or "").lower():
        pytest.fail("TEST_DATABASE_URL must be a local, isolated PostgreSQL+asyncpg test database (name contains 'test')")
    schema = "p0_test_" + uuid4().hex
    admin_engine = create_async_engine(value, poolclass=NullPool, hide_parameters=True)
    async with admin_engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(value, poolclass=NullPool, hide_parameters=True,
                                 connect_args={"server_settings": {"search_path": schema}})
    try:
        yield engine
    finally:
        await engine.dispose()
        async with admin_engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin_engine.dispose()


def upgrade(connection, revision="head"):
    config = migration_config()
    config.attributes["connection"] = connection
    command.upgrade(config, revision)


@pytest_asyncio.fixture
async def db(pg_engine):
    async with pg_engine.begin() as conn:
        await conn.run_sync(upgrade)
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def actors(db):
    users = [User(email=f"{name}@example.com", display_name=name, password_hash="unused", is_admin=name == "admin", is_active=name != "inactive")
             for name in ("admin", "alice", "bob", "inactive")]
    db.add_all(users)
    model = AIModelConfig(name="mock", provider="mock", is_default=True)
    db.add(model)
    await db.commit()
    for user in users:
        db.expunge(user)
    return {**{u.display_name: u for u in users}, "model": model}


@pytest_asyncio.fixture
async def api(db):
    app = create_app()

    async def session():
        async with async_sessionmaker(db.bind, expire_on_commit=False)() as request_db:
            yield request_db

    app.dependency_overrides[get_db] = session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


def auth(user):
    return {"Authorization": "Bearer " + create_access_token(user.id)}
