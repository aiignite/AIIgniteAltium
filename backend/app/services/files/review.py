"""确定性设计审查：基于归一化快照的规则检查，结果可复现、不调用模型。"""

from typing import Any

RULESET_VERSION = "p1.1"
MAX_REFS = 50

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def _refs(values: list[str], limit: int = MAX_REFS) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
        if len(seen) >= limit:
            break
    return seen


def _finding(rule: str, severity: str, title: str, refs: list[str], detail: str = "") -> dict[str, Any] | None:
    unique = _refs(refs)
    if not unique:
        return None
    return {"rule": rule, "severity": severity, "title": title, "detail": detail, "refs": unique, "count": len(refs)}


def _terminal_count(net: dict[str, Any]) -> int:
    if isinstance(net.get("terminalCount"), int):
        return net["terminalCount"]
    terminals = net.get("terminals")
    return len(terminals) if isinstance(terminals, list) else 0


def review_snapshot(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    snapshot = snapshot or {}
    components = [c for c in snapshot.get("components") or [] if isinstance(c, dict)]
    nets = [n for n in snapshot.get("nets") or [] if isinstance(n, dict)]
    bom = [r for r in snapshot.get("bom") or [] if isinstance(r, dict)]
    pcbs = [p for p in snapshot.get("pcbs") or [] if isinstance(p, dict)]
    warnings = [str(w) for w in snapshot.get("warnings") or []]

    designators = [str(c.get("designator") or "?") for c in components]
    counts: dict[str, int] = {}
    for designator in designators:
        counts[designator] = counts.get(designator, 0) + 1

    findings = [
        _finding("no_components", "warning", "快照未包含元件", [] if components else ["snapshot"],
                 "无法执行元件级检查，请确认原理图已成功解析"),
        _finding("duplicate_designator", "error", "位号重复",
                 [d for d in counts if counts[d] > 1], "同一工程内多个元件使用相同位号"),
        _finding("missing_footprint", "warning", "元件缺少封装",
                 [str(c.get("designator") or "?") for c in components if not str(c.get("footprint") or "").strip()],
                 "缺少封装将影响 PCB 布局与 BOM 准确性"),
        _finding("missing_value", "warning", "元件缺少值/型号",
                 [str(c.get("designator") or "?") for c in components
                  if not str(c.get("value") or c.get("comment") or "").strip()],
                 "建议补充值或型号，便于 BOM 与替代料管理"),
        _finding("single_terminal_net", "warning", "单端网络",
                 [str(n.get("name") or "?") for n in nets if _terminal_count(n) <= 1],
                 "仅一个连接端子的网络通常是悬空或未完成布线"),
        _finding("dnp_bom_rows", "info", "BOM 含 DNP 行",
                 [str(r.get("designator") or "?") for r in bom if r.get("dnp")],
                 "DNP 元件不参与贴装，请确认是否符合预期"),
        _finding("parse_warnings", "info", "解析告警", warnings, "解析过程中出现降级或告警，结果可能不完整"),
    ]

    for pcb in pcbs:
        name = str(pcb.get("name") or "?")
        rect = (pcb.get("board") or {}).get("outlineRectMils")
        if not isinstance(rect, list) or len(rect) != 4:
            findings.append(_finding("board_outline_missing", "warning", "缺少板框", [name],
                                     "PCB 未检测到矩形板框，尺寸与布局检查不可用"))
            continue
        width, height = rect[2] - rect[0], rect[3] - rect[1]
        if width <= 0 or height <= 0:
            findings.append(_finding("board_outline_invalid", "error", "板框尺寸无效", [name],
                                     f"板框宽高为 {width} x {height} mil"))

    return sorted((f for f in findings if f), key=lambda f: SEVERITY_ORDER.get(f["severity"], 9))


def summarize(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"error": 0, "warning": 0, "info": 0}
    for finding in findings:
        counts[finding["severity"]] = counts.get(finding["severity"], 0) + 1
    return counts
