"""工程解析服务：保存上传 → 隔离 worker 解析 → 快照落库。"""

import asyncio
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.files.parse_job import ParseJob
from app.models.files.snapshot_version import SnapshotVersion
from app.models.files.uploaded_project import UploadedProject
from app.services.files.worker_client import run_parse

logger = logging.getLogger(__name__)

ALLOWED_SUFFIXES = {".prjpcb", ".schdoc", ".pcbdoc", ".schlib", ".pcblib", ".snapshojson", ".json"}
SCHEMA_DIRECT = "aidrive.snapshot.v0"


def _data_root() -> Path:
    root = settings.resolve_data_dir()
    (root / "uploads").mkdir(exist_ok=True)
    (root / "render").mkdir(exist_ok=True)
    return root


def project_upload_dir(project_id: UUID) -> Path:
    path = _data_root() / "uploads" / str(project_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def project_render_dir(project_id: UUID) -> Path:
    path = _data_root() / "render" / str(project_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def sanitize_filename(name: str) -> str:
    keep = "".join(ch for ch in name if ch.isalnum() or ch in "._- ")
    return (keep.strip() or "file.bin")[:120]


async def save_uploaded_files(db: AsyncSession, project: UploadedProject, files: list[tuple[str, bytes]]) -> None:
    dest = project_upload_dir(project.id)
    for original_name, payload in files:
        target = dest / sanitize_filename(original_name)
        target.write_bytes(payload)
    project.storage_dir = str(dest)


def _try_direct_snapshot(files: list[tuple[str, bytes]]) -> dict[str, Any] | None:
    """单文件上传 aidrive.snapshot.v0 JSON 时直接采用（无需 altium-monkey 的回退通道）。"""
    for name, payload in files:
        if name.lower().endswith(".json") and len(payload) < 50_000_000:
            try:
                import json

                data = json.loads(payload.decode("utf-8"))
                if isinstance(data, dict) and str(data.get("schema", "")).startswith("aidrive.snapshot"):
                    return data
            except Exception:  # noqa: BLE001
                continue
    return None


async def run_parse_job(db: AsyncSession, job_id: UUID) -> None:
    """执行已领取（running）的解析任务，结果与快照版本在同一事务内落库。"""
    job = await db.get(ParseJob, job_id)
    if job is None or job.status != "running":
        return
    project = await db.get(UploadedProject, job.project_id)
    if project is None:
        job.status = "failed"
        job.error = "工程不存在"
        job.finished_at = datetime.now(timezone.utc)
        await db.commit()
        return
    project_id = project.id
    storage_dir = Path(project.storage_dir)
    project_name = project.name
    # 解析可能耗时数分钟，先释放事务，避免长期占用连接
    await db.commit()

    started = time.time()
    try:
        files = await asyncio.to_thread(_read_dir_files, storage_dir)
        direct = await asyncio.to_thread(_try_direct_snapshot, files)
        if direct is not None:
            result = {"ok": True, "snapshot": direct, "svgManifest": [], "designJsonFile": ""}
        elif not storage_dir.exists():
            result = {"ok": False, "error": "工程文件不存在，无法解析"}
        else:
            result = await asyncio.to_thread(
                run_parse,
                storage_dir,
                project_render_dir(project_id),
                render_svg=True,
                project_name=project_name,
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("parse job %s failed", job_id)
        result = {"ok": False, "error": str(exc)[:4000]}
    await _persist_result(db, job_id, project_id, result, int((time.time() - started) * 1000))


async def _persist_result(db: AsyncSession, job_id: UUID, project_id: UUID, result: dict[str, Any], duration: int) -> None:
    async with db.begin():
        job = await db.scalar(select(ParseJob).where(ParseJob.id == job_id).with_for_update())
        if job is None:
            return
        project = await db.scalar(
            select(UploadedProject)
            .where(UploadedProject.id == project_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        job.finished_at = datetime.now(timezone.utc)
        job.error = ""
        if project is None or project.is_deleted:
            job.status = "failed"
            job.error = "工程不存在或已删除"
            return
        project.parse_duration_ms = duration
        if not result.get("ok"):
            message = str(result.get("error") or "未知解析错误")[:4000]
            job.status = "failed"
            job.error = message
            project.status = "failed"
            project.error = message
            return
        snapshot = result["snapshot"]
        svg_manifest = result.get("svgManifest") or []
        design_json_file = result.get("designJsonFile") or ""
        design_json_path = str(project_render_dir(project.id) / design_json_file) if design_json_file else ""
        version = (project.current_version or 0) + 1
        db.add(
            SnapshotVersion(
                project_id=project.id,
                version=version,
                snapshot=snapshot,
                svg_manifest=svg_manifest,
                design_json_path=design_json_path,
                parse_duration_ms=duration,
            )
        )
        project.snapshot = snapshot
        project.svg_manifest = svg_manifest
        project.design_json_path = design_json_path
        project.current_version = version
        project.status = "ready"
        project.error = ""
        job.status = "succeeded"


def _read_dir_files(root: Path) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    if not root.exists():
        return out
    for path in sorted(root.iterdir()):
        if path.is_file():
            try:
                out.append((path.name, path.read_bytes()))
            except OSError:
                continue
    return out


async def delete_project_files(project: UploadedProject) -> None:
    for sub in ("uploads", "render"):
        path = _data_root() / sub / str(project.id)
        if path.exists():
            await asyncio.to_thread(shutil.rmtree, path, True)
