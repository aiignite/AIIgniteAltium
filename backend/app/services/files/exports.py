"""工程输出文件：BOM/网络 CSV、输出包 ZIP 与附件文件名。

所有数据来自归一化快照（aidrive.snapshot.v0），不在此处解析 Altium 源文件。
"""

import csv
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

from app.models.files.uploaded_project import UploadedProject

CSV_MEDIA_TYPE = "text/csv; charset=utf-8"
ZIP_MEDIA_TYPE = "application/zip"
OUTJOB_MEDIA_TYPE = "application/octet-stream"
PNP_MEDIA_TYPE = "text/csv; charset=utf-8"


def merge_bom(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 值|封装|DNP 合并 BOM 行，保持首次出现顺序。"""
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
    return [merged[key] for key in order]


def _cell(value: Any) -> str:
    text = "" if value is None else str(value)
    # 防 CSV 公式注入：Excel 会把 = + @ 开头及 -数字 外的 - 开头当公式执行
    if text[:1] in {"=", "+", "@", "\t", "\r"} or (text[:1] == "-" and not text[1:2].isdigit()):
        return "'" + text
    return text


def _csv_bytes(header: list[str], rows: Iterable[Iterable[Any]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow([_cell(value) for value in row])
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def _snapshot(project: UploadedProject) -> dict[str, Any]:
    return project.snapshot or {}


def bom_csv(project: UploadedProject, *, merged: bool = True) -> bytes:
    rows = [r for r in _snapshot(project).get("bom") or [] if isinstance(r, dict)]
    if merged:
        return _csv_bytes(
            ["值", "封装", "库引用", "描述", "数量", "位号", "DNP"],
            (
                [
                    row["value"],
                    row["footprint"],
                    row["libraryRef"],
                    row["description"],
                    row["quantity"],
                    " ".join(row["designators"]),
                    "是" if row["dnp"] else "",
                ]
                for row in merge_bom(rows)
            ),
        )
    return _csv_bytes(
        ["位号", "值", "封装", "库引用", "描述", "图纸", "DNP"],
        (
            [
                r.get("designator", ""),
                r.get("value", ""),
                r.get("footprint", ""),
                r.get("libraryRef", ""),
                r.get("description", ""),
                r.get("sheet", ""),
                "是" if r.get("dnp") else "",
            ]
            for r in rows
        ),
    )


def nets_csv(project: UploadedProject) -> bytes:
    def terminals(net: dict[str, Any]) -> str:
        items = net.get("terminals") or []
        return "; ".join(
            f"{t.get('designator', '?')}-{t.get('pin', '')}" if isinstance(t, dict) else str(t)
            for t in items
        )

    rows = [n for n in _snapshot(project).get("nets") or [] if isinstance(n, dict)]
    return _csv_bytes(
        ["网络名", "连接数", "端接明细"],
        (
            [
                net.get("name", ""),
                net.get("terminalCount", len(net.get("terminals") or [])),
                terminals(net),
            ]
            for net in rows
        ),
    )


def _manifest(project: UploadedProject, files: list[dict[str, Any]]) -> bytes:
    snapshot = _snapshot(project)
    payload = {
        "schema": snapshot.get("schema", "aidrive.snapshot.v0"),
        "projectName": project.name,
        "snapshotVersion": project.current_version or 0,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "stats": snapshot.get("stats", {}),
        "boards": [
            {"name": p.get("name", ""), "board": p.get("board", {}), "stats": p.get("stats", {})}
            for p in snapshot.get("pcbs") or []
            if isinstance(p, dict)
        ],
        "warnings": snapshot.get("warnings", []),
        "files": files,
        "notes": [
            "Gerber/钻孔不在本包内：请下载「Gerber/钻孔 OutJob」并放入 Altium 工程目录运行，由 Altium 生成。",
            "本包数据来自平台归一化快照，与 Altium 原生输出可能存在差异，投板前请核对。",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def build_package(project: UploadedProject, render_dir: Path) -> bytes:
    """打包 BOM、网络表、清单、design.json 与已有渲染图。"""
    entries: list[tuple[str, bytes]] = [
        ("bom.csv", bom_csv(project, merged=True)),
        ("bom-detail.csv", bom_csv(project, merged=False)),
        ("nets.csv", nets_csv(project)),
    ]
    design_json = Path(project.design_json_path) if project.design_json_path else None
    if design_json is not None and design_json.is_file():
        entries.append(("design.json", design_json.read_bytes()))
    if render_dir.is_dir():
        for svg in sorted(render_dir.glob("*.svg")):
            entries.append((f"render/{svg.name}", svg.read_bytes()))
    files = [{"name": name, "size": len(data)} for name, data in entries]
    entries.append(("manifest.json", _manifest(project, files)))

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return buffer.getvalue()


def attachment_headers(filename: str) -> dict[str, str]:
    ascii_name = "".join(
        ch if ch.isascii() and (ch.isalnum() or ch in "-_. ") else "_" for ch in filename
    ).strip() or "export"
    return {
        "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
    }


def export_filename(project: UploadedProject, label: str, suffix: str) -> str:
    version = project.current_version or 0
    return f"{project.name}-{label}-v{version}{suffix}"
