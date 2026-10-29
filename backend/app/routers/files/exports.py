"""工程输出文件下载：BOM、网络表、输出包与制造输出。"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.files.uploaded_project import UploadedProject
from app.security import get_current_user
from app.services.files import exports, parse_service
from app.services.files.access import get_owned_project as _get_owned_project
from app.services.files.export_service import ExportError, generate_manufacturing

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/files/projects", tags=["files"])


def _require_ready(project: UploadedProject) -> None:
    if not project.current_version or not project.snapshot:
        raise HTTPException(409, "工程尚未解析完成，无法导出")


def _pcb_documents(project: UploadedProject) -> list[dict]:
    return [p for p in (project.snapshot or {}).get("pcbs") or [] if isinstance(p, dict) and p.get("name")]


@router.get("/{project_id}/exports/bom")
async def export_bom(
    project_id: UUID,
    merged: bool = Query(True, description="true=按值/封装合并，false=按位号明细"),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    project = await _get_owned_project(db, project_id, user.id)
    _require_ready(project)
    return Response(
        content=exports.bom_csv(project, merged=merged),
        media_type=exports.CSV_MEDIA_TYPE,
        headers=exports.attachment_headers(exports.export_filename(project, "合并BOM" if merged else "BOM明细", ".csv")),
    )


@router.get("/{project_id}/exports/nets")
async def export_nets(
    project_id: UUID,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    project = await _get_owned_project(db, project_id, user.id)
    _require_ready(project)
    return Response(
        content=exports.nets_csv(project),
        media_type=exports.CSV_MEDIA_TYPE,
        headers=exports.attachment_headers(exports.export_filename(project, "网络表", ".csv")),
    )


@router.get("/{project_id}/exports/package")
async def export_package(
    project_id: UUID,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    project = await _get_owned_project(db, project_id, user.id)
    _require_ready(project)
    content = exports.build_package(project, parse_service.project_render_dir(project.id))
    return Response(
        content=content,
        media_type=exports.ZIP_MEDIA_TYPE,
        headers=exports.attachment_headers(exports.export_filename(project, "输出包", ".zip")),
    )


@router.get("/{project_id}/exports/pnp")
async def export_pnp(
    project_id: UUID,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    project = await _get_owned_project(db, project_id, user.id)
    _require_ready(project)
    if not _pcb_documents(project):
        raise HTTPException(409, "工程未包含 PCB 文档（.PcbDoc），无法生成贴片坐标")
    content = await _manufacturing(project, "pnp")
    return Response(
        content=content,
        media_type=exports.PNP_MEDIA_TYPE,
        headers=exports.attachment_headers(exports.export_filename(project, "贴片坐标", ".csv")),
    )


@router.get("/{project_id}/exports/outjob")
async def export_outjob(
    project_id: UUID,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    project = await _get_owned_project(db, project_id, user.id)
    _require_ready(project)
    if not _pcb_documents(project):
        raise HTTPException(409, "工程未包含 PCB 文档（.PcbDoc），无法生成 Gerber 输出配置")
    content = await _manufacturing(project, "outjob")
    return Response(
        content=content,
        media_type=exports.OUTJOB_MEDIA_TYPE,
        headers=exports.attachment_headers(exports.export_filename(project, "Gerber输出配置", ".OutJob")),
    )


async def _manufacturing(project: UploadedProject, kind: str) -> bytes:
    try:
        return await generate_manufacturing(project, kind)
    except ExportError as exc:
        logger.warning("manufacturing export failed: project=%s kind=%s error=%s", project.id, kind, exc)
        raise HTTPException(500, "制造文件生成失败，请稍后重试或重新解析工程") from exc
