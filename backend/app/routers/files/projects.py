import re
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.files.uploaded_project import UploadedProject
from app.schemas import CamelModel
from app.security import get_current_user
from app.services.files import parse_service

router = APIRouter(prefix="/files/projects", tags=["files"])


class ProjectOut(CamelModel):
    id: str
    name: str
    status: str
    error: str
    file_names: list[str]
    stats: dict[str, Any] = {}
    svg_manifest: list[dict] = []
    parse_duration_ms: int = 0
    created_at: str
    updated_at: str


class ProjectDetailOut(ProjectOut):
    snapshot: dict[str, Any] = {}


def _out(p: UploadedProject, *, with_snapshot: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": str(p.id),
        "name": p.name,
        "status": p.status,
        "error": p.error,
        "file_names": p.file_names or [],
        "stats": (p.snapshot or {}).get("stats", {}),
        "svg_manifest": p.svg_manifest or [],
        "parse_duration_ms": p.parse_duration_ms,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }
    if with_snapshot:
        data["snapshot"] = p.snapshot or {}
    return data


async def _get_owned_project(db: AsyncSession, project_id: UUID, user_id: UUID) -> UploadedProject:
    project = await db.get(UploadedProject, project_id)
    if project is None or project.is_deleted or str(project.user_id) != str(user_id):
        raise HTTPException(status_code=404, detail="工程不存在")
    return project


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(UploadedProject)
        .where(UploadedProject.user_id == str(user.id), UploadedProject.is_deleted.is_(False))
        .order_by(UploadedProject.updated_at.desc())
    )
    return [_out(p) for p in result.scalars()]


@router.post("", response_model=ProjectOut)
async def upload_project(
    background_tasks: BackgroundTasks,
    name: str = Form(""),
    files: list[UploadFile] = File(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not files:
        raise HTTPException(status_code=400, detail="未选择文件")
    payloads: list[tuple[str, bytes]] = []
    for f in files:
        raw = await f.read()
        suffix = Path(f.filename or "").suffix.lower()
        if suffix not in parse_service.ALLOWED_SUFFIXES:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型: {f.filename}（支持 .PrjPcb/.SchDoc/.PcbDoc/.SchLib/.PcbLib/.json）",
            )
        payloads.append((f.filename or "file.bin", raw))
    project_name = name.strip() or Path(payloads[0][0]).stem
    project = UploadedProject(
        user_id=str(user.id),
        name=project_name,
        status="uploaded",
        file_names=[n for n, _ in payloads],
    )
    db.add(project)
    await db.flush()
    await parse_service.save_uploaded_files(db, project, payloads)
    await db.commit()
    await db.refresh(project)
    background_tasks.add_task(parse_service.parse_project, project.id)
    return _out(project)


@router.post("/{project_id}/reparse", response_model=ProjectOut)
async def reparse_project(
    project_id: UUID,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    project = await _get_owned_project(db, project_id, user.id)
    project.status = "parsing"
    await db.commit()
    await db.refresh(project)
    background_tasks.add_task(parse_service.parse_project, project.id)
    return _out(project)


@router.get("/{project_id}", response_model=ProjectDetailOut)
async def get_project(
    project_id: UUID,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    project = await _get_owned_project(db, project_id, user.id)
    return _out(project, with_snapshot=True)


@router.delete("/{project_id}")
async def delete_project(
    project_id: UUID,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_owned_project(db, project_id, user.id)
    project.is_deleted = True
    await db.commit()
    background_tasks.add_task(parse_service.delete_project_files, project)
    return {"ok": True}


def _snapshot_rows(project: UploadedProject, key: str) -> list[dict[str, Any]]:
    rows = (project.snapshot or {}).get(key) or []
    return rows if isinstance(rows, list) else []


def _apply_query(rows: list[dict[str, Any]], search: str, page: int, page_size: int, sort_key: str | None, sort_dir: str) -> dict[str, Any]:
    out = rows
    if search:
        needle = search.lower()

        def match(row: dict[str, Any]) -> bool:
            return any(needle in str(v).lower() for v in row.values())

        out = [r for r in out if match(r)]
    sort_whitelist = {"designator", "name", "value", "footprint", "terminalCount", "sheet"}
    if sort_key in sort_whitelist:
        out = sorted(out, key=lambda r: str(r.get(sort_key, "")), reverse=(sort_dir == "desc"))
    total = len(out)
    start = (page - 1) * page_size
    return {"items": out[start : start + page_size], "total": total}


@router.get("/{project_id}/components")
async def list_components(
    project_id: UUID,
    search: str = "",
    page: int = 1,
    page_size: int = 50,
    sort_by: str | None = None,
    sort_dir: str = "asc",
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_owned_project(db, project_id, user.id)
    return _apply_query(_snapshot_rows(project, "components"), search, max(page, 1), min(page_size, 500), sort_by, sort_dir)


@router.get("/{project_id}/nets")
async def list_nets(
    project_id: UUID,
    search: str = "",
    page: int = 1,
    page_size: int = 50,
    sort_by: str | None = None,
    sort_dir: str = "asc",
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_owned_project(db, project_id, user.id)
    return _apply_query(_snapshot_rows(project, "nets"), search, max(page, 1), min(page_size, 500), sort_by, sort_dir)


@router.get("/{project_id}/nets/{net_name}")
async def get_net(
    project_id: UUID,
    net_name: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    project = await _get_owned_project(db, project_id, user.id)
    for net in _snapshot_rows(project, "nets"):
        if net.get("name") == net_name:
            return net
    raise HTTPException(status_code=404, detail="网络不存在")


@router.get("/{project_id}/bom")
async def list_bom(
    project_id: UUID,
    search: str = "",
    page: int = 1,
    page_size: int = 100,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_owned_project(db, project_id, user.id)
    rows = _snapshot_rows(project, "bom")
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in rows:
        key = f"{row.get('value', '')}|{row.get('footprint', '')}|{row.get('dnp', False)}"
        if key not in merged:
            merged[key] = {
                "value": row.get("value", ""),
                "footprint": row.get("footprint", ""),
                "libraryRef": row.get("libraryRef", ""),
                "description": row.get("description", ""),
                "dnp": bool(row.get("dnp")),
                "designators": [],
                "quantity": 0,
            }
            order.append(key)
        merged[key]["designators"].append(row.get("designator", "?"))
        merged[key]["quantity"] += 1
    out = [merged[k] for k in order]
    if search:
        needle = search.lower()
        out = [r for r in out if any(needle in str(v).lower() for v in r.values())]
    total = len(out)
    start = (max(page, 1) - 1) * min(page_size, 500)
    return {"items": out[start : start + min(page_size, 500)], "total": total}


@router.get("/{project_id}/svgs")
async def list_svgs(
    project_id: UUID,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    project = await _get_owned_project(db, project_id, user.id)
    return project.svg_manifest or []


@router.get("/{project_id}/svgs/{svg_id}")
async def get_svg(
    project_id: UUID,
    svg_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    project = await _get_owned_project(db, project_id, user.id)
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", svg_id):
        raise HTTPException(status_code=400, detail="非法 svgId")
    path = parse_service.project_render_dir(project.id) / f"{svg_id}.svg"
    if not path.exists():
        raise HTTPException(status_code=404, detail="渲染文件不存在")
    return FileResponse(path, media_type="image/svg+xml")
