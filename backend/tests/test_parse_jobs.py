import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.models import ParseJob, SnapshotVersion, UploadedProject
from app.services.files import jobs, parse_service
from conftest import auth

PREFIX = "/api/v1"
SNAPSHOT = {
    "schema": "aidrive.snapshot.v0",
    "project": {"name": "demo"},
    "stats": {"components": 2},
    "pcbs": [{"outlineRectMils": [100, 200, 1895, 1125]}],
}


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    return tmp_path


@pytest.fixture
def factory(db):
    return async_sessionmaker(db.bind, expire_on_commit=False)


async def upload(api, actor, snapshot=None, filename="demo.snapshot.json", content_type="application/json"):
    payload = json.dumps(snapshot or SNAPSHOT).encode()
    response = await api.post(
        PREFIX + "/files/projects",
        headers=auth(actor),
        data={"name": "demo"},
        files={"files": (filename, payload, content_type)},
    )
    return response


async def test_upload_enqueues_single_durable_job(api, actors, db):
    response = await upload(api, actors["alice"])
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "parsing"
    assert body["currentVersion"] == 0
    project_id = body["id"]

    job = await db.scalar(select(ParseJob).where(ParseJob.project_id == project_id))
    assert job is not None and job.status == "queued" and job.attempt == 0

    again, created = await jobs.enqueue_parse(db, job.project_id)
    await db.commit()
    assert created is False and again.id == job.id
    assert (await db.scalar(select(func.count()).select_from(ParseJob))) == 1


async def test_worker_creates_immutable_versions(api, actors, db, factory):
    created = (await upload(api, actors["alice"])).json()
    project_id = created["id"]

    assert await jobs.process_next(factory, parse_service.run_parse_job) is True
    await db.commit()

    project = await db.get(UploadedProject, project_id)
    await db.refresh(project)
    assert project.status == "ready"
    assert project.current_version == 1
    assert project.snapshot == SNAPSHOT

    versions = await api.get(PREFIX + f"/files/projects/{project_id}/versions", headers=auth(actors["alice"]))
    assert versions.status_code == 200
    assert [v["version"] for v in versions.json()] == [1]

    detail = await api.get(PREFIX + f"/files/projects/{project_id}/versions/1", headers=auth(actors["alice"]))
    assert detail.status_code == 200 and detail.json()["snapshot"] == SNAPSHOT

    # 重新上传新内容后重新解析：新增版本，旧版本快照保持不变
    new_snapshot = {**SNAPSHOT, "project": {"name": "demo-v2"}, "stats": {"components": 3}}
    (parse_service.project_upload_dir(project.id) / "demo.snapshot.json").write_text(json.dumps(new_snapshot))
    reparse = await api.post(PREFIX + f"/files/projects/{project_id}/reparse", headers=auth(actors["alice"]))
    assert reparse.status_code == 200 and reparse.json()["currentVersion"] == 1
    assert await jobs.process_next(factory, parse_service.run_parse_job) is True
    await db.refresh(project)
    assert project.current_version == 2 and project.snapshot["project"]["name"] == "demo-v2"

    old = await api.get(PREFIX + f"/files/projects/{project_id}/versions/1", headers=auth(actors["alice"]))
    assert old.json()["snapshot"]["project"]["name"] == "demo"
    versions = await api.get(PREFIX + f"/files/projects/{project_id}/versions", headers=auth(actors["alice"]))
    assert [v["version"] for v in versions.json()] == [2, 1]


async def test_reparse_conflicts_while_job_active(api, actors, db):
    project_id = (await upload(api, actors["alice"])).json()["id"]
    response = await api.post(PREFIX + f"/files/projects/{project_id}/reparse", headers=auth(actors["alice"]))
    assert response.status_code == 409


async def test_failed_parse_records_job_and_project_error(api, actors, db, factory, monkeypatch):
    project_id = (await upload(api, actors["alice"], filename="demo.PcbDoc",
                               content_type="application/octet-stream")).json()["id"]
    monkeypatch.setattr(parse_service, "run_parse", lambda *a, **kw: {"ok": False, "error": "bad board"})
    assert await jobs.process_next(factory, parse_service.run_parse_job) is True
    project = await db.get(UploadedProject, project_id)
    await db.refresh(project)
    assert project.status == "failed" and project.error == "bad board"
    job = await db.scalar(select(ParseJob).where(ParseJob.project_id == project_id))
    await db.refresh(job)
    assert job.status == "failed" and job.error == "bad board"
    assert (await db.scalar(select(func.count()).select_from(SnapshotVersion))) == 0


async def test_orphaned_running_job_is_requeued_after_crash(api, actors, db, factory):
    project_id = (await upload(api, actors["alice"])).json()["id"]
    job = await db.scalar(select(ParseJob).where(ParseJob.project_id == project_id))
    job.status = "running"
    job.attempt = 1
    job.started_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await db.commit()

    assert await jobs.requeue_orphans(db, stale_after_seconds=60) == 1
    await db.refresh(job)
    assert job.status == "queued" and job.started_at is None

    assert await jobs.process_next(factory, parse_service.run_parse_job) is True
    await db.refresh(job)
    assert job.status == "succeeded" and job.attempt == 2


async def test_recent_running_job_not_stolen(api, actors, db):
    project_id = (await upload(api, actors["alice"])).json()["id"]
    job = await db.scalar(select(ParseJob).where(ParseJob.project_id == project_id))
    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    await db.commit()
    assert await jobs.requeue_orphans(db, stale_after_seconds=600) == 0


async def test_versions_are_owner_only(api, actors):
    project_id = (await upload(api, actors["alice"])).json()["id"]
    for actor in ("bob", "admin"):
        assert (await api.get(PREFIX + f"/files/projects/{project_id}/versions", headers=auth(actors[actor]))).status_code == 404
        assert (await api.get(PREFIX + f"/files/projects/{project_id}/versions/1", headers=auth(actors[actor]))).status_code == 404
    missing = await api.get(PREFIX + f"/files/projects/{project_id}/versions/9", headers=auth(actors["alice"]))
    assert missing.status_code == 404
