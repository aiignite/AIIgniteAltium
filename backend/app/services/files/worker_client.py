"""隔离 worker 客户端（ADR-002）：子进程运行 altium worker，JSON 文件协议。

后端进程不 import altium_monkey，满足 AGPL 聚合隔离与故障隔离（解析崩溃不影响主服务）。
"""

import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

WORKER_SCRIPT = Path(__file__).resolve().parent.parent.parent / "worker" / "altium_files_worker.py"
EXPORT_WORKER_SCRIPT = Path(__file__).resolve().parent.parent.parent / "worker" / "altium_export_worker.py"
PARSE_TIMEOUT_SECONDS = 300
EXPORT_TIMEOUT_SECONDS = 120


def _run_worker(
    script: Path, job: dict[str, Any], out_dir: Path, *, timeout: int, label: str
) -> dict[str, Any]:
    job.setdefault("jobId", uuid4().hex)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aidrive_job_") as tmp:
        job_path = Path(tmp) / "job.json"
        job_path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        cmd = [sys.executable, str(script), str(job_path)]
        logger.info("%s worker start: %s", label, cmd)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"{label}超时（>{timeout}s）"}
    if proc.returncode != 0:
        logger.error("%s worker failed rc=%s stderr=%s", label, proc.returncode, proc.stderr[-2000:])
        return {"ok": False, "error": f"{label}进程失败: {proc.stderr.strip()[-800:] or '未知错误'}"}
    result_path = out_dir / "result.json"
    if not result_path.exists():
        return {"ok": False, "error": "worker 未产出 result.json"}
    return json.loads(result_path.read_text(encoding="utf-8"))


def run_parse(project_dir: Path, out_dir: Path, *, render_svg: bool = True, project_name: str = "") -> dict[str, Any]:
    """同步执行解析（应在线程池/BackgroundTasks 中调用）。返回 worker 结果 JSON。"""
    return _run_worker(
        WORKER_SCRIPT,
        {
            "projectDir": str(project_dir),
            "outDir": str(out_dir),
            "renderSvg": render_svg,
            "projectName": project_name,
        },
        out_dir,
        timeout=PARSE_TIMEOUT_SECONDS,
        label="解析",
    )


def run_export(project_dir: Path, out_dir: Path, *, kind: str, pcb_name: str = "") -> dict[str, Any]:
    """同步执行制造输出（pnp/outjob）。返回 worker 结果 JSON。"""
    return _run_worker(
        EXPORT_WORKER_SCRIPT,
        {
            "kind": kind,
            "projectDir": str(project_dir),
            "outDir": str(out_dir),
            "pcbName": pcb_name,
        },
        out_dir,
        timeout=EXPORT_TIMEOUT_SECONDS,
        label="导出",
    )
