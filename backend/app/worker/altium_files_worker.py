"""Altium 离线解析 worker（独立子进程，ADR-002 AGPL 隔离）。

协议：argv[1] = job.json 路径
  job:  {"jobId", "projectDir", "outDir", "renderSvg"}
  产出 outDir/result.json：
    {"ok": true, "snapshot": {...}, "svgManifest": [...], "designJsonFile": "design.json"}
    {"ok": false, "error": "..."}

本文件只依赖标准库与 altium_monkey，不 import 应用代码。
"""

import json
import sys
import traceback
from pathlib import Path
from typing import Any

SCHEMA = "aidrive.snapshot.v0"


def _short_sheet(ref: str) -> str:
    return ref.rsplit(":", 1)[-1] if ":" in ref else ref


def _outline_rect_mils(outline: Any) -> tuple[float, float, float, float] | None:
    """包围盒 (left, bottom, right, top) mils。优先现成属性，否则由顶点计算。"""
    for attr in ("bounding_box", "rectangle_mils"):
        val = getattr(outline, attr, None)
        if callable(val):
            try:
                val = val()
            except TypeError:
                continue
        if isinstance(val, (list, tuple)) and len(val) == 4 and all(isinstance(v, (int, float)) for v in val):
            return tuple(float(v) for v in val)  # type: ignore[return-value]
    points = getattr(outline, "points_mils", None)
    if callable(points):
        points = points()
    if points:
        xs = [float(p[0]) for p in points]
        ys = [float(p[1]) for p in points]
        return (min(xs), min(ys), max(xs), max(ys))
    return None


def _safe_name(stem: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in stem)[:60] or "doc"


def find_or_create_prjpcb(project_dir: Path) -> tuple[Path, list[str], list[str]]:
    """返回 (prjpcb路径, sch文件名列表, pcb文件名列表)。无工程文件时合成 INI。"""
    existing = sorted(project_dir.glob("*.PrjPcb")) + sorted(project_dir.glob("*.prjpcb"))
    sch = sorted(p.name for p in project_dir.glob("*.SchDoc"))
    pcb = sorted(p.name for p in project_dir.glob("*.PcbDoc"))
    if existing:
        return existing[0], sch, pcb
    lines = ["[Design]", ""]
    idx = 1
    for name in sch:
        lines += [f"[Document{idx}]", f"DocumentPath={name}", "DocumentKind=SCH", "Enabled=1", ""]
        idx += 1
    for name in pcb:
        lines += [f"[Document{idx}]", f"DocumentPath={name}", "DocumentKind=PCB", "Enabled=1", ""]
        idx += 1
    prjpcb = project_dir / "_synthesized.PrjPcb"
    prjpcb.write_text("\n".join(lines), encoding="utf-8")
    return prjpcb, sch, pcb


