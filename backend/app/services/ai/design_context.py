"""设计上下文构建：把归一化快照压缩为可注入提示词的紧凑文本（渐进披露第一层）。"""

from typing import Any


def live_summary_to_context(summary: dict[str, Any]) -> str:
    """gateway 实时摘要 → 提示词上下文文本。"""
    if not summary or not summary.get("ok"):
        return ""
    lines: list[str] = ["（实时连接 · Altium 当前打开的设计）"]
    lines.append(f"工程: {summary.get('project') or '?'}")
    doc = summary.get("document") or {}
    if doc.get("kind"):
        lines.append(f"活动文档: [{doc.get('kind')}] {doc.get('name', '')}")
    stats = summary.get("pcbStats") or {}
    if stats:
        lines.append(
            f"PCB: 元件 {stats.get('components', '?')} / 焊盘 {stats.get('pads', '?')} / "
            f"走线 {stats.get('tracks', '?')} / 过孔 {stats.get('vias', '?')} / 网络 {stats.get('nets', '?')}"
        )
    board = summary.get("board") or {}
    if board.get("widthMils"):
        lines.append(f"板框: {board['widthMils']} x {board.get('heightMils', '?')} mil, {board.get('layers', '?')} 层")
    sch = summary.get("schematic") or {}
    comps = sch.get("components") or []
    if comps:
        comp_text = ", ".join(
            f"{c.get('designator', '?')}({c.get('value', '') or c.get('footprint', '')})" for c in comps[:12]
        )
        lines.append(f"原理图元件(前{len(comps[:12])}个): {comp_text}")
    nets = sch.get("nets") or []
    if nets:
        lines.append("网络: " + ", ".join(f"{n.get('name')}({n.get('count')})" for n in nets[:12]))
    errors = summary.get("errors") or []
    for e in errors[:3]:
        lines.append(f"注意: {e}")
    return "\n".join(lines)


def build_design_context(snapshot: dict[str, Any], max_components: int = 25, max_nets: int = 30) -> str:
    if not snapshot:
        return ""
    lines: list[str] = []
    project = snapshot.get("project") or {}
    stats = snapshot.get("stats") or {}
    lines.append(f"工程: {project.get('name', '?')}")
    lines.append(
        f"规模: 元件 {stats.get('componentCount', '?')} / 网络 {stats.get('netCount', '?')} / BOM 行 {stats.get('bomRowCount', '?')}"
    )
    docs = snapshot.get("documents") or []
    if docs:
        names = ", ".join(d.get("filename", "?") for d in docs[:8])
        lines.append(f"文档: {names}")

    comps = snapshot.get("components") or []
    if comps:
        lines.append("元件（前 %d 个）:" % min(max_components, len(comps)))
        for c in comps[:max_components]:
            lines.append(
                f"  - {c.get('designator', '?')}: value={c.get('value', '') or c.get('comment', '')} "
                f"footprint={c.get('footprint', '')}"
            )

    nets = snapshot.get("nets") or []
    if nets:
        names = [n.get("name", "?") for n in nets]
        shown = ", ".join(names[:max_nets])
        more = f" …等共 {len(names)} 个" if len(names) > max_nets else ""
        lines.append(f"网络: {shown}{more}")
        # 单端网络提示（审查价值高）
        single = [n.get("name", "?") for n in nets if len(n.get("terminals") or []) <= 1]
        if single:
            lines.append(f"可疑单端网络({len(single)}): {', '.join(single[:15])}")

    for pcb in snapshot.get("pcbs") or []:
        s = pcb.get("stats") or {}
        b = pcb.get("board") or {}
        lines.append(
            f"PCB[{pcb.get('name', '?')}]: 元件 {s.get('components', '?')}, 焊盘 {s.get('pads', '?')}, "
            f"走线 {s.get('tracks', '?')}, 过孔 {s.get('vias', '?')}, 叠层 {b.get('layerStackupCount', '?')} 层"
        )
        rect = b.get("outlineRectMils")
        if rect and len(rect) == 4:
            w = (rect[2] - rect[0]) / 1000.0
            h = (rect[3] - rect[1]) / 1000.0
            lines.append(f"  板框: {w:.1f} x {h:.1f} mil")

    bom = snapshot.get("bom") or []
    if bom:
        lines.append(f"BOM（前 {min(12, len(bom))} 行 / 共 {len(bom)} 行）:")
        for row in bom[:12]:
            lines.append(
                f"  - {row.get('designator', '?')} | {row.get('value', '')} | {row.get('footprint', '')}"
                + (" | DNP" if row.get("dnp") else "")
            )

    warnings = snapshot.get("warnings") or []
    for w in warnings[:5]:
        lines.append(f"警告: {w}")
    return "\n".join(lines)
