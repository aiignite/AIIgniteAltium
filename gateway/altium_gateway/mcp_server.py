"""MCP server 入口：把命令层暴露为标准 MCP tools。

- stdio（默认）：`python -m altium_gateway.mcp_server` 或 `altium-gateway-mcp`，
  可直接注册到 Claude Desktop / ZCode 等 MCP 客户端。
- HTTP：`python -m altium_gateway.mcp_server --http` 输出 streamable HTTP 的
  ASGI 应用路径说明；gateway REST 应用亦在 /mcp 挂载同一服务。
"""

from __future__ import annotations

import argparse
import base64
import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import commands as cmd
from .app import build_driver

mcp = FastMCP("altium-gateway")
_driver = build_driver()


def _run(name: str, params: dict[str, Any] | None = None) -> str:
    result = cmd.execute_command(_driver, name, params)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def altium_ping() -> str:
    """检查 Altium 内 AIDriveBridge 驻留脚本是否在线。"""
    return _run("altium_ping")


@mcp.tool()
def altium_get_project_info() -> str:
    """获取 Altium 当前打开的工程名称、路径与活动文档。"""
    return _run("altium_get_project_info")


@mcp.tool()
def altium_get_schematic_components() -> str:
    """列出当前原理图文档的元件（位号/值/封装）。"""
    return _run("altium_get_schematic_components")


@mcp.tool()
def altium_get_schematic_nets() -> str:
    """列出当前原理图的网络标签/电源端口及连接计数。"""
    return _run("altium_get_schematic_nets")


@mcp.tool()
def altium_get_pcb_components() -> str:
    """列出当前 PCB 文档的元件与所在层。"""
    return _run("altium_get_pcb_components")


@mcp.tool()
def altium_get_pcb_stats() -> str:
    """当前 PCB 的元件/焊盘/走线/过孔/网络计数与板框尺寸、叠层数。"""
    return _run("altium_get_pcb_stats")


@mcp.tool()
def altium_get_stackup() -> str:
    """当前 PCB 的板层名称列表。"""
    return _run("altium_get_stackup")


@mcp.tool()
def altium_take_screenshot() -> str:
    """截取 Altium 当前文档窗口画面，返回 data URI（供多模态查看）。"""
    result = cmd.execute_command(_driver, "altium_take_screenshot", {})
    if result.get("ok") and result.get("format") == "svg":
        raw = result.get("data", "")
        b64 = base64.b64encode(raw.encode("utf-8")).decode("ascii") if not raw.startswith("data:") else raw.split(",", 1)[-1]
        result = {**result, "data": "data:image/svg+xml;base64," + b64}
    return json.dumps(result, ensure_ascii=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="AIDriveAltium MCP server")
    parser.add_argument("--http", action="store_true", help="以 streamable HTTP 方式运行（默认 stdio）")
    args = parser.parse_args()
    if args.http:
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
