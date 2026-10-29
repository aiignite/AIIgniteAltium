"""确定性设计审查：基于归一化快照的规则检查，结果可复现、不调用模型。"""

import re
from typing import Any

RULESET_VERSION = "p2.0"
MAX_REFS = 50
AUTO_NET_PATTERN = re.compile(r"^(N\$|Net[A-Za-z]*_?\d+$|Net\d+$)")

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
    component_designators = set(designators)
    bom_designators = {str(r.get("designator") or "?") for r in bom}
    net_names = [str(n.get("name") or "?") for n in nets]

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
        _finding("bom_missing_row", "warning", "元件缺少 BOM 行",
                 sorted(component_designators - bom_designators),
                 "BOM 中找不到对应位号，导出的采购与贴装清单将遗漏该元件"),
        _finding("bom_orphan_row", "warning", "BOM 行缺少元件",
                 sorted(bom_designators - component_designators),
                 "BOM 中的位号在元件列表中不存在，可能来自过期或未同步的 BOM"),
        _finding("single_terminal_net", "warning", "单端网络",
                 [str(n.get("name") or "?") for n in nets if _terminal_count(n) <= 1],
                 "仅一个连接端子的网络通常是悬空或未完成布线"),
        _finding("net_auto_named", "info", "自动命名网络",
                 [name for name in net_names if AUTO_NET_PATTERN.match(name)],
                 "默认网络名通常表示未手动命名，建议确认连接关系与可读性"),
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
            continue
        if rect[0] != 0 or rect[1] != 0:
            findings.append(_finding("board_outline_off_origin", "info", "板框未对齐原点", [name],
                                     f"板框起点为 ({rect[0]}, {rect[1]}) mil，建议对齐原点以便制造与拼板"))

    return sorted((f for f in findings if f), key=lambda f: SEVERITY_ORDER.get(f["severity"], 9))


def summarize(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"error": 0, "warning": 0, "info": 0}
    for finding in findings:
        counts[finding["severity"]] = counts.get(finding["severity"], 0) + 1
    return counts


SEVERITY_LABELS = {"error": "错误", "warning": "警告", "info": "提示"}


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip() or "-"


def report_markdown(
    project_name: str,
    *,
    snapshot_version: int,
    ruleset_version: str,
    counts: dict[str, int],
    findings: list[dict[str, Any]],
    created_at: str,
) -> str:
    lines = [
        f"# {project_name} 设计审查报告",
        "",
        f"- 工程：{project_name}",
        f"- 快照版本：v{snapshot_version}",
        f"- 规则集：{ruleset_version}",
        f"- 审查时间：{created_at}",
        f"- 结论：错误 {counts.get('error', 0)}、警告 {counts.get('warning', 0)}、提示 {counts.get('info', 0)}",
        "",
        "## 审查结果",
        "",
    ]
    if not findings:
        lines.append("未发现问题。")
    else:
        lines.extend(["| 级别 | 问题 | 规则 | 对象 | 说明 |", "| --- | --- | --- | --- | --- |"])
        for finding in findings:
            refs = finding.get("refs") or []
            ref_text = "、".join(refs)
            if finding.get("count", len(refs)) > len(refs):
                ref_text += f"（共 {finding['count']} 项）"
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(SEVERITY_LABELS.get(finding.get("severity"), finding.get("severity"))),
                        _cell(finding.get("title")),
                        _cell(finding.get("rule")),
                        _cell(ref_text),
                        _cell(finding.get("detail")),
                    ]
                )
                + " |"
            )
    lines.extend(
        [
            "",
            "## 说明",
            "",
            "本报告由平台基于离线解析快照的确定性规则生成，不调用模型；规则结果可复现。",
            "请结合原理图/PCB 实际连接与设计要求确认整改方案。",
            "",
        ]
    )
    return "\n".join(lines)
