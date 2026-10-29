import io
import json
import zipfile
from copy import deepcopy

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.services.files import jobs, parse_service
from conftest import auth

PREFIX = "/api/v1"
SNAPSHOT = {
    "schema": "aidrive.snapshot.v0",
    "project": {"name": "export", "filename": "demo.PrjPcb"},
    "stats": {"componentCount": 3, "netCount": 2, "bomRowCount": 3},
    "components": [
        {"designator": "R1", "value": "10k", "footprint": "R0603", "sheet": "Sheet1"},
        {"designator": "R2", "value": "10k", "footprint": "R0603", "sheet": "Sheet1"},
        {"designator": "C1", "value": "100nF", "footprint": "C0603", "sheet": "Sheet1"},
    ],
    "nets": [
        {
            "name": "GND",
            "terminalCount": 2,
            "terminals": [{"designator": "R1", "pin": "2"}, {"designator": "C1", "pin": "2"}],
        },
        {"name": "N$1", "terminalCount": 1, "terminals": [{"designator": "R2", "pin": "1"}]},
    ],
    "bom": [
        {"designator": "R1", "value": "10k", "footprint": "R0603", "libraryRef": "R", "description": "电阻", "sheet": "Sheet1", "dnp": False},
        {"designator": "R2", "value": "10k", "footprint": "R0603", "libraryRef": "R", "description": "电阻", "sheet": "Sheet1", "dnp": False},
        {"designator": "C1", "value": "100nF", "footprint": "C0603", "libraryRef": "C", "description": "电容", "sheet": "Sheet1", "dnp": True},
    ],
    "pcbs": [{"name": "demo.PcbDoc", "stats": {"pads": 8}, "board": {"outlineRectMils": [0, 0, 1000, 500]}}],
    "warnings": [],
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


async def ready_project(api, actors, factory, snapshot=None):
    project_id = await create_project(api, actors["alice"], snapshot)
    assert await jobs.process_next(factory, parse_service.run_parse_job) is True
    return project_id


async def test_bom_csv_merged_and_detail(api, actors, factory):
    project_id = await ready_project(api, actors, factory)
    merged = await api.get(
        PREFIX + f"/files/projects/{project_id}/exports/bom", headers=auth(actors["alice"])
    )
    assert merged.status_code == 200
    assert merged.headers["content-type"].startswith("text/csv")
    assert "attachment" in merged.headers["content-disposition"]
    text = merged.content.decode("utf-8-sig")
    lines = text.splitlines()
    assert lines[0] == "值,封装,库引用,描述,数量,位号,DNP"
    assert "10k,R0603,R,电阻,2,R1 R2," in lines
    assert "100nF,C0603,C,电容,1,C1,是" in lines

    detail = await api.get(
        PREFIX + f"/files/projects/{project_id}/exports/bom?merged=false",
        headers=auth(actors["alice"]),
    )
    assert detail.status_code == 200
    rows = detail.content.decode("utf-8-sig").splitlines()
    assert rows[0] == "位号,值,封装,库引用,描述,图纸,DNP"
    assert len(rows) == 4
    assert rows[3] == "C1,100nF,C0603,C,电容,Sheet1,是"


async def test_nets_csv_includes_terminals(api, actors, factory):
    project_id = await ready_project(api, actors, factory)
    response = await api.get(
        PREFIX + f"/files/projects/{project_id}/exports/nets", headers=auth(actors["alice"])
    )
    assert response.status_code == 200
    rows = response.content.decode("utf-8-sig").splitlines()
    assert rows[0] == "网络名,连接数,端接明细"
    assert "GND,2,R1-2; C1-2" in rows
    assert "N$1,1,R2-1" in rows


async def test_csv_formula_injection_is_neutralized(api, actors, factory):
    snapshot = deepcopy(SNAPSHOT)
    snapshot["bom"] = [
        {"designator": "=cmd|' /C calc'!A0", "value": "@SUM(1)", "footprint": "+A1", "dnp": False},
        {"designator": "-12", "value": "-R1", "footprint": "", "dnp": False},
    ]
    project_id = await ready_project(api, actors, factory, snapshot)
    response = await api.get(
        PREFIX + f"/files/projects/{project_id}/exports/bom?merged=false",
        headers=auth(actors["alice"]),
    )
    text = response.content.decode("utf-8-sig")
    assert "'=cmd|' /C calc'!A0" in text
    assert "'@SUM(1)" in text
    assert "'+A1" in text
    assert "-12" in text
    assert "'-R1" in text


async def test_output_package_contains_bom_nets_manifest_and_renders(api, actors, factory):
    project_id = await ready_project(api, actors, factory)
    (parse_service.project_render_dir(project_id) / "sch_0.svg").write_text("<svg/>", encoding="utf-8")
    response = await api.get(
        PREFIX + f"/files/projects/{project_id}/exports/package", headers=auth(actors["alice"])
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        assert {"bom.csv", "bom-detail.csv", "nets.csv", "manifest.json", "render/sch_0.svg"} <= names
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["projectName"] == "demo"
    assert manifest["snapshotVersion"] == 1
    assert manifest["stats"]["componentCount"] == 3
    assert manifest["boards"][0]["name"] == "demo.PcbDoc"
    assert any("OutJob" in note for note in manifest["notes"])


async def test_exports_require_ready_snapshot(api, actors):
    project_id = await create_project(api, actors["alice"])
    for path in ("bom", "nets", "package", "pnp", "outjob"):
        response = await api.get(
            PREFIX + f"/files/projects/{project_id}/exports/{path}", headers=auth(actors["alice"])
        )
        assert response.status_code == 409
        assert "尚未解析" in response.json()["detail"]


async def test_exports_are_owner_only(api, actors, factory):
    project_id = await ready_project(api, actors, factory)
    for actor in ("bob", "admin"):
        for path in ("bom", "nets", "package", "pnp", "outjob"):
            response = await api.get(
                PREFIX + f"/files/projects/{project_id}/exports/{path}", headers=auth(actors[actor])
            )
            assert response.status_code == 404
    assert (await api.get(PREFIX + f"/files/projects/{project_id}/exports/bom")).status_code == 401


async def test_manufacturing_requires_pcb_document(api, actors, factory):
    snapshot = deepcopy(SNAPSHOT)
    snapshot["pcbs"] = []
    project_id = await ready_project(api, actors, factory, snapshot)
    for path in ("pnp", "outjob"):
        response = await api.get(
            PREFIX + f"/files/projects/{project_id}/exports/{path}", headers=auth(actors["alice"])
        )
        assert response.status_code == 409
        assert "PCB" in response.json()["detail"]


async def test_manufacturing_streams_worker_output(api, actors, factory, monkeypatch):
    from app.routers.files import exports as exports_router

    project_id = await ready_project(api, actors, factory)
    calls = []

    async def fake_generate(project, kind):
        calls.append(kind)
        return b"Designator,Comment\r\nR1,10k\r\n"

    monkeypatch.setattr(exports_router, "generate_manufacturing", fake_generate)
    pnp = await api.get(PREFIX + f"/files/projects/{project_id}/exports/pnp", headers=auth(actors["alice"]))
    assert pnp.status_code == 200
    assert pnp.content.startswith(b"Designator,Comment")
    outjob = await api.get(PREFIX + f"/files/projects/{project_id}/exports/outjob", headers=auth(actors["alice"]))
    assert outjob.status_code == 200
    assert outjob.headers["content-type"] == "application/octet-stream"
    assert calls == ["pnp", "outjob"]


async def test_manufacturing_failure_hides_internal_details(api, actors, factory, monkeypatch):
    from app.routers.files import exports as exports_router
    from app.services.files.export_service import ExportError

    project_id = await ready_project(api, actors, factory)

    async def boom(project, kind):
        raise ExportError("/private/uploads/project/demo.PcbDoc 解析失败")

    monkeypatch.setattr(exports_router, "generate_manufacturing", boom)
    response = await api.get(PREFIX + f"/files/projects/{project_id}/exports/outjob", headers=auth(actors["alice"]))
    assert response.status_code == 500
    assert "制造文件生成失败" in response.json()["detail"]
    assert "private" not in response.text
