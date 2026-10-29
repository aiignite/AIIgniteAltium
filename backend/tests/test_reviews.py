import json

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.services.files import jobs, parse_service
from conftest import auth

PREFIX = "/api/v1"
SNAPSHOT = {
    "schema": "aidrive.snapshot.v0",
    "project": {"name": "review"},
    "stats": {"componentCount": 3, "netCount": 2, "bomRowCount": 1},
    "components": [
        {"designator": "R1", "value": "10k", "footprint": ""},
        {"designator": "R1", "value": "", "footprint": "R0603"},
        {"designator": "C1", "value": "100nF", "footprint": "C0603"},
    ],
    "nets": [{"name": "N$1", "terminalCount": 1}, {"name": "GND", "terminals": [1, 2, 3]}],
    "bom": [{"designator": "R1", "value": "10k", "footprint": "R0603", "dnp": True}],
    "pcbs": [
        {"name": "Board1", "board": {}},
        {"name": "Board2", "board": {"outlineRectMils": [0, 0, 0, 0]}},
    ],
    "warnings": ["原理图渲染降级"],
}
EXPECTED_RULES = {
    "duplicate_designator",
    "missing_footprint",
    "missing_value",
    "bom_missing_row",
    "single_terminal_net",
    "net_auto_named",
    "dnp_bom_rows",
    "parse_warnings",
    "board_outline_missing",
    "board_outline_invalid",
}


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    return tmp_path


@pytest.fixture
def factory(db):
    return async_sessionmaker(db.bind, expire_on_commit=False)


async def create_project(api, actor, snapshot=None):
    response = await api.post(
        PREFIX + "/files/projects",
        headers=auth(actor),
        data={"name": "demo"},
        files={"files": ("demo.snapshot.json", json.dumps(snapshot or SNAPSHOT).encode(), "application/json")},
    )
    assert response.status_code == 200
    return response.json()["id"]


async def test_review_requires_ready_snapshot(api, actors):
    project_id = await create_project(api, actors["alice"])
    response = await api.post(PREFIX + f"/files/projects/{project_id}/reviews", headers=auth(actors["alice"]))
    assert response.status_code == 409


async def test_review_findings_are_deterministic_and_versioned(api, actors, db, factory):
    project_id = await create_project(api, actors["alice"])
    assert await jobs.process_next(factory, parse_service.run_parse_job) is True

    first = await api.post(PREFIX + f"/files/projects/{project_id}/reviews", headers=auth(actors["alice"]))
    assert first.status_code == 200
    body = first.json()
    assert body["snapshotVersion"] == 1
    assert body["rulesetVersion"] == "p2.0"
    assert body["counts"] == {"error": 2, "warning": 5, "info": 3}
    assert {f["rule"] for f in body["findings"]} == EXPECTED_RULES
    assert [f["severity"] for f in body["findings"]].index("error") == 0
    findings = {f["rule"]: f for f in body["findings"]}
    assert findings["bom_missing_row"]["refs"] == ["C1"]
    assert findings["net_auto_named"]["refs"] == ["N$1"]

    second = await api.post(PREFIX + f"/files/projects/{project_id}/reviews", headers=auth(actors["alice"]))
    assert second.json()["findings"] == body["findings"]

    listing = await api.get(PREFIX + f"/files/projects/{project_id}/reviews", headers=auth(actors["alice"]))
    assert listing.status_code == 200 and len(listing.json()) == 2
    detail = await api.get(PREFIX + f"/files/projects/{project_id}/reviews/{body['id']}", headers=auth(actors["alice"]))
    assert detail.json()["findings"] == body["findings"]

    updated = {**SNAPSHOT, "components": [{"designator": "U1", "value": "MCU", "footprint": "QFP48"}],
               "nets": [{"name": "GND", "terminals": [1, 2]}],
               "bom": [{"designator": "U1", "value": "MCU", "footprint": "QFP48", "dnp": False}],
               "pcbs": [], "warnings": []}
    (parse_service.project_upload_dir(project_id) / "demo.snapshot.json").write_text(json.dumps(updated))
    assert (await api.post(PREFIX + f"/files/projects/{project_id}/reparse", headers=auth(actors["alice"]))).status_code == 200
    assert await jobs.process_next(factory, parse_service.run_parse_job) is True

    third = await api.post(PREFIX + f"/files/projects/{project_id}/reviews", headers=auth(actors["alice"]))
    assert third.status_code == 200
    assert third.json()["snapshotVersion"] == 2
    assert third.json()["findings"] == []


async def test_review_report_markdown(api, actors, db, factory):
    project_id = await create_project(api, actors["alice"])
    assert await jobs.process_next(factory, parse_service.run_parse_job) is True
    run = (await api.post(PREFIX + f"/files/projects/{project_id}/reviews", headers=auth(actors["alice"]))).json()

    url = PREFIX + f"/files/projects/{project_id}/reviews/{run['id']}/report.md"
    response = await api.get(url, headers=auth(actors["alice"]))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    text = response.content.decode("utf-8")
    assert text.startswith("# demo 设计审查报告")
    assert "快照版本：v1" in text
    assert "规则集：p2.0" in text
    assert "结论：错误 2、警告 5、提示 3" in text
    assert "duplicate_designator" in text and "位号重复" in text

    for actor in ("bob", "admin"):
        assert (await api.get(url, headers=auth(actors[actor]))).status_code == 404
    assert (await api.get(url)).status_code == 401


async def test_reviews_are_owner_only(api, actors, db, factory):
    project_id = await create_project(api, actors["alice"])
    assert await jobs.process_next(factory, parse_service.run_parse_job) is True
    run = (await api.post(PREFIX + f"/files/projects/{project_id}/reviews", headers=auth(actors["alice"]))).json()
    for actor in ("bob", "admin"):
        assert (await api.post(PREFIX + f"/files/projects/{project_id}/reviews", headers=auth(actors[actor]))).status_code == 404
        assert (await api.get(PREFIX + f"/files/projects/{project_id}/reviews", headers=auth(actors[actor]))).status_code == 404
        assert (await api.get(
            PREFIX + f"/files/projects/{project_id}/reviews/{run['id']}", headers=auth(actors[actor])
        )).status_code == 404
