"""离线设计快照查询工具（渐进披露第二层）。

系统提示词只给概览，明细由模型通过这些工具按需拉取：避免整板数据一次性入 prompt，
也避免模型在看不见对象的情况下猜测位号/网络。所有查询都限定在当前对话关联的工程，
并按所有者校验（``get_owned_project``），模型无法指定工程 ID 或地址。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select

from app.ai_tools import ToolContext, current_tool_context

DEFAULT_LIMIT = 20
MAX_LIMIT = 60
PREVIEW_TERMINALS = 6

OPTIONAL = {"required": False}


def _text(value: Any) -> str:
    return str(value if value is not None else "").strip()


def _matched(haystack: str, needle: str) -> bool:
    return not needle or needle.lower() in haystack.lower()


def _limit(value: Any) -> int:
    try:
        size = int(value) if value is not None else DEFAULT_LIMIT
    except (TypeError, ValueError):
        size = DEFAULT_LIMIT
    return max(1, min(size, MAX_LIMIT))


async def _snapshot(context: ToolContext) -> tuple[dict[str, Any], str, UUID]:
    from app.database import async_session_maker
    from app.services.files.access import get_owned_project

    if context.project_id is None or context.user_id is None:
        return {}, "当前对话未关联离线工程，无法查询设计数据", UUID(int=0)
    async with async_session_maker() as db:
        try:
            project = await get_owned_project(db, context.project_id, context.user_id)
        except HTTPException as exc:
            return {}, f"工程不可访问：{exc.detail}", UUID(int=0)
        snapshot = project.snapshot or {}
        if not snapshot:
            return {}, "工程尚未解析完成，暂无可查询的快照数据", project.id
        return snapshot, "", project.id


def _as_list(snapshot: dict[str, Any], key: str) -> list[dict[str, Any]]:
    rows = snapshot.get(key)
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _envelope(items: list[dict[str, Any]], limit: int, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "success": True,
        "matched": len(items),
        "returned": min(len(items), limit),
        "items": items[:limit],
        "truncated": len(items) > limit,
    }
    if extra:
        payload.update(extra)
    if payload["truncated"]:
        payload["hint"] = "结果已截断，请收紧过滤条件或提高 limit"
    return payload


async def find_components(*, designator: str = "", value: str = "", footprint: str = "",
                         missing_footprint: bool = False, missing_value: bool = False,
                         limit: int = DEFAULT_LIMIT, **_ignored: Any) -> dict[str, Any]:
    snapshot, error, _ = await _snapshot(current_tool_context())
    if error:
        return {"success": False, "error": error}
    rows = []
    for c in _as_list(snapshot, "components"):
        des = _text(c.get("designator"))
        val = _text(c.get("value") or c.get("comment"))
        fp = _text(c.get("footprint"))
        if not _matched(des, designator) or not _matched(val, value) or not _matched(fp, footprint):
            continue
        if missing_footprint and fp:
            continue
        if missing_value and val:
            continue
        rows.append({"designator": des, "value": val, "footprint": fp,
                     "description": _text(c.get("description")), "sheet": _text(c.get("sheet"))})
    return _envelope(rows, _limit(limit), {"filters": {
        "designator": designator, "value": value, "footprint": footprint,
        "missingFootprint": bool(missing_footprint), "missingValue": bool(missing_value)}})


async def get_component(*, designator: str, **_ignored: Any) -> dict[str, Any]:
    snapshot, error, _ = await _snapshot(current_tool_context())
    if error:
        return {"success": False, "error": error}
    target = _text(designator).upper()
    component = next((c for c in _as_list(snapshot, "components")
                      if _text(c.get("designator")).upper() == target), None)
    if component is None:
        return {"success": False, "error": f"快照中没有位号 {designator}"}
    connections = []
    for net in _as_list(snapshot, "nets"):
        for t in net.get("terminals") or []:
            if isinstance(t, dict) and _text(t.get("designator")).upper() == target:
                connections.append({"net": _text(net.get("name")), "pin": _text(t.get("pin")),
                                    "pinName": _text(t.get("pinName")), "pinType": _text(t.get("pinType")),
                                    "netTerminalCount": _net_terminal_count(net)})
    bom = next((b for b in _as_list(snapshot, "bom")
                if _text(b.get("designator")).upper() == target), None)
    return {"success": True, "component": component, "connections": connections,
            "connectionCount": len(connections), "bomRow": bom,
            "singlePinNets": [c["net"] for c in connections if c["netTerminalCount"] <= 1]}


def _net_terminal_count(net: dict[str, Any]) -> int:
    if isinstance(net.get("terminalCount"), int):
        return net["terminalCount"]
    terminals = net.get("terminals")
    return len(terminals) if isinstance(terminals, list) else 0


async def find_nets(*, name: str = "", min_terminals: int | None = None,
                    max_terminals: int | None = None, limit: int = DEFAULT_LIMIT,
                    **_ignored: Any) -> dict[str, Any]:
    snapshot, error, _ = await _snapshot(current_tool_context())
    if error:
        return {"success": False, "error": error}
    rows = []
    for net in _as_list(snapshot, "nets"):
        net_name = _text(net.get("name"))
        count = _net_terminal_count(net)
        if not _matched(net_name, name):
            continue
        if min_terminals is not None and count < int(min_terminals):
            continue
        if max_terminals is not None and count > int(max_terminals):
            continue
        terminals = [t for t in (net.get("terminals") or []) if isinstance(t, dict)]
        rows.append({"name": net_name, "terminalCount": count,
                     "terminals": [_text(t.get("designator")) for t in terminals[:PREVIEW_TERMINALS]]})
    return _envelope(rows, _limit(limit), {"filters": {"name": name, "minTerminals": min_terminals,
                                                       "maxTerminals": max_terminals}})


async def get_net(*, name: str, **_ignored: Any) -> dict[str, Any]:
    snapshot, error, _ = await _snapshot(current_tool_context())
    if error:
        return {"success": False, "error": error}
    target = _text(name).upper()
    net = next((n for n in _as_list(snapshot, "nets") if _text(n.get("name")).upper() == target), None)
    if net is None:
        close = [_text(n.get("name")) for n in _as_list(snapshot, "nets")
                 if target and target[:3] in _text(n.get("name")).upper()][:8]
        message = f"快照中没有网络 {name}"
        if close:
            message += f"，相近网络：{', '.join(close)}"
        return {"success": False, "error": message}
    terminals = [t for t in (net.get("terminals") or []) if isinstance(t, dict)]
    return {"success": True, "name": _text(net.get("name")), "terminalCount": _net_terminal_count(net),
            "terminals": [{"designator": _text(t.get("designator")), "pin": _text(t.get("pin")),
                           "pinName": _text(t.get("pinName")), "pinType": _text(t.get("pinType"))}
                          for t in terminals[:MAX_LIMIT]],
            "returned": min(len(terminals), MAX_LIMIT), "truncated": len(terminals) > MAX_LIMIT}


async def get_bom_rows(*, designator: str = "", value: str = "", footprint: str = "",
                       dnp_only: bool = False, limit: int = DEFAULT_LIMIT, **_ignored: Any) -> dict[str, Any]:
    snapshot, error, _ = await _snapshot(current_tool_context())
    if error:
        return {"success": False, "error": error}
    rows = []
    for b in _as_list(snapshot, "bom"):
        des = _text(b.get("designator"))
        val = _text(b.get("value"))
        fp = _text(b.get("footprint"))
        if not _matched(des, designator) or not _matched(val, value) or not _matched(fp, footprint):
            continue
        if dnp_only and not b.get("dnp"):
            continue
        rows.append({"designator": des, "value": val, "footprint": fp, "dnp": bool(b.get("dnp"))})
    return _envelope(rows, _limit(limit), {"filters": {"designator": designator, "value": value,
                                                       "footprint": footprint, "dnpOnly": bool(dnp_only)}})


async def get_review_findings(*, rule: str = "", severity: str = "", designator: str = "",
                              limit: int = DEFAULT_LIMIT, **_ignored: Any) -> dict[str, Any]:
    """最近一次确定性审查结果；没有记录时按同一规则集即时计算（不落库、不调用模型）。"""
    from app.database import async_session_maker
    from app.models.files.review_run import ReviewRun
    from app.services.files.review import RULESET_VERSION, review_snapshot

    context = current_tool_context()
    snapshot, error, project_id = await _snapshot(context)
    if error:
        return {"success": False, "error": error}
    source = "latest_run"
    async with async_session_maker() as db:
        run = (await db.execute(
            select(ReviewRun).where(ReviewRun.project_id == project_id).order_by(ReviewRun.created_at.desc()).limit(1)
        )).scalars().first()
    if run is not None:
        findings, ruleset = run.findings or [], run.ruleset_version
    else:
        findings, ruleset, source = review_snapshot(snapshot), RULESET_VERSION, "computed"

    rows = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        refs = [_text(r) for r in (f.get("refs") or [])]
        if rule and _text(f.get("rule")).lower() != rule.lower():
            continue
        if severity and _text(f.get("severity")).lower() != severity.lower():
            continue
        if designator and designator.upper() not in [r.upper() for r in refs]:
            continue
        rows.append({"rule": _text(f.get("rule")), "severity": _text(f.get("severity")),
                     "title": _text(f.get("title")), "detail": _text(f.get("detail")),
                     "count": f.get("count", len(refs)), "refs": refs[:20]})
    return _envelope(rows, _limit(limit), {"rulesetVersion": ruleset, "source": source})


_SCHEMAS: dict[str, dict[str, Any]] = {
    "find_components": {
        "designator": {**OPTIONAL, "type": "string", "description": "位号包含的片段，如 R1、C"},
        "value": {**OPTIONAL, "type": "string", "description": "值/型号包含的片段"},
        "footprint": {**OPTIONAL, "type": "string", "description": "封装包含的片段"},
        "missing_footprint": {**OPTIONAL, "type": "boolean", "description": "只返回缺少封装的元件"},
        "missing_value": {**OPTIONAL, "type": "boolean", "description": "只返回缺少值/型号的元件"},
        "limit": {**OPTIONAL, "type": "integer", "description": "最多返回条数，默认 20，上限 60"},
    },
    "get_component": {"designator": {"type": "string", "description": "完整位号，如 C12"}},
    "find_nets": {
        "name": {**OPTIONAL, "type": "string", "description": "网络名包含的片段，如 VCC、SPI"},
        "min_terminals": {**OPTIONAL, "type": "integer", "description": "最小连接端子数"},
        "max_terminals": {**OPTIONAL, "type": "integer", "description": "最大连接端子数（找单端/悬空网络用 1）"},
        "limit": {**OPTIONAL, "type": "integer", "description": "最多返回条数，默认 20，上限 60"},
    },
    "get_net": {"name": {"type": "string", "description": "完整网络名"}},
    "get_bom_rows": {
        "designator": {**OPTIONAL, "type": "string", "description": "位号包含的片段"},
        "value": {**OPTIONAL, "type": "string", "description": "值包含的片段"},
        "footprint": {**OPTIONAL, "type": "string", "description": "封装包含的片段"},
        "dnp_only": {**OPTIONAL, "type": "boolean", "description": "只返回 DNP 行"},
        "limit": {**OPTIONAL, "type": "integer", "description": "最多返回条数，默认 20，上限 60"},
    },
    "get_review_findings": {
        "rule": {**OPTIONAL, "type": "string", "description": "规则 ID，如 single_terminal_net"},
        "severity": {**OPTIONAL, "type": "string", "description": "error / warning / info"},
        "designator": {**OPTIONAL, "type": "string", "description": "只看涉及该位号/网络的条目"},
        "limit": {**OPTIONAL, "type": "integer", "description": "最多返回条数，默认 20，上限 60"},
    },
}

_DESCRIPTIONS = {
    "find_components": "按位号/值/封装过滤查询离线快照元件列表（工程规模大时优先用它，而不是要求全量数据）",
    "get_component": "查询单个元件的完整信息：属性、所在网络与引脚、对应 BOM 行",
    "find_nets": "按网络名片段与端子数过滤查询网络列表；max_terminals=1 可找出单端/悬空网络",
    "get_net": "查询单个网络的完整连接明细（引脚级），网络名支持模糊提示",
    "get_bom_rows": "按位号/值/封装/DNP 过滤查询 BOM 行",
    "get_review_findings": "读取本工程的确定性审查结果（可按规则/级别/位号过滤），回答设计问题时优先引用它",
}


def register_design_tools(registry) -> None:  # noqa: ANN001 - 接收 ToolRegistry 实例，避免循环导入注解
    handlers = {
        "find_components": find_components,
        "get_component": get_component,
        "find_nets": find_nets,
        "get_net": get_net,
        "get_bom_rows": get_bom_rows,
        "get_review_findings": get_review_findings,
    }
    for name, handler in handlers.items():
        if registry.get(name) is not None:
            continue
        registry.register(
            name=name,
            description=_DESCRIPTIONS[name],
            category="design",
            handler=handler,
            params_schema=_SCHEMAS[name],
        )
