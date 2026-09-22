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
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from . import commands as cmd
from .config import settings
from .drivers.file_bridge import FileBridgeDriver
from .drivers.mock import MockAltiumDriver

logger = logging.getLogger(__name__)

# PowerShell 截取 Altium Designer 主窗口（EnumWindows 按标题 'Altium Designer' 定位可见窗口，
# PrintWindow 免遮挡）。桥端 DelphiScript 无法做 GDI 截图，改由 gateway 在本机窗口级截取。
_PS_CAPTURE = r"""
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
public class WC {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  public static IntPtr Find(string needle) {
    IntPtr result = IntPtr.Zero;
    EnumWindows(delegate(IntPtr h, IntPtr l) {
      StringBuilder sb = new StringBuilder(512);
      GetWindowText(h, sb, 512);
      string t = sb.ToString();
      if (t.IndexOf(needle, StringComparison.OrdinalIgnoreCase) >= 0 && IsWindowVisible(h)) {
        result = h;
        return false;
      }
      return true;
    }, IntPtr.Zero);
    return result;
  }
}
"@
$h = [WC]::Find('Altium Designer')
if ($h -eq [IntPtr]::Zero) { Write-Output 'NO_WINDOW'; exit 1 }
[void][WC]::ShowWindow($h, 9)   # SW_RESTORE
[void][WC]::SetForegroundWindow($h)
Start-Sleep -Milliseconds 300
$r = New-Object RECT
if (-not [WC]::GetWindowRect($h, [ref]$r)) { Write-Output 'NO_RECT'; exit 1 }
$w = $r.Right - $r.Left
$hh = $r.Bottom - $r.Top
if ($w -le 0 -or $hh -le 0) { Write-Output 'BAD_RECT'; exit 1 }
$bmp = New-Object System.Drawing.Bitmap($w, $hh)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
$ok = [WC]::PrintWindow($h, $hdc, 2)   # PW_RENDERFULLCONTENT
$g.ReleaseHdc($hdc)
$g.Dispose()
if (-not $ok) { $bmp.Dispose(); Write-Output 'PRINT_FAIL'; exit 1 }
$bmp.Save($args[0], [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output 'OK'
"""


def capture_altium_window() -> bytes | None:
    """本机截取 Altium Designer 主窗口为 PNG 字节；找不到窗口或失败返回 None。"""
    tmp_png = None
    try:
        fd, tmp_png = tempfile.mkstemp(suffix=".png")
        import os

        os.close(fd)
        script = Path(tempfile.mkdtemp(prefix="altium_cap_")) / "capture.ps1"
        script.write_text(_PS_CAPTURE, encoding="utf-8")
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), tmp_png],
            capture_output=True,
            timeout=20,
        )
        if proc.returncode == 0 and Path(tmp_png).stat().st_size > 0:
            return Path(tmp_png).read_bytes()
        logger.info(
            "window capture failed rc=%s out=%s err=%s",
            proc.returncode,
            proc.stdout.decode("utf-8", "ignore")[:200],
            proc.stderr.decode("utf-8", "ignore")[:200],
        )
        return None
    except Exception as exc:  # noqa: BLE001 —— 截图失败回退占位图，不影响服务
        logger.info("window capture error: %s", exc)
        return None
    finally:
        if tmp_png:
            try:
                Path(tmp_png).unlink(missing_ok=True)
            except OSError:
                pass


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
    payload = cmd.execute_command(driver, name, params)
    if payload.get("ok") is False and not payload.get("requiresConfirmation") and not payload.get("dryRun"):
        raise HTTPException(status_code=502, detail=payload.get("error", "Altium op failed"))
    return payload


@app.get("/live/summary")
def live_summary() -> dict[str, Any]:
    return cmd.build_live_summary(driver)


@app.get("/screenshot")
def screenshot():
    result = cmd.execute_command(driver, "altium_take_screenshot", {})
    if not result.get("ok"):
        # 桥端 DelphiScript 不支持 GDI 截图时，回退本机窗口级截取真实 PNG
        png = capture_altium_window()
        if png:
            return Response(content=png, media_type="image/png")
        return Response(
            content=_placeholder_svg().encode("utf-8"),
            media_type="image/svg+xml",
        )
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


def _placeholder_svg() -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360">'
        '<rect width="100%" height="100%" fill="#f6f8fa"/>'
        '<text x="320" y="170" fill="#57606a" font-family="monospace" font-size="22" '
        'text-anchor="middle">Altium 截图暂不可用</text>'
        '<text x="320" y="200" fill="#8b949e" font-family="monospace" font-size="14" '
        'text-anchor="middle">DelphiScript 不支持 GDI 截图（DLL 声明受限）</text>'
        "</svg>"
    )


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    logger.info("gateway mode=%s bridge_dir=%s", settings.mode, settings.bridge_dir)
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
