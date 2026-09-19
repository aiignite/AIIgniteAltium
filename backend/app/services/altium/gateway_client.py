"""gateway REST 客户端：后端 → 局域网 Windows 机上的 altium-gateway(:3296)。"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = httpx.Timeout(connect=4.0, read=8.0, write=4.0, pool=4.0)
COMMAND_TIMEOUT = httpx.Timeout(connect=4.0, read=40.0, write=4.0, pool=4.0)


class GatewayError(RuntimeError):
    pass


class GatewayClient:
    def __init__(self, base_url: str, token: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def health(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, trust_env=False) as client:
                resp = await client.get(f"{self.base_url}/health", headers=self._headers())
        except httpx.HTTPError as exc:
            raise GatewayError(f"无法连接 gateway: {exc}") from exc
        if resp.status_code == 401:
            raise GatewayError("gateway 令牌不匹配")
        if resp.status_code != 200:
            raise GatewayError(f"gateway HTTP {resp.status_code}")
        return resp.json()

    async def tools(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, trust_env=False) as client:
            resp = await client.get(f"{self.base_url}/tools", headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    async def command(self, name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=COMMAND_TIMEOUT, trust_env=False) as client:
                resp = await client.post(
                    f"{self.base_url}/command/{name}", json=params or {}, headers=self._headers()
                )
        except httpx.HTTPError as exc:
            raise GatewayError(f"gateway 调用失败: {exc}") from exc
        if resp.status_code == 502:
            raise GatewayError(resp.json().get("detail", "Altium 操作失败"))
        if resp.status_code != 200:
            raise GatewayError(f"gateway HTTP {resp.status_code}")
        return resp.json()

    async def live_summary(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=COMMAND_TIMEOUT, trust_env=False) as client:
                resp = await client.get(f"{self.base_url}/live/summary", headers=self._headers())
        except httpx.HTTPError as exc:
            raise GatewayError(f"gateway 调用失败: {exc}") from exc
        if resp.status_code != 200:
            raise GatewayError(f"gateway HTTP {resp.status_code}")
        return resp.json()

    async def screenshot(self) -> tuple[bytes, str]:
        """返回 (图片字节, media_type)。"""
        try:
            async with httpx.AsyncClient(timeout=COMMAND_TIMEOUT, trust_env=False) as client:
                resp = await client.get(f"{self.base_url}/screenshot", headers=self._headers())
        except httpx.HTTPError as exc:
            raise GatewayError(f"gateway 调用失败: {exc}") from exc
        if resp.status_code != 200:
            raise GatewayError(f"gateway HTTP {resp.status_code}")
        return resp.content, resp.headers.get("content-type", "image/svg+xml")
