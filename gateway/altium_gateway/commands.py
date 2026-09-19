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
}


def list_commands() -> list[dict[str, Any]]:
    return [
        {
            "name": c.name,
            "title": c.title,
            "description": c.description,
            "category": c.category,
            "requiresConfirmation": c.requires_confirmation,
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


def execute_command(driver: AltiumDriver, name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    cmd = COMMANDS.get(name)
    if cmd is None:
        return {"ok": False, "error": f"未知命令: {name}"}
    ops = cmd.build_ops(params or {})
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
