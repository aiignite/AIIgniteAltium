"""gateway REST 应用（:3296）。

端点：
- GET  /health                健康与桥状态
- GET  /tools                 命令/工具清单（含 MCP 元数据）
- POST /command/{name}        执行命令
- GET  /live/summary          聚合实时设计摘要（LLM 上下文用）
- GET  /screenshot            截图（svg/png）
- POST /mcp                   MCP streamable HTTP（亦提供 stdio 入口）
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from . import commands as cmd
from .config import settings
from .drivers.file_bridge import FileBridgeDriver
from .drivers.mock import MockAltiumDriver

logger = logging.getLogger(__name__)


def build_driver():
    if settings.mode == "live":
        return FileBridgeDriver()
    return MockAltiumDriver()


driver = build_driver()
app = FastAPI(title="AIDriveAltium Gateway", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    if settings.token and request.url.path not in ("/health",):
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {settings.token}":
            return Response(status_code=401, content="invalid gateway token")
    return await call_next(request)


def _check(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("ok"):
        raise HTTPException(status_code=502, detail=payload.get("error", "Altium op failed"))
    return payload


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "mode": settings.mode,
        "bridgeDir": str(settings.bridge_dir),
        "altiumOnline": driver.is_alive(),
        "commands": len(cmd.COMMANDS),
    }


@app.get("/tools")
def tools() -> list[dict[str, Any]]:
    return cmd.list_commands()


@app.post("/command/{name}")
def run_command(name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return _check(cmd.execute_command(driver, name, params))


@app.get("/live/summary")
def live_summary() -> dict[str, Any]:
    return cmd.build_live_summary(driver)


@app.get("/screenshot")
def screenshot():
    result = cmd.execute_command(driver, "altium_take_screenshot", {})
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result.get("error", "截图失败"))
    fmt = result.get("format", "svg")
    data = result.get("data", "")
    if data.startswith("data:"):
        head, _, b64 = data.partition(",")
        fmt = "png" if "image/png" in head else "svg"
        content = base64.b64decode(b64)
    else:
        content = data.encode("utf-8")
    media = "image/svg+xml" if fmt == "svg" else "image/png"
    return Response(content=content, media_type=media)


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    logger.info("gateway mode=%s bridge_dir=%s", settings.mode, settings.bridge_dir)
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
