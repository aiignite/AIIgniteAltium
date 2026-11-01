"""设计上下文构建：把归一化快照压缩为可注入提示词的紧凑文本（渐进披露第一层）。

明细不属于上下文：这里只给概览 + 与当前问题相关的对象，其余交给查询工具
（``find_components`` / ``find_nets`` / ``get_bom_rows`` / ``get_review_findings``），
并按字符预算硬上限裁剪，避免大工程把提示词撑爆。
"""

import re
from typing import Any

MAX_CONTEXT_CHARS = 6000
DESIGNATOR_RE = re.compile(r"\b([A-Za-z]{1,4}\d{1,5})\b")
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-$+.]{1,}")
_STOP_WORDS = {"THE", "AND", "FOR", "WITH", "WHAT", "HOW", "WHY", "PCB", "SCH", "BOM", "ALT"}

DISCLOSURE_HINT = "明细请用查询工具获取：find_components / find_nets / get_bom_rows / get_review_findings"


def intent_terms(query: str) -> tuple[set[str], set[str]]:
    """从提问中提取意图线索：显式位号 + 关键词（大小写不敏感，用于命中元件/网络/封装）。"""
    text = query or ""
    designators = {m.group(1).upper() for m in DESIGNATOR_RE.finditer(text)}
    words = {w.upper() for w in _TOKEN_RE.findall(text)} - designators
    words = {w for w in words if w not in _STOP_WORDS and len(w) >= 2}
    return designators, words


