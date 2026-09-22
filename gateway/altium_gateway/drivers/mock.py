"""mock 驱动：内置演示数据（jlink 风格），供无 Altium 环境开发联调与演示。"""

import base64
import time
from typing import Any

from .base import AltiumDriver

_STARTED_AT = time.time()

_MOCK_COMPONENTS = [
    {"designator": "U1", "value": "AMS1117 3.3", "footprint": "SOT-223"},
    {"designator": "U2", "value": "STM32F103C8T6", "footprint": "LQFP48_N"},
    {"designator": "Y1", "value": "8MHz", "footprint": "JZ"},
    {"designator": "OUT1", "value": "SWD", "footprint": "HDR1X4"},
    {"designator": "USB_Mini", "value": "USB", "footprint": "USB Mini"},
]

_MOCK_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
<rect width="640" height="360" fill="#101418"/>
<text x="20" y="40" fill="#7ee787" font-family="monospace" font-size="20">AIDriveAltium MOCK</text>
<rect x="40" y="80" width="160" height="120" fill="#1f6feb" opacity="0.8"/>
<rect x="240" y="80" width="160" height="120" fill="#238636" opacity="0.8"/>
<rect x="440" y="80" width="160" height="120" fill="#bf3989" opacity="0.8"/>
<text x="70" y="150" fill="#fff" font-family="monospace">U2 MCU</text>
<text x="270" y="150" fill="#fff" font-family="monospace">U1 LDO</text>
<text x="470" y="150" fill="#fff" font-family="monospace">Y1 XTAL</text>
<text x="20" y="330" fill="#8b949e" font-family="monospace" font-size="14">mock screenshot at {t}</text>
</svg>"""


def _svg_png_data_uri() -> str:
    raw = _MOCK_SVG.format(t=int(time.time() - _STARTED_AT)).encode("utf-8")
    return "data:image/svg+xml;base64," + base64.b64encode(raw).decode("ascii")


class MockAltiumDriver(AltiumDriver):
    def execute(self, ops: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
        return [self._run(op, params) for op, params in ops]

    def _run(self, op: str, params: dict[str, Any]) -> dict[str, Any]:
        if op == "ping":
            return {"ok": True, "reply": "PONG", "driver": "mock"}
        if op == "get_project_info":
            return {
                "ok": True,
                "name": "Mock JLink Demo",
                "path": "C:\\Demo\\MockJLink.PrjPcb",
                "document_kind": "PCB",
                "document_name": "mock_pcb.PcbDoc",
                "server_online": True,
            }
        if op == "sch_components":
            return {"ok": True, "count": len(_MOCK_COMPONENTS), "items": [dict(c) for c in _MOCK_COMPONENTS], "document": "mock_sch.SchDoc"}
        if op == "sch_nets":
            nets = [
                {"name": "VCC", "count": 14},
                {"name": "GND", "count": 22},
                {"name": "USB_DP", "count": 2},
                {"name": "USB_DM", "count": 2},
                {"name": "NetC4_1", "count": 1},
            ]
            return {"ok": True, "count": len(nets), "items": nets, "document": "mock_sch.SchDoc"}
        if op == "pcb_components":
            items = []
            for i, c in enumerate(_MOCK_COMPONENTS):
                item = dict(c)
                item["x"] = 2000 + i * 400
                item["y"] = 1500 + i * 300
                item["rotation"] = (i * 90) % 360
                items.append(item)
            return {"ok": True, "count": len(items), "items": items, "document": "mock_pcb.PcbDoc"}
        if op == "pcb_stats":
            return {
                "ok": True,
                "components": 5,
                "pads": 62,
                "tracks": 310,
                "vias": 24,
                "nets": 29,
                "left": 0,
                "bottom": 0,
                "right": 17952,
                "top": 9253,
                "unit": "mil/10",
                "layers": 4,
            }
        if op == "get_stackup":
            return {
                "ok": True,
                "count": 4,
                "items": [
                    {"name": "Top Layer", "kind": "signal"},
                    {"name": "Mid Layer 1", "kind": "signal"},
                    {"name": "Bottom Overlay", "kind": "overlay"},
                    {"name": "Bottom Layer", "kind": "signal"},
                ],
            }
        if op == "take_screenshot":
            return {"ok": True, "format": "svg", "data": _svg_png_data_uri()}
        if op == "pcb_highlight_net":
            net = str(params.get("net") or "")
            if not net:
                return {"ok": False, "error": "missing net param"}
            return {"ok": True, "count": 1, "net": net, "mode": 1 if str(params.get("mode", "1")) != "0" else 0}
        if op == "pcb_move_component":
            designator = str(params.get("designator") or "")
            if not designator:
                return {"ok": False, "error": "missing designator/x/y params"}
            x, y = params.get("x"), params.get("y")
            if x is None or y is None:
                return {"ok": False, "error": "missing designator/x/y params"}
            return {"ok": True, "designator": designator, "x": x, "y": y}
        if op == "pcb_rotate_component":
            designator = str(params.get("designator") or "")
            if not designator:
                return {"ok": False, "error": "missing designator/rotation params"}
            return {"ok": True, "designator": designator, "rotation": params.get("rotation")}
        return {"ok": False, "error": f"mock driver 未实现 op: {op}"}

    def is_alive(self) -> bool:
        return True
