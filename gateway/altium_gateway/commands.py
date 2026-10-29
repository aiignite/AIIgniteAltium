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

    def build_ops(self, params: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        return [(self.op_name, params)]


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