def _field(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _hits(item: dict[str, Any], designators: set[str], words: set[str], *, name_keys: tuple[str, ...]) -> bool:
    if not designators and not words:
        return False
    name = _field(item, *name_keys).upper()
    if name in designators or any(d and d in name for d in designators):
        return True
    return any(w in name for w in words)


def live_summary_to_context(summary: dict[str, Any], query: str = "") -> str:
    """gateway 实时摘要 → 提示词上下文文本。"""
    if not summary or not summary.get("ok"):
        return ""
    designators, words = intent_terms(query)
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
        lines.append(
            f"板框: {board['widthMils']} x {board.get('heightMils', '?')} mil, {board.get('layers', '?')} 层"
        )
    sch = summary.get("schematic") or {}
    comps = sch.get("components") or []
    net_items = sch.get("nets") or []
    matched = [c for c in comps if _hits(c, designators, words, name_keys=("designator", "value", "footprint"))]
    shown_comps = (matched or comps)[:12]
    if shown_comps:
        label = "（与问题相关）" if matched else f"(前{len(shown_comps)}个)"
        comp_text = ", ".join(
            f"{c.get('designator', '?')}({c.get('value', '') or c.get('footprint', '')})" for c in shown_comps
        )
        lines.append(f"原理图元件{label}: {comp_text}")
    matched_nets = [n for n in net_items if _hits(n, designators, words, name_keys=("name",))]
    shown_nets = (matched_nets or net_items)[:12]
    if shown_nets:
        label = "（与问题相关）" if matched_nets else ""
        lines.append(f"网络{label}: " + ", ".join(f"{n.get('name')}({n.get('count')})" for n in shown_nets))
    errors = summary.get("errors") or []
    for e in errors[:3]:
        lines.append(f"注意: {e}")
    if len(comps) > 12 or len(net_items) > 12:
        lines.append("实时明细请用 altium_find_components / altium_find_nets 按需查询。")
    return "\n".join(lines)


def build_design_context(snapshot: dict[str, Any], max_components: int = 12, max_nets: int = 20,
                         *, query: str = "", max_chars: int = MAX_CONTEXT_CHARS) -> str:
    """快照 → 概览上下文。给出板级事实与「与当前问题相关」的对象，明细留给查询工具。"""
    if not snapshot:
        return ""
    designators, words = intent_terms(query)
    head: list[str] = []
    project = snapshot.get("project") or {}
    stats = snapshot.get("stats") or {}
    head.append(f"工程: {project.get('name', '?')}")
    head.append(
        f"规模: 元件 {stats.get('componentCount', '?')} / 网络 {stats.get('netCount', '?')} / BOM 行 {stats.get('bomRowCount', '?')}"
    )
    docs = snapshot.get("documents") or []
    if docs:
        head.append("文档: " + ", ".join(d.get("filename", "?") for d in docs[:8]))

    comps = snapshot.get("components") or []
    matched_comps = [c for c in comps if _hits(c, designators, words, name_keys=("designator", "value", "footprint"))]
    shown_comps = (matched_comps or comps)[:max_components]
    comp_section: list[str] = []
    if shown_comps:
        label = f"（命中 {len(matched_comps)} 个，与问题相关）" if matched_comps else f"（前 {len(shown_comps)} 个）"
        comp_section.append(f"元件{label}:")
        comp_section.extend(
            f"  - {c.get('designator', '?')}: value={c.get('value', '') or c.get('comment', '')} "
            f"footprint={c.get('footprint', '')}"
            for c in shown_comps
        )
        if len(comps) > len(shown_comps):
            comp_section.append(f"  （共 {len(comps)} 个元件，其余请用 find_components 查询）")

    net_section: list[str] = []
    nets = snapshot.get("nets") or []
    if nets:
        matched_nets = [n for n in nets if _hits(n, designators, words, name_keys=("name",))]
        pool = matched_nets or nets
        names = [n.get("name", "?") for n in pool]
        shown = ", ".join(names[:max_nets])
        more = f" …等共 {len(names)} 个" if len(names) > max_nets else ""
        label = "（与问题相关）" if matched_nets else ""
        net_section.append(f"网络{label}: {shown}{more}")
        single = [n.get("name", "?") for n in nets if _terminal_count(n) <= 1]
        if single:
            net_section.append(
                f"可疑单端网络({len(single)}): {', '.join(single[:15])}"
                + ("…" if len(single) > 15 else "（完整清单用 find_nets max_terminals=1）")
            )

    pcb_section: list[str] = []
    for pcb in snapshot.get("pcbs") or []:
        s = pcb.get("stats") or {}
        b = pcb.get("board") or {}
        pcb_section.append(
            f"PCB[{pcb.get('name', '?')}]: 元件 {s.get('components', '?')}, 焊盘 {s.get('pads', '?')}, "
            f"走线 {s.get('tracks', '?')}, 过孔 {s.get('vias', '?')}, 叠层 {b.get('layerStackupCount', '?')} 层"
        )
        rect = b.get("outlineRectMils")
        if rect and len(rect) == 4:
            w = rect[2] - rect[0]
            h = rect[3] - rect[1]
            pcb_section.append(f"  板框: {w:.1f} x {h:.1f} mil")

    bom_section: list[str] = []
    bom = snapshot.get("bom") or []
    if bom:
        matched_rows = [r for r in bom if _hits(r, designators, words, name_keys=("designator", "value", "footprint"))]
        pool = matched_rows or bom
        shown_rows = pool[:8]
        label = f"（命中 {len(matched_rows)} 行）" if matched_rows else f"（前 {len(shown_rows)} 行）"
        bom_section.append(f"BOM{label} / 共 {len(bom)} 行:")
        bom_section.extend(
            f"  - {row.get('designator', '?')} | {row.get('value', '')} | {row.get('footprint', '')}"
            + (" | DNP" if row.get("dnp") else "")
            for row in shown_rows
        )

    warning_section = [f"警告: {w}" for w in (snapshot.get("warnings") or [])[:5]]

    # 预算优先级：概览与告警必须保留，明细按 元件 → 网络 → BOM 顺序让步
    sections = [head, warning_section, pcb_section, comp_section, net_section, bom_section]
    lines: list[str] = []
    used = 0
    trimmed = False
    for section in sections:
        cost = sum(len(x) + 1 for x in section)
        if used + cost > max_chars:
            trimmed = True
            continue
        lines.extend(section)
        used += cost
    if trimmed or comps or nets or bom:
        lines.append(DISCLOSURE_HINT + ("（本次上下文已按预算裁剪）" if trimmed else ""))
    return "\n".join(lines)


def _terminal_count(net: dict[str, Any]) -> int:
    if isinstance(net.get("terminalCount"), int):
        return net["terminalCount"]
    terminals = net.get("terminals")
    return len(terminals) if isinstance(terminals, list) else 0
