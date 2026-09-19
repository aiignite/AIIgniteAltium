"""工程解析服务：保存上传 → 隔离 worker 解析 → 快照落库。"""

import asyncio
import logging
import shutil
import time
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
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


async def parse_project(project_id: UUID) -> None:
    """BackgroundTask 入口：自管 session（请求 session 已关闭）。"""
    from app.database import async_session_maker

    async with async_session_maker() as db:
        project = await db.get(UploadedProject, project_id)
        if project is None:
            return
        project.status = "parsing"
        await db.commit()
        started = time.time()
        try:
            direct = _try_direct_snapshot(_read_upload_files(project))
            if direct is not None:
                result = {"ok": True, "snapshot": direct, "svgManifest": [], "designJsonFile": ""}
            else:
                result = await asyncio.to_thread(
                    run_parse,
                    Path(project.storage_dir),
                    project_render_dir(project.id),
                    render_svg=True,
                    project_name=project.name,
                )
            duration = int((time.time() - started) * 1000)
            if not result.get("ok"):
                project.status = "failed"
                project.error = result.get("error", "未知解析错误")[:4000]
            else:
                project.status = "ready"
                project.error = ""
                project.snapshot = result["snapshot"]
                project.svg_manifest = result.get("svgManifest", [])
                design_json_file = result.get("designJsonFile") or ""
                project.design_json_path = (
                    str(project_render_dir(project.id) / design_json_file) if design_json_file else ""
                )
            project.parse_duration_ms = duration
        except Exception as exc:  # noqa: BLE001
            logger.exception("parse_project failed")
            project.status = "failed"
            project.error = str(exc)[:4000]
        await db.commit()


def _read_upload_files(project: UploadedProject) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    root = Path(project.storage_dir)
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
