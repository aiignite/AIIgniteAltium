"""gateway 配置（环境变量优先）。"""

import os
import tempfile
from pathlib import Path


def _bridge_dir_default() -> Path:
    env = os.environ.get("ALTIUM_BRIDGE_DIR")
    if env:
        return Path(env)
    if os.name == "nt":
        # 与 DelphiScript 脚本内 DEFAULT_BRIDGE_DIR 保持一致
        home = os.environ.get("USERPROFILE", r"C:\\")
        return Path(home) / "Documents" / "AltiumBridge"
    return Path(tempfile.gettempdir()) / "AltiumBridge"


class GatewaySettings:
    """网关配置。

    ALTIUM_MODE: mock(默认，内置演示数据，便于无 Altium 开发联调) | live(文件乒乓桥)
    ALTIUM_BRIDGE_DIR: 与 Altium 内 DelphiScript 驻留脚本共享的请求/响应目录
    GATEWAY_PORT: 监听端口（默认 3296）
    GATEWAY_TOKEN: 可选静态令牌，后端与 gateway 一致即可
    """

    def __init__(self) -> None:
        self.mode = os.environ.get("ALTIUM_MODE", "mock").lower()
        self.bridge_dir = _bridge_dir_default()
        self.port = int(os.environ.get("GATEWAY_PORT", "3296"))
        self.host = os.environ.get("GATEWAY_HOST", "0.0.0.0")
        self.token = os.environ.get("GATEWAY_TOKEN", "")
        self.op_timeout_seconds = float(os.environ.get("ALTIUM_OP_TIMEOUT", "20"))

    @property
    def requests_dir(self) -> Path:
        return self.bridge_dir / "requests"

    @property
    def responses_dir(self) -> Path:
        return self.bridge_dir / "responses"


settings = GatewaySettings()
