import asyncio

import httpx
import pytest

from app.services.altium.gateway_client import GatewayClient, GatewayError
from test_boundaries import mock_http

BASE = "http://127.0.0.1:3296"


def no_backoff(monkeypatch):
    monkeypatch.setattr("app.services.altium.gateway_client.RETRY_BACKOFF_SECONDS", (0, 0))


async def test_get_retries_transport_then_succeeds(monkeypatch):
    no_backoff(monkeypatch)
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            raise httpx.ConnectError("transient", request=request)
        return httpx.Response(200, json={"altiumOnline": True})

    mock_http(monkeypatch, handler)
    assert await GatewayClient(BASE).health() == {"altiumOnline": True}
    assert len(calls) == 3


async def test_get_retries_5xx_then_succeeds(monkeypatch):
    no_backoff(monkeypatch)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(502 if len(calls) < 3 else 200, json={"ok": True})

    mock_http(monkeypatch, handler)
    assert await GatewayClient(BASE).live_summary() == {"ok": True}
    assert len(calls) == 3


async def test_get_transport_failure_is_bounded(monkeypatch):
    no_backoff(monkeypatch)
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("slow", request=request)

    mock_http(monkeypatch, handler)
    with pytest.raises(GatewayError) as caught:
        await GatewayClient(BASE).screenshot()
    assert caught.value.category == "transport" and len(calls) == 3


async def test_command_transport_error_is_not_retried(monkeypatch):
    no_backoff(monkeypatch)
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("down", request=request)

    mock_http(monkeypatch, handler)
    with pytest.raises(GatewayError):
        await GatewayClient(BASE).command("get_board_summary")
    assert len(calls) == 1


async def test_get_4xx_is_not_retried(monkeypatch):
    no_backoff(monkeypatch)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(401)

    mock_http(monkeypatch, handler)
    with pytest.raises(GatewayError) as caught:
        await GatewayClient(BASE).health()
    assert caught.value.category == "http" and caught.value.status == 401 and len(calls) == 1


async def test_retry_sleep_is_cancellation_safe(monkeypatch):
    monkeypatch.setattr("app.services.altium.gateway_client.RETRY_BACKOFF_SECONDS", (5, 5))
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("down", request=request)

    mock_http(monkeypatch, handler)
    task = asyncio.create_task(GatewayClient(BASE).health())
    while not calls:
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.05)
    assert len(calls) == 1
