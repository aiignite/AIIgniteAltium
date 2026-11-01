"""命令层（ADR-001）：语义化命令 → 桥 ops 的确定性编译。

v1 全部为只读查询命令（requires_confirmation=False）；写命令自 M5 起
按同一注册表扩展，必须携带 requires_confirmation=True 与 dry_run 实现。
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Callable

from .drivers.base import AltiumDriver


@dataclass
class CommandDef:
    name: str
    title: str
    description: str
    op_name: str
    category: str = "query"
    requires_confirmation: bool = False
    params_schema: dict[str, Any] = field(default_factory=dict)
    # 语义查询命令：复用现有只读桥 op，在网关侧过滤/截断（不改 DelphiScript 协议）
    post_filter: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None
    op_selector: Callable[[dict[str, Any]], str] | None = None

    def resolve_op(self, params: dict[str, Any]) -> str:
        return self.op_selector(params) if self.op_selector else self.op_name

    def build_ops(self, params: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        if self.post_filter is not None:
            return [(self.resolve_op(params), {})]
        return [(self.resolve_op(params), params)]


_DEFAULT_LIMIT = 20
_MAX_LIMIT = 60


def _text(value: Any) -> str:
    return str(value if value is not None else "").strip()


def _matched(haystack: str, needle: str) -> bool:
    return not needle or needle.lower() in haystack.lower()


def _limit(value: Any) -> int:
    try:
        size = int(value) if value is not None else _DEFAULT_LIMIT
    except (TypeError, ValueError):
        size = _DEFAULT_LIMIT
    return max(1, min(size, _MAX_LIMIT))


def _optional(**specs: dict[str, Any]) -> dict[str, Any]:
    return {key: {**value, "required": False} for key, value in specs.items()}


def _page(payload: dict[str, Any], rows: list[dict[str, Any]], size: int, filters: dict[str, Any]) -> dict[str, Any]:
    """语义查询统一信封：保留桥原始字段，追加匹配数与截断标记。"""
    if not payload.get("ok"):
        return payload
    out = dict(payload)
    out["items"] = rows[:size]
    out["matched"] = len(rows)
    out["returned"] = min(len(rows), size)
    out["truncated"] = len(rows) > size
    out["filters"] = filters
    if out["truncated"]:
        out["hint"] = "结果已截断，请收紧过滤条件或提高 limit"
    return out


def _filter_components(payload: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    designator = _text(params.get("designator"))
    value = _text(params.get("value"))
    footprint = _text(params.get("footprint"))
    rows = [
        dict(item) for item in (payload.get("items") or [])
        if isinstance(item, dict)
        and _matched(_text(item.get("designator")), designator)
        and _matched(_text(item.get("value")), value)
        and _matched(_text(item.get("footprint")), footprint)
    ]
    return _page(payload, rows, _limit(params.get("limit")),
                 {"designator": designator, "value": value, "footprint": footprint})


def _net_terminals(item: dict[str, Any]) -> int:
    for key in ("count", "terminalCount"):
        if isinstance(item.get(key), int):
            return item[key]
    terminals = item.get("terminals")
    return len(terminals) if isinstance(terminals, list) else 0


def _filter_nets(payload: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    name = _text(params.get("name"))
    rows = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        terminals = _net_terminals(item)
        if not _matched(_text(item.get("name")), name):
            continue
        if params.get("min_terminals") is not None and terminals < int(params["min_terminals"]):
            continue
        if params.get("max_terminals") is not None and terminals > int(params["max_terminals"]):
            continue
        row = dict(item)
        row["terminalCount"] = terminals
        rows.append(row)
    return _page(payload, rows, _limit(params.get("limit")),
                 {"name": name, "minTerminals": params.get("min_terminals"),
                  "maxTerminals": params.get("max_terminals")})


def _component_scope(params: dict[str, Any]) -> str:
    return "pcb_components" if _text(params.get("scope")).lower() == "pcb" else "sch_components"


COMMANDS: dict[str, CommandDef] = {
    "altium_ping": CommandDef(
        name="altium_ping",
        title="连通性测试",
        description="检查 Altium 内 AIDriveBridge 驻留脚本是否在线",
        op_name="ping",
        params_schema={},
    ),
    "altium_get_project_info": CommandDef(
        name="altium_get_project_info",
        title="当前工程信息",
        description="获取 Altium 中当前打开的工程名称、路径与活动文档",
        op_name="get_project_info",
        params_schema={},
    ),
    "altium_get_schematic_components": CommandDef(
        name="altium_get_schematic_components",
        title="原理图元件清单",
        description="列出当前原理图文档的元件（位号/值/封装）",
        op_name="sch_components",
        params_schema={},
    ),
    "altium_get_schematic_nets": CommandDef(
        name="altium_get_schematic_nets",
        title="原理图网络清单",
        description="列出当前原理图的网络标签/电源端口及连接计数",
        op_name="sch_nets",
        params_schema={},
    ),
    "altium_get_pcb_components": CommandDef(
        name="altium_get_pcb_components",
        title="PCB 元件清单",
        description="列出当前 PCB 文档的元件与所在层",
        op_name="pcb_components",
        params_schema={},
    ),
    "altium_get_pcb_stats": CommandDef(
        name="altium_get_pcb_stats",
        title="PCB 统计",
        description="当前 PCB 的元件/焊盘/走线/过孔/网络计数与板框尺寸、叠层数",
        op_name="pcb_stats",
        params_schema={},
    ),
    "altium_get_stackup": CommandDef(
        name="altium_get_stackup",
        title="叠层信息",
        description="当前 PCB 的板层名称列表",
        op_name="get_stackup",
        params_schema={},
    ),
    "altium_take_screenshot": CommandDef(
        name="altium_take_screenshot",
        title="截图",
        description="截取 Altium 当前文档窗口画面（供多模态模型查看）",
        op_name="take_screenshot",
        params_schema={},
    ),
    "altium_find_components": CommandDef(
        name="altium_find_components",
        title="按条件查元件",
        description=(
            "在当前 Altium 原理图或 PCB 中按位号/值/封装片段查询元件（scope=sch|pcb，默认 sch）。"
            "大设计请用它按需取明细，不要请求全量清单"
        ),
        op_name="sch_components",
        params_schema=_optional(
            designator={"type": "str", "description": "位号包含的片段，如 U、R1"},
            value={"type": "str", "description": "值/型号包含的片段"},
            footprint={"type": "str", "description": "封装包含的片段"},
            scope={"type": "str", "description": "查询范围：sch（默认）或 pcb"},
            limit={"type": "int", "description": "最多返回条数，默认 20，上限 60"},
        ),
        post_filter=_filter_components,
        op_selector=_component_scope,
    ),
    "altium_find_nets": CommandDef(
        name="altium_find_nets",
        title="按条件查网络",
        description=(
            "在当前 Altium 原理图中按网络名片段与端子数查询网络；"
            "max_terminals=1 用于找单端/悬空网络"
        ),
        op_name="sch_nets",
        params_schema=_optional(
            name={"type": "str", "description": "网络名包含的片段，如 USB、GND"},
            min_terminals={"type": "int", "description": "最小连接端子数"},
            max_terminals={"type": "int", "description": "最大连接端子数"},
            limit={"type": "int", "description": "最多返回条数，默认 20，上限 60"},
        ),
        post_filter=_filter_nets,
    ),
    "altium_highlight_net": CommandDef(
        name="altium_highlight_net",
        title="高亮网络",
        description="在 PCB 中高亮或取消高亮指定网络（仅视觉高亮，不修改设计）",
        op_name="pcb_highlight_net",
        category="write",
        requires_confirmation=True,
        params_schema={"net": "str", "mode": "int"},
    ),
    "altium_move_component": CommandDef(
        name="altium_move_component",
        title="移动元件",
        description="按位号将 PCB 元件移动到指定坐标（x/y 单位 mils）",
        op_name="pcb_move_component",
        category="write",
        requires_confirmation=True,
        params_schema={"designator": "str", "x": "int", "y": "int"},
    ),
    "altium_rotate_component": CommandDef(
        name="altium_rotate_component",
        title="旋转元件",
        description="按位号将 PCB 元件旋转到指定角度（单位：度，0-360）",
        op_name="pcb_rotate_component",
        category="write",
        requires_confirmation=True,
        params_schema={"designator": "str", "rotation": "int"},
    ),
}


def list_commands() -> list[dict[str, Any]]:
    return [
        {
            "name": c.name,
            "title": c.title,
            "description": c.description,
            "category": c.category,
            "requiresConfirmation": c.requires_confirmation,
            "paramsSchema": c.params_schema,
        }
        for c in COMMANDS.values()
    ]


def _post_process(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """live 模式截图返回 BMP 文件路径：转 PNG data URI 并清理。"""
    if name == "altium_take_screenshot" and payload.get("ok") and payload.get("file"):
        from pathlib import Path

        file_path = Path(str(payload["file"]))
        try:
            from PIL import Image

            with Image.open(file_path) as img:
                img.save(file_path.with_suffix(".png"), "PNG")
            raw = file_path.with_suffix(".png").read_bytes()
            payload["format"] = "png"
            payload["data"] = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
        except Exception as exc:  # Pillow 缺失时回退返回原始路径
            payload["error"] = f"BMP→PNG 转换失败: {exc}"
        finally:
            try:
                file_path.unlink(missing_ok=True)
                file_path.with_suffix(".png").unlink(missing_ok=True)
            except OSError:
                pass
    return payload


_CONTROL_KEYS = {"dry_run", "dryRun", "confirmed", "confirm"}


def _find_component(driver: AltiumDriver, designator: str) -> dict[str, Any] | None:
    """通过只读 pcb_components 查询定位元件（dry-run 预览用）。"""
    results = driver.execute([("pcb_components", {})])
    payload = results[0] if results else {}
    if not payload.get("ok"):
        return None
    target = designator.upper()
    for item in payload.get("items", []):
        if str(item.get("designator", "")).upper() == target:
            return item
    return None


def _dry_run(cmd: CommandDef, driver: AltiumDriver, params: dict[str, Any]) -> dict[str, Any]:
    """写命令 dry-run：参数校验；move/rotate 额外查询当前状态生成具体预览。"""
    name = cmd.name
    if name == "altium_highlight_net":
        net = str(params.get("net") or "").strip()
        if not net:
            return {"ok": False, "command": name, "dryRun": True, "error": "缺少参数 net（网络名）"}
        mode = 1 if str(params.get("mode", 1)) != "0" else 0
        action = "高亮" if mode else "取消高亮"
        return {
            "ok": True,
            "command": name,
            "dryRun": True,
            "preview": f"{action} PCB 网络 '{net}'（仅视觉，不修改设计）",
            "params": {"net": net, "mode": mode},
        }
    if name in ("altium_move_component", "altium_rotate_component"):
        designator = str(params.get("designator") or "").strip()
        if not designator:
            return {"ok": False, "command": name, "dryRun": True, "error": "缺少参数 designator（位号）"}
        comp = _find_component(driver, designator)
        if comp is None:
            return {"ok": False, "command": name, "dryRun": True, "error": f"当前 PCB 中未找到元件 {designator}"}
        if name == "altium_move_component":
            x, y = params.get("x"), params.get("y")
            if x is None or y is None:
                return {"ok": False, "command": name, "dryRun": True, "error": "缺少参数 x/y（单位 mils）"}
            preview = (
                f"将元件 {designator} 从 ({comp.get('x', '?')}mils, {comp.get('y', '?')}mils) "
                f"移动到 ({x}mils, {y}mils)"
            )
        else:
            rot = params.get("rotation")
            if rot is None:
                return {"ok": False, "command": name, "dryRun": True, "error": "缺少参数 rotation（单位：度）"}
            preview = f"将元件 {designator} 从 {comp.get('rotation', '?')}° 旋转到 {rot}°"
        return {
            "ok": True,
            "command": name,
            "dryRun": True,
            "preview": preview,
            "params": dict(params),
            "current": comp,
        }
    return {"ok": False, "command": name, "dryRun": True, "error": "该命令不支持 dry-run"}


def execute_command(driver: AltiumDriver, name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    cmd = COMMANDS.get(name)
    if cmd is None:
        return {"ok": False, "error": f"未知命令: {name}"}
    params = params or {}
    if cmd.requires_confirmation:
        if params.get("dry_run") or params.get("dryRun"):
            return _dry_run(cmd, driver, params)
        if not (params.get("confirmed") or params.get("confirm")):
            return {
                "ok": False,
                "command": name,
                "requiresConfirmation": True,
                "error": f"写命令 {name} 需确认：请先带 dry_run=true 预览，再带 confirmed=true 执行",
            }
    exec_params = {k: v for k, v in params.items() if k not in _CONTROL_KEYS}
    ops = cmd.build_ops(exec_params)
    results = driver.execute(ops)
    payload = results[0] if results else {"ok": False, "error": "no result"}
    if cmd.post_filter is not None and isinstance(payload, dict):
        payload = cmd.post_filter(payload, exec_params)
    payload["command"] = name
    return _post_process(name, payload)


def build_live_summary(driver: AltiumDriver) -> dict[str, Any]:
    """聚合一条给 LLM 的实时设计摘要（单一桥事务内批量查询）。"""
    ops = [
        ("get_project_info", {}),
        ("pcb_stats", {}),
        ("sch_nets", {}),
        ("sch_components", {}),
    ]
    results = driver.execute(ops)
    info, stats, nets, comps = (results + [{}]*4)[:4]

    def ok(r: dict[str, Any]) -> bool:
        return isinstance(r, dict) and r.get("ok")

    summary: dict[str, Any] = {
        "ok": all(ok(r) for r in (info, stats)),
        "project": info.get("name") if ok(info) else None,
        "document": {"kind": info.get("document_kind"), "name": info.get("document_name")} if ok(info) else None,
        "pcbStats": {k: stats.get(k) for k in ("components", "pads", "tracks", "vias", "nets")} if ok(stats) else None,
        "board": {
            "widthMils": (stats.get("right", 0) - stats.get("left", 0)) if ok(stats) else None,
            "heightMils": (stats.get("top", 0) - stats.get("bottom", 0)) if ok(stats) else None,
            "layers": stats.get("layers") if ok(stats) else None,
        },
        "schematic": {
            "componentCount": comps.get("count") if ok(comps) else None,
            "components": comps.get("items", [])[:15] if ok(comps) else [],
            "netCount": nets.get("count") if ok(nets) else None,
            "nets": nets.get("items", [])[:15] if ok(nets) else [],
        },
        "errors": [r.get("error") for r in results if isinstance(r, dict) and not r.get("ok")],
    }
    return summary
