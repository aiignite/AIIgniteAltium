import json
import subprocess
import sys
from pathlib import Path

import pytest

WORKER = Path(__file__).resolve().parents[1] / "app" / "worker" / "altium_export_worker.py"


def altium_monkey_available() -> bool:
    probe = subprocess.run([sys.executable, "-c", "import altium_monkey"], capture_output=True)
    return probe.returncode == 0


pytestmark = pytest.mark.skipif(
    not altium_monkey_available(), reason="altium-monkey 未安装，跳过制造输出 worker 测试"
)


def run_worker(tmp_path: Path, project_dir: Path, *, kind: str = "outjob", pcb_name: str = "Board.PcbDoc"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    out_dir = tmp_path / "out"
    out_dir.mkdir(exist_ok=True)
    job_path = tmp_path / "job.json"
    job_path.write_text(
        json.dumps(
            {
                "kind": kind,
                "projectDir": str(project_dir),
                "outDir": str(out_dir),
                "pcbName": pcb_name,
            }
        ),
        encoding="utf-8",
    )
    subprocess.run([sys.executable, str(WORKER), str(job_path)], check=True, capture_output=True)
    return json.loads((out_dir / "result.json").read_text(encoding="utf-8")), out_dir


def test_outjob_covers_gerber_drill_and_pick_place(tmp_path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "Board.PcbDoc").write_bytes(b"not parsed by outjob builder")

    result, out_dir = run_worker(tmp_path, project_dir)

    assert result == {"ok": True, "files": [{"name": "manufacturing.OutJob"}]}
    text = (out_dir / "manufacturing.OutJob").read_text(encoding="latin-1")
    assert "Gerber" in text
    assert "NC Drill" in text
    assert "Board.PcbDoc" in text
    assert "PICKPLACE" in text


def test_worker_rejects_path_traversal_and_missing_pcb(tmp_path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "Board.PcbDoc").write_bytes(b"")

    result, out_dir = run_worker(tmp_path, project_dir, pcb_name="../outside/Board.PcbDoc")
    assert result["ok"] is True
    assert "Board.PcbDoc" in (out_dir / "manufacturing.OutJob").read_text(encoding="latin-1")

    empty = tmp_path / "empty"
    empty.mkdir()
    missing, _ = run_worker(tmp_path / "second", empty, pcb_name="")
    assert missing["ok"] is False
    assert "未找到 .PcbDoc" in missing["error"]
