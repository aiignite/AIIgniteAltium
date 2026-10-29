"""文件乒乓驱动（live 模式）：与 Altium 内 DelphiScript 驻留脚本交换
固定文件名 request.txt / response.txt。

时序：写 requests/request.txt → 轮询 responses/response.txt → 解析 → 删除两文件。
（使用固定文件名，规避 DelphiScript 侧 FindFirst/TSearchRec 目录枚举不可靠的问题。）
"""

import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from ..config import settings
from ..protocol import encode_request, parse_response
from .base import AltiumDriver

logger = logging.getLogger(__name__)


class FileBridgeDriver(AltiumDriver):
    def __init__(self, bridge_dir: Path | None = None, op_timeout: float | None = None) -> None:
        self.bridge_dir = bridge_dir or settings.bridge_dir
        self.timeout = op_timeout or settings.op_timeout_seconds
        self._lock = threading.Lock()
        self.last_response_at: float | None = None
        self.requests_dir = self.bridge_dir / "requests"
        self.responses_dir = self.bridge_dir / "responses"

    def ensure_dirs(self) -> None:
        self.requests_dir.mkdir(parents=True, exist_ok=True)
        self.responses_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, ops: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
        self.ensure_dirs()
        request_path = self.requests_dir / "request.txt"
        response_path = self.responses_dir / "response.txt"
        # 清掉上一次残留，避免读到陈旧响应
        for p in (response_path, request_path):
            try:
                p.unlink()
            except OSError:
                pass
        with self._lock:
            request_path.write_text("", encoding="ascii")  # 先占位，防桥读到半写文件
            request_id = uuid.uuid4().hex[:12]  # 必须非空，否则桥端 ReqId='' 会直接 Exit
            request_path.write_text(encode_request(request_id, ops), encoding="ascii")
            deadline = time.time() + self.timeout
            while time.time() < deadline:
                if response_path.exists():
                    try:
                        text = response_path.read_text(encoding="ascii", errors="replace")
                    except OSError:
                        time.sleep(0.1)
                        continue
                    time.sleep(0.05)  # 等 DelphiScript 写完
                    self.last_response_at = time.time()
                    for p in (response_path, request_path):
                        try:
                            p.unlink()
                        except OSError:
                            pass
                    ok, ordered = parse_response(text, len(ops))
                    return [r.to_payload() for r in ordered]
                time.sleep(0.15)
        logger.error("bridge timeout ops=%s", [o for o, _ in ops])
        return [{"ok": False, "error": f"Altium 桥响应超时（>{self.timeout}s），请确认 Altium 内 AIDriveBridge 脚本正在运行"} for _ in ops]

    def is_alive(self) -> bool:
        return self.last_response_at is not None and time.time() - self.last_response_at < 300
