import json

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.services.files import jobs, parse_service
from conftest import auth

PREFIX = "/api/v1"
V1 = {
    "schema": "aidrive.snapshot.v0",
    "stats": {"componentCount": 2, "netCount": 2, "bomRowCount": 2},
    "components": [
        {"designator": "R1", "value": "10k", "footprint": "0603", "description": "resistor", "sheet": "S1"},
        {"designator": "C1", "value": "100nF", "footprint": "0603", "description": "cap", "sheet": "S1"},
    ],
    "nets": [
        {"name": "VCC", "terminalCount": 2, "terminals": [
            {"designator": "R1", "pin": "1"}, {"designator": "C1", "pin": "1"}]},
        {"name": "GND", "terminalCount": 2, "terminals": [
            {"designator": "R1", "pin": "2"}, {"designator": "C1", "pin": "2"}]},
    ],
    "bom": [
        {"designator": "R1", "value": "10k", "footprint": "0603", "dnp": False},
        {"designator": "C1", "value": "100nF", "footprint": "0603", "dnp": False},
    ],
    "pcbs": [{"name": "BoardA.PcbDoc", "board": {"outlineRectMils": [0, 0, 1000, 500]},
              "stats": {"pads": 4, "tracks": 3, "vias": 0}}],
    "warnings": [],
}
V2 = {
    "schema": "aidrive.snapshot.v0",
    "stats": {"componentCount": 2, "netCount": 2, "bomRowCount": 2},
    "components": [
        {"designator": "R1", "value": "22k", "footprint": "0603", "description": "resistor", "sheet": "S1"},
        {"designator": "R2", "value": "1k", "footprint": "0402", "description": "resistor", "sheet": "S2"},
    ],
    "nets": [
        {"name": "VCC", "terminalCount": 1, "terminals": [{"designator": "R1", "pin": "1"}]},
        {"name": "N$2", "terminalCount": 2, "terminals": [
            {"designator": "R2", "pin": "1"}, {"designator": "R1", "pin": "3"}]},
    ],
    "bom": [
        {"designator": "R1", "value": "22k", "footprint": "0603", "dnp": False},
        {"designator": "R2", "value": "1k", "footprint": "0402", "dnp": False},
    ],
    "pcbs": [{"name": "BoardA.PcbDoc", "board": {"outlineRectMils": [0, 0, 1200, 600]},
              "stats": {"pads": 6, "tracks": 3, "vias": 0}}],
    "warnings": [],
}


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)


@pytest.fixture
def factory(db):
    return async_sessionmaker(db.bind, expire_on_commit=False)


async def create_project(api, actor, snapshot):
    response = await api.post(
        PREFIX + "/files/projects",
        headers=auth(actor),
        data={"name": "demo"},
        files={"files": ("demo.snapshot.json", json.dumps(snapshot).encode(), "application/json")},
    )
    assert response.status_code == 200
    return response.json()["id"]


async def two_versions(api, actor, factory):
    project_id = await create_project(api, actor, V1)
    assert await jobs.process_next(factory, parse_service.run_parse_job) is True
    (parse_service.project_upload_dir(project_id) / "demo.snapshot.json").write_text(json.dumps(V2))
    assert (await api.post(PREFIX + f"/files/projects/{project_id}/reparse", headers=auth(actor))).status_code == 200
    assert await jobs.process_next(factory, parse_service.run_parse_job) is True
    return project_id


async def test_diff_reports_design_changes(api, actors, db, factory):
    project_id = await two_versions(api, actors["alice"], factory)
    response = await api.get(PREFIX + f"/files/projects/{project_id}/diff", headers=auth(actors["alice"]))
    assert response.status_code == 200
    body = response.json()
    assert (body["fromVersion"], body["toVersion"]) == (1, 2)

    assert [c["designator"] for c in body["components"]["added"]] == ["R2"]
    assert [c["designator"] for c in body["components"]["removed"]] == ["C1"]
    changed = body["components"]["changed"]
    assert [c["designator"] for c in changed] == ["R1"]
    assert changed[0]["fields"]["value"] == {"from": "10k", "to": "22k"}

    nets = body["nets"]
    assert [n["name"] for n in nets["added"]] == ["N$2"]
    assert [n["name"] for n in nets["removed"]] == ["GND"]
    vcc = next(n for n in nets["changed"] if n["name"] == "VCC")
    assert vcc["terminalCount"] == {"from": 2, "to": 1}
    assert vcc["terminalsRemoved"] == ["C1-1"]

    assert [b["designator"] for b in body["bom"]["added"]] == ["R2"]
    assert [b["designator"] for b in body["bom"]["removed"]] == ["C1"]
    assert body["bom"]["changed"][0]["fields"]["value"] == {"from": "10k", "to": "22k"}

    board = body["boards"]["changed"][0]
    assert board["name"] == "BoardA.PcbDoc"
    assert board["fields"]["widthMil"] == {"from": 1000, "to": 1200}
    assert board["fields"]["pads"] == {"from": 4, "to": 6}

    assert body["summary"] == {
        "componentAdded": 1, "componentRemoved": 1, "componentChanged": 1,
        "netAdded": 1, "netRemoved": 1, "netChanged": 1,
        "bomAdded": 1, "bomRemoved": 1, "bomChanged": 1,
        "boardAdded": 0, "boardRemoved": 0, "boardChanged": 1,
    }


async def test_diff_same_version_is_empty(api, actors, db, factory):
    project_id = await two_versions(api, actors["alice"], factory)
    response = await api.get(
        PREFIX + f"/files/projects/{project_id}/diff?from=2&to=2", headers=auth(actors["alice"])
    )
    assert response.status_code == 200
    assert set(response.json()["summary"].values()) == {0}


async def test_diff_validates_versions_and_owner(api, actors, db, factory):
    project_id = await two_versions(api, actors["alice"], factory)
    assert (await api.get(
        PREFIX + f"/files/projects/{project_id}/diff?from=1&to=9", headers=auth(actors["alice"])
    )).status_code == 404
    assert (await api.get(
        PREFIX + f"/files/projects/{project_id}/diff?from=0&to=2", headers=auth(actors["alice"])
    )).status_code == 422
    for actor in ("bob", "admin"):
        assert (await api.get(
            PREFIX + f"/files/projects/{project_id}/diff", headers=auth(actors[actor])
        )).status_code == 404
    assert (await api.get(PREFIX + f"/files/projects/{project_id}/diff")).status_code == 401