def parse(project_dir: Path, out_dir: Path, render_svg: bool, project_name_hint: str = "") -> tuple[dict[str, Any], list[dict], str]:
    import altium_monkey as am

    prjpcb, sch_names, pcb_names = find_or_create_prjpcb(project_dir)
    design = am.AltiumDesign.from_prjpcb(str(prjpcb))
    warnings: list[str] = []
    compiled = None

    snapshot: dict[str, Any] = {
        "schema": SCHEMA,
        "generator": {"tool": "altium-monkey", "version": getattr(am, "__version__", "?")},
        "project": {
            "name": prjpcb.stem.replace("_synthesized", "") or project_name_hint or project_dir.name,
            "filename": prjpcb.name,
            "parameters": {},
        },
        "documents": [],
        "stats": {},
        "components": [],
        "nets": [],
        "bom": [],
        "pcbs": [],
        "warnings": warnings,
    }
    stats = {
        "componentCount": 0,
        "netCount": 0,
        "bomRowCount": 0,
        "logicalDocuments": 0,
        "physicalDocuments": 0,
    }

    try:
        compiled = design.compile()
        summary = compiled.summary
        stats.update(
            componentCount=summary.component_count,
            netCount=summary.net_count,
            logicalDocuments=summary.logical_document_count,
            physicalDocuments=summary.physical_document_count,
        )
        for meta in compiled.physical_page_metadata:
            snapshot["documents"].append({"filename": _short_sheet(meta.physical_instance_path or meta.room_name or "sheet"), "sheetNumber": ""})
    except Exception as exc:  # 无原理图或编译失败时降级继续
        warnings.append(f"原理图编译降级: {exc}")

    try:
        dj = design.to_json()
        out_dir.joinpath("design.json").write_text(
            json.dumps(dj, ensure_ascii=False), encoding="utf-8"
        )
        project = dj.get("project") or {}
        if project.get("parameters"):
            snapshot["project"]["parameters"] = project["parameters"]
        if not snapshot["documents"]:
            snapshot["documents"] = [
                {"filename": s.get("filename", "sheet"), "sheetNumber": s.get("sheet_number", "")}
                for s in dj.get("sheets") or []
            ]
        comps = []
        for c in dj.get("components") or []:
            comps.append(
                {
                    "designator": c.get("designator", "?"),
                    "value": c.get("value") or c.get("comment") or "",
                    "footprint": c.get("footprint") or "",
                    "description": c.get("description") or "",
                    "sheet": _short_sheet(c.get("physical_sheet_id") or ""),
                }
            )
        snapshot["components"] = comps
        nets = []
        for n in dj.get("nets") or []:
            terminals = [
                {
                    "designator": t.get("designator", "?"),
                    "pin": str(t.get("pin", "")),
                    "pinName": t.get("pin_name", ""),
                    "pinType": t.get("pin_type", ""),
                }
                for t in n.get("terminals") or []
            ]
            nets.append({"name": n.get("name", "?"), "terminalCount": len(terminals), "terminals": terminals})
        snapshot["nets"] = nets
    except Exception as exc:
        warnings.append(f"设计 JSON 导出降级: {exc}")

    try:
        snapshot["bom"] = [
            {
                "designator": r.get("designator", "?"),
                "value": r.get("value", ""),
                "footprint": r.get("footprint", ""),
                "libraryRef": r.get("library_ref", ""),
                "description": r.get("description", ""),
                "sheet": r.get("sheet", ""),
                "dnp": bool(r.get("dnp")),
            }
            for r in design.to_bom()
        ]
        stats["bomRowCount"] = len(snapshot["bom"])
    except Exception as exc:
        warnings.append(f"BOM 导出降级: {exc}")

    svg_manifest: list[dict] = []
    if render_svg:
        # 原理图页渲染
        try:
            if compiled is None:
                compiled = design.compile()
            for i, meta in enumerate(compiled.physical_page_metadata):
                try:
                    svg = design.to_physical_svg(meta.page_occurrence_ref)
                    svg_id = f"sch_{i}"
                    out_dir.joinpath(f"{svg_id}.svg").write_text(svg, encoding="utf-8")
                    svg_manifest.append(
                        {"svgId": svg_id, "kind": "sch", "title": meta.room_name or _short_sheet(meta.physical_instance_path) or f"Sheet {i + 1}", "file": f"{svg_id}.svg"}
                    )
                except Exception as exc:
                    warnings.append(f"原理图渲染失败({getattr(meta, 'room_name', i)}): {exc}")
        except Exception as exc:
            warnings.append(f"原理图渲染不可用: {exc}")

        # PCB 渲染 + 统计
        for name in pcb_names:
            pcb_info: dict[str, Any] = {"name": name, "stats": {}, "board": {}}
            try:
                pcb = design.load_pcbdoc(name)
            except Exception:
                try:
                    pcb = am.AltiumPcbDoc.from_file(str(project_dir / name))
                except Exception as exc:
                    warnings.append(f"PCB 加载失败({name}): {exc}")
                    continue
            try:
                outline = pcb.board.outline
                rect = _outline_rect_mils(outline)
                stackup = pcb.board.layer_stackup
                stackup = stackup() if callable(stackup) else stackup
                pcb_info["board"] = {
                    "outlineRectMils": [float(v) for v in rect] if rect else None,
                    "layerStackupCount": len(stackup or []),
                }
                pcb_info["stats"] = {
                    "components": len(pcb.components or []),
                    "pads": len(pcb.pads or []),
                    "tracks": len(pcb.tracks or []),
                    "vias": len(pcb.vias or []),
                    "nets": len(pcb.nets or []),
                }
                snapshot["pcbs"].append(pcb_info)
            except Exception as exc:
                warnings.append(f"PCB 统计失败({name}): {exc}")
            if render_svg:
                svg_id = f"pcb_{_safe_name(Path(name).stem)}"
                try:
                    svg = pcb.to_svg(am.PcbSvgRenderOptions(allow_text_geometry_fallback=True))
                except Exception:
                    try:
                        svg = pcb.to_board_outline_svg()
                        warnings.append(f"PCB 渲染降级为板框({name})")
                    except Exception as exc:
                        warnings.append(f"PCB 渲染失败({name}): {exc}")
                        continue
                out_dir.joinpath(f"{svg_id}.svg").write_text(svg, encoding="utf-8")
                svg_manifest.append({"svgId": svg_id, "kind": "pcb", "title": name, "file": f"{svg_id}.svg"})

    snapshot["stats"] = stats
    if isinstance(snapshot["nets"], list) and snapshot["nets"]:
        stats["netCount"] = len(snapshot["nets"])
    return snapshot, svg_manifest, "design.json"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: altium_files_worker.py <job.json>", file=sys.stderr)
        return 2
    job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    project_dir = Path(job["projectDir"])
    out_dir = Path(job["outDir"])
    render_svg = bool(job.get("renderSvg", True))
    project_name_hint = str(job.get("projectName") or "")
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any]
    try:
        try:
            import altium_monkey  # noqa: F401
        except ImportError as exc:
            result = {"ok": False, "error": f"altium-monkey 未安装: {exc}"}
        else:
            snapshot, svg_manifest, design_json_file = parse(project_dir, out_dir, render_svg, project_name_hint)
            if snapshot["project"].get("name") in ("", None) and project_name_hint:
                snapshot["project"]["name"] = project_name_hint
            result = {
                "ok": True,
                "snapshot": snapshot,
                "svgManifest": svg_manifest,
                "designJsonFile": design_json_file,
            }
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": f"{exc}\n{traceback.format_exc()[-1200:]}"}
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print("worker done ok=%s" % result.get("ok"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
