import asyncio
from typing import Any
from uuid import uuid4

import httpx

from app.services.system.credentials import decrypt_credential
from app.services.system.outbound import validate_outbound_url

DEFAULT_TIMEOUT = httpx.Timeout(connect=4.0, read=8.0, write=4.0, pool=4.0)
COMMAND_TIMEOUT = httpx.Timeout(connect=4.0, read=40.0, write=4.0, pool=4.0)
# 仅幂等 GET 重试；命令、4xx、重定向一律不重试
GET_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (0.2, 0.5)


class GatewayError(RuntimeError):
    def __init__(self, category: str, status: int | None = None):
        self.category, self.status, self.request_id = category, status, uuid4().hex
        super().__init__(f"gateway_{category}; status={status or 'none'}; requestId={self.request_id}")


class GatewayClient:
    def __init__(self, base_url: str, token: str = "") -> None:
        self.base_url = base_url
        self.token = token

    async def _request(self, method: str, path: str, *, payload=None, timeout=COMMAND_TIMEOUT,
                       retryable: bool = False) -> httpx.Response:
        base_url = await validate_outbound_url(self.base_url)
        token = decrypt_credential(self.token)
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        attempts = GET_ATTEMPTS if retryable else 1
        last_error: GatewayError | None = None
        try:
            async with httpx.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False) as client:
                for attempt in range(attempts):
                    try:
                        resp = await client.request(method, base_url + path, json=payload, headers=headers)
                    except httpx.HTTPError:
                        last_error = GatewayError("transport")
                        if attempt + 1 < attempts:
                            await asyncio.sleep(RETRY_BACKOFF_SECONDS[min(attempt, len(RETRY_BACKOFF_SECONDS) - 1)])
                            continue
                        raise last_error from None
                    if resp.status_code == 200:
                        return resp
                    if retryable and resp.status_code >= 500 and attempt + 1 < attempts:
                        last_error = GatewayError("http", resp.status_code)
                        await asyncio.sleep(RETRY_BACKOFF_SECONDS[min(attempt, len(RETRY_BACKOFF_SECONDS) - 1)])
                        continue
                    raise GatewayError("redirect" if 300 <= resp.status_code < 400 else "http", resp.status_code)
        except asyncio.CancelledError:
            raise
        raise last_error or GatewayError("transport")

    def _json(self, resp):
        try:
            return resp.json()
        except ValueError:
            raise GatewayError("invalid_response", resp.status_code) from None

    async def health(self) -> dict[str, Any]:
        return self._json(await self._request("GET", "/health", timeout=DEFAULT_TIMEOUT, retryable=True))

    async def tools(self) -> list[dict[str, Any]]:
        return self._json(await self._request("GET", "/tools", timeout=DEFAULT_TIMEOUT, retryable=True))

    async def command(self, name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not name.replace("_", "").isalnum():
            raise GatewayError("invalid_command")
        return self._json(await self._request("POST", f"/command/{name}", payload=params or {}))

    async def live_summary(self) -> dict[str, Any]:
        result = self._json(await self._request("GET", "/live/summary", retryable=True))
        if not isinstance(result, dict):
            raise GatewayError("invalid_response")
        if result.get("errors"):
            result["errors"] = ["gateway_partial_failure"]
        return result

    async def screenshot(self) -> tuple[bytes, str]:
        resp = await self._request("GET", "/screenshot", retryable=True)
        return resp.content, resp.headers.get("content-type", "image/svg+xml")
