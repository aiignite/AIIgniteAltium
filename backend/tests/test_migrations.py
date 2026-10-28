import json
import sys

import pytest
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.database import Base
from app.models import AIModelConfig, Conversation, UploadedProject, User
from app.models.altium.connection import ConnectionGrant, GatewayConnection
from app.services.system.migrations import adopt_baseline, check_schema_current, migration_config, validate_baseline
from conftest import upgrade

pytestmark = pytest.mark.integration


def baseline():
    return ScriptDirectory.from_config(migration_config()).get_revision("0001_baseline").module.baseline_metadata()


async def test_empty_upgrade_complete_schema_and_constraints(pg_engine):
    async with pg_engine.begin() as conn:
        await conn.run_sync(upgrade)
        await conn.run_sync(check_schema_current)

        def verify(connection):
            inspector = inspect(connection)
            assert set(inspector.get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
            for name, table in Base.metadata.tables.items():
                columns = {c["name"]: c for c in inspector.get_columns(name)}
                assert set(columns) == set(table.c.keys())
                for c in table.c:
                    assert str(c.type.compile(dialect=connection.dialect)) == str(columns[c.name]["type"].compile(dialect=connection.dialect))
                    assert c.nullable == columns[c.name]["nullable"]
            assert set(inspector.get_pk_constraint("alt_connection_grants")["constrained_columns"]) == {"connection_id", "user_id"}
            assert len(inspector.get_foreign_keys("alt_connection_grants")) == 2
            assert len(inspector.get_check_constraints("ai_conversations")) == 1

        await conn.run_sync(verify)
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as db:
        user = User(email="test@example.com", password_hash="unused")
        conn = GatewayConnection(name="test", base_url="http://localhost:3296")
        project = UploadedProject(name="test", user_id="test")
        db.add_all([user, conn, project])
        await db.commit()
        uid, cid, pid = user.id, conn.id, project.id
        db.add(ConnectionGrant(connection_id=cid, user_id=uid))
        await db.commit()
        db.add(ConnectionGrant(connection_id=cid, user_id=uid))
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()
        db.add(Conversation(user_id=uid, project_id=pid, connection_id=cid))
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()
        from uuid import uuid4
        db.add(ConnectionGrant(connection_id=uuid4(), user_id=uid))
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()


async def test_existing_snapshot_backfilled_as_version_one(pg_engine):
    async with pg_engine.begin() as conn:
        await conn.run_sync(lambda c: upgrade(c, "0002_p0_security"))
        await conn.execute(text("""INSERT INTO fls_projects
            (id,name,user_id,status,error,file_names,svg_manifest,design_json_path,parse_duration_ms,remark,is_deleted,snapshot,storage_dir)
            VALUES ('00000000-0000-0000-0000-0000000000aa','legacy','u','ready','','[]','[]','',12,'',false,
                    '{"project": {"name": "legacy"}}'::json,'/tmp/legacy')"""))
        await conn.run_sync(upgrade)
        row = (await conn.execute(text(
            "SELECT version, snapshot FROM fls_snapshots WHERE project_id = '00000000-0000-0000-0000-0000000000aa'"
        ))).one()
        assert row[0] == 1
        payload = row[1] if isinstance(row[1], dict) else json.loads(row[1])
        assert payload["project"]["name"] == "legacy"
        assert await conn.scalar(text(
            "SELECT current_version FROM fls_projects WHERE id = '00000000-0000-0000-0000-0000000000aa'"
        )) == 1


async def test_legacy_baseline_copy_adoption_preserves_plaintext_and_no_grants(pg_engine):
    async with pg_engine.begin() as conn:
        await conn.run_sync(lambda c: baseline().create_all(c))
        await conn.execute(text("""INSERT INTO alt_connections (id,name,base_url,api_token,status,last_error,info,remark,is_deleted)
            VALUES ('00000000-0000-0000-0000-000000000001','legacy','http://localhost:3296','old-token','connected','','{}','',false)"""))
        await conn.run_sync(validate_baseline)
        await conn.run_sync(adopt_baseline)
        await conn.run_sync(check_schema_current)
        assert await conn.scalar(text("SELECT api_token FROM alt_connections")) == "old-token"
        assert await conn.scalar(text("SELECT count(*) FROM alt_connection_grants")) == 0
        assert (await conn.run_sync(lambda c: MigrationContext.configure(c).get_current_revision())) == "0004_review_runs"


@pytest.mark.parametrize("tamper", [    "ALTER TABLE alt_connections DROP COLUMN remark",
    "ALTER TABLE alt_connections ALTER COLUMN api_token TYPE TEXT",
    "ALTER TABLE alt_connections ALTER COLUMN last_error DROP NOT NULL",
    "ALTER TABLE ai_model_configs DROP CONSTRAINT ai_model_configs_name_key",
    "ALTER TABLE ai_conversations DROP CONSTRAINT ai_conversations_user_id_fkey",
    "DROP INDEX ix_sys_users_email",
    "CREATE TABLE extra_table (id integer)",
])
async def test_baseline_adoption_refuses_mismatch(pg_engine, tamper):
    async with pg_engine.begin() as conn:
        await conn.run_sync(lambda c: baseline().create_all(c))
        await conn.execute(text(tamper))
    with pytest.raises(RuntimeError, match="Baseline mismatch"):
        async with pg_engine.begin() as conn:
            await conn.run_sync(adopt_baseline)
    async with pg_engine.connect() as conn:
        assert not await conn.run_sync(lambda c: MigrationContext.configure(c).get_current_heads())
        assert not await conn.run_sync(lambda c: inspect(c).has_table("alt_connection_grants"))


async def test_startup_requires_migration(pg_engine, monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "engine", pg_engine)
    with pytest.raises(RuntimeError, match="alembic upgrade"):
        await main.bootstrap()
    async with pg_engine.connect() as conn:
        assert await conn.run_sync(lambda c: inspect(c).get_table_names()) == []


async def test_bootstrap_existing_admin_not_reset(db, pg_engine, monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "engine", pg_engine)
    monkeypatch.setattr(main, "async_session_maker", async_sessionmaker(pg_engine, expire_on_commit=False))
    monkeypatch.setattr(settings, "admin_email", "existing@example.com")
    monkeypatch.setattr(settings, "admin_password", "admin123456")
    monkeypatch.setattr(settings, "admin_bootstrap_reset_password", False)
    admin = User(email="existing@example.com", password_hash="real-existing-hash", is_admin=True)
    db.add(admin)
    await db.commit()
    await main.bootstrap()
    await db.refresh(admin)
    assert admin.password_hash == "real-existing-hash"
    monkeypatch.setattr(settings, "admin_bootstrap_reset_password", True)
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        await main.bootstrap()
    monkeypatch.setattr(settings, "admin_bootstrap_reset_password", False)
    monkeypatch.setattr(settings, "admin_email", "new@example.com")
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        await main.bootstrap()
    assert not any(name.startswith("altium_monkey") for name in sys.modules)
