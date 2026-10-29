"""制造输出编排：调用隔离 worker 生成贴片坐标 CSV 与 Gerber OutJob。"""

import asyncio
import tempfile
from pathlib import Path

from app.models.files.uploaded_project import UploadedProject
from app.services.files import worker_client


class ExportError(Exception):
    """制造输出失败；细节仅写日志，不回传客户端。"""


def _pcb_name(project: UploadedProject) -> str:
    for pcb in (project.snapshot or {}).get("pcbs") or []:
        name = pcb.get("name") if isinstance(pcb, dict) else ""
        if name and str(name).lower().endswith(".pcbdoc"):
            return Path(str(name)).name
    for name in project.file_names or []:
        if str(name).lower().endswith(".pcbdoc"):
            return Path(str(name)).name
    return ""


def _generate(project: UploadedProject, kind: str) -> bytes:
    project_dir = Path(project.storage_dir)
    if not project_dir.is_dir():
        raise ExportError("工程文件不存在")
    with tempfile.TemporaryDirectory(prefix="aidrive_export_") as tmp:
        out_dir = Path(tmp)
        result = worker_client.run_export(
            project_dir, out_dir, kind=kind, pcb_name=_pcb_name(project)
        )
        if not result.get("ok"):
            raise ExportError(str(result.get("error") or "未知导出错误"))
        files = result.get("files") or []
        target = out_dir / str((files[0] if files else {}).get("name") or "")
        if not files or not target.is_file() or target.parent != out_dir:
            raise ExportError("导出未产生有效文件")
        return target.read_bytes()


async def generate_manufacturing(project: UploadedProject, kind: str) -> bytes:
    return await asyncio.to_thread(_generate, project, kind)
