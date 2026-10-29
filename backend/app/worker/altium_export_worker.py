"""Altium 制造输出 worker（独立子进程，ADR-002 AGPL 隔离）。

协议：argv[1] = job.json 路径
  job: {"kind": "pnp" | "outjob", "projectDir", "outDir", "pcbName", "projectName"}
  产出 outDir/result.json：
    {"ok": true, "files": [{"name": "manufacturing.OutJob"}]}
    {"ok": false, "error": "..."}

本文件只依赖标准库与 altium_monkey，不 import 应用代码。
"""

import csv
import io
import json
import sys
import traceback
from pathlib import Path
from typing import Any

PNP_HEADER = [
    "Designator",
    "Comment",
    "Layer",
    "Footprint",
    "CenterX(mm)",
    "CenterY(mm)",
    "Rotation(deg)",
    "Description",
]


def _pcb_document(project_dir: Path, name: str) -> str:
    """返回位于工程目录内的 PcbDoc 文件名（拒绝路径穿越）。"""
    candidate = Path(name).name if name else ""
    if candidate and candidate.lower().endswith(".pcbdoc") and (project_dir / candidate).is_file():
        return candidate
    found = sorted(p.name for p in project_dir.glob("*.PcbDoc"))
    if not found:
        raise FileNotFoundError("工程目录中未找到 .PcbDoc 文档")
    return found[0]


def _project_file(project_dir: Path, pcb_name: str) -> Path:
    existing = sorted(project_dir.glob("*.PrjPcb")) + sorted(project_dir.glob("*.prjpcb"))
    if existing:
        return existing[0]
    lines = ["[Design]", "", "[Document1]", f"DocumentPath={pcb_name}", "DocumentKind=PCB", "Enabled=1", ""]
    prjpcb = project_dir / "_synthesized.PrjPcb"
    prjpcb.write_text("\n".join(lines), encoding="utf-8")
    return prjpcb


def build_pnp(project_dir: Path, out_dir: Path, pcb_name: str) -> list[str]:
    import altium_monkey as am

    design = am.AltiumDesign.from_prjpcb(str(_project_file(project_dir, pcb_name)))
    entries = design.to_pnp(units="mm")
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(PNP_HEADER)
    for entry in entries:
        writer.writerow(
            [
                entry.designator,
                entry.comment,
                entry.layer,
                entry.footprint,
                f"{entry.center_x:.4f}",
                f"{entry.center_y:.4f}",
                f"{entry.rotation:.2f}",
                entry.description,
            ]
        )
    target = out_dir / "pick-and-place.csv"
    target.write_bytes(("\ufeff" + buffer.getvalue()).encode("utf-8"))
    return [target.name]


def build_outjob(project_dir: Path, out_dir: Path, pcb_name: str) -> list[str]:
    """生成 Altium OutJob：Gerber(RS-274X) + NC Drill + Pick & Place。

    平台不直接产出 Gerber；该配置需放入工程目录、在 Altium 中运行后生成制造文件。
    """
    from altium_monkey.altium_outjob import AltiumOutJob

    outjob = AltiumOutJob.create_pcb_fabrication(
        pcb_name,
        output_dir="outputs",
        name="manufacturing",
        gerber=True,
        nc_drill=True,
    )
    place_medium = outjob.add_generated_files_medium("PICKPLACE", "outputs/pickplace")
    outjob.add_pick_place(pcb_name, enabled_medium=place_medium, units="Metric", csv_format=True)

    buffer = io.StringIO()
    outjob.config.write(buffer, space_around_delimiters=False)
    text = buffer.getvalue().replace("\n", "\r\n")
    try:
        data = text.encode("latin-1")
    except UnicodeEncodeError:
        data = text.encode("utf-8-sig")
    target = out_dir / "manufacturing.OutJob"
    target.write_bytes(data)
    return [target.name]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: altium_export_worker.py <job.json>", file=sys.stderr)
        return 2
    job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    project_dir = Path(job["projectDir"])
    out_dir = Path(job["outDir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    kind = str(job.get("kind") or "")
    result: dict[str, Any]
    try:
        try:
            import altium_monkey  # noqa: F401
        except ImportError as exc:
            result = {"ok": False, "error": f"altium-monkey 未安装: {exc}"}
        else:
            pcb_name = _pcb_document(project_dir, str(job.get("pcbName") or ""))
            if kind == "pnp":
                files = build_pnp(project_dir, out_dir, pcb_name)
            elif kind == "outjob":
                files = build_outjob(project_dir, out_dir, pcb_name)
            else:
                raise ValueError(f"未知导出类型: {kind}")
            result = {"ok": True, "files": [{"name": name} for name in files]}
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": f"{exc}\n{traceback.format_exc()[-1200:]}"}
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print("export worker done ok=%s" % result.get("ok"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
