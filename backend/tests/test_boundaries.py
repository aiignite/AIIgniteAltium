import asyncio
import json
import socket
from unittest.mock import AsyncMock

import httpx
import pytest
from cryptography.fernet import Fernet

from app.config import Settings, settings
from app.services.ai import providers
from app.services.ai.design_context import build_design_context
from app.services.altium.gateway_client import GatewayClient, GatewayError
from app.services.system.credentials import CredentialError, decrypt_credential, encrypt_credential
from app.services.system.outbound import OutboundError, normalize_base_url, validate_outbound_url


@pytest.mark.parametrize("value", ["", "hello-secret", "密钥"])
def test_credentials(value):
    encrypted = encrypt_credential(value)
    assert decrypt_credential(encrypted) == value
    if value:
        assert encrypted.startswith("enc:v1:") and value not in encrypted


def test_credentials_fail_closed(monkeypatch):
    encrypted = encrypt_credential("secret")
    monkeypatch.setattr(settings, "credential_encryption_key", Fernet.generate_key().decode())
    for value in (encrypted, "plaintext", "enc:v2:invalid", "enc:v1:bad"):
        with pytest.raises(CredentialError) as exc:
            decrypt_credential(value)
        assert value not in str(exc.value)
    monkeypatch.setattr(settings, "credential_encryption_key", "")
    assert encrypt_credential("") == decrypt_credential("") == ""
    with pytest.raises(CredentialError):
        encrypt_credential("secret")
    with pytest.raises(CredentialError):
        decrypt_credential(encrypted)


@pytest.mark.parametrize("secret", ["", " ", "dev-secret-change-me-in-production"])
def test_startup_keys(secret):
    cfg = Settings(_env_file=None, secret_key=secret)
    with pytest.raises(RuntimeError):
        cfg.validate_security()


@pytest.mark.parametrize("password", ["", " ", "admin123456"])
def test_bootstrap_defaults(password):
    cfg = Settings(_env_file=None, admin_password=password)
    with pytest.raises(RuntimeError):
        cfg.validate_bootstrap_password()


def test_main_process_does_not_import_worker_library():
    import sys
    assert not any(name.startswith("altium_monkey") for name in sys.modules)


def test_mils_nonzero_origin_multiple_boards():
    snapshot = {"pcbs": [
        {"name": "one", "board": {"outlineRectMils": [100, 200, 1895, 1125]}},
        {"name": "two", "board": {"outlineRectMils": [-300, -400, 200, 100]}},
    ]}
    context = build_design_context(snapshot)
    assert "1795.0 x 925.0 mil" in context and "500.0 x 500.0 mil" in context


def test_normalization():
    assert normalize_base_url("HTTPS://API.OPENAI.COM.:443/v1/") == "https://api.openai.com/v1"
    assert normalize_base_url("http://[0:0:0:0:0:0:0:1]:80/") == "http://[::1]"


@pytest.mark.parametrize("url", ["https://user:secret@api.openai.com/v1", "https://api.openai.com/v1?token=secret", "https://api.openai.com/v1#x", "file:///tmp/a", "ftp://api.openai.com/v1", "https://api.openai.com.evil/v1", "https://api.openai.com/v10", "https://api.openai.com/v1/evil", "https://api.openai.com:444/v1", "https://api.openai.com/%76%31", "https://api.openai.com\\@evil/v1", "http://", "http://127.0.0.1:0"])
async def test_url_rejected_before_dns(url, monkeypatch):
    lookup = AsyncMock(side_effect=AssertionError("DNS should not be called"))
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", lookup)
    with pytest.raises(OutboundError) as exc:
        await validate_outbound_url(url)
    assert "secret" not in str(exc.value)
    lookup.assert_not_called()


@pytest.mark.parametrize("address", ["169.254.169.254", "0.0.0.0", "224.0.0.1", "100.100.100.200", "192.0.2.1", "::", "fe80::1", "ff02::1", "::ffff:169.254.169.254", "2002:a9fe:a9fe::1", "fd00:ec2::254", "168.63.129.16"])
async def test_special_ips_always_denied(address, monkeypatch):
    host = f"[{address}]" if ":" in address else address
    url = "http://" + host
    monkeypatch.setattr(settings, "outbound_allowed_urls", [url])
    with pytest.raises(OutboundError):
        await validate_outbound_url(url)


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "192.168.0.1", "::1", "fd00::1"])
async def test_explicit_local_allowed(address, monkeypatch):
    host = f"[{address}]" if ":" in address else address
    url = "http://" + host
    monkeypatch.setattr(settings, "outbound_allowed_urls", [url])
    assert await validate_outbound_url(url) == url


async def test_all_dns_results_checked(monkeypatch):
    lookup = AsyncMock(return_value=[(socket.AF_INET, 1, 6, "", ("93.184.216.34", 443)),
                                    (socket.AF_INET6, 1, 6, "", ("fe80::1", 443, 0, 0))])
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", lookup)
    with pytest.raises(OutboundError):
        await validate_outbound_url("https://api.openai.com/v1")
    lookup.return_value = [(socket.AF_INET6, 1, 6, "", ("::1", 3296, 0, 0))]
    assert await validate_outbound_url("http://localhost:3296") == "http://localhost:3296"


def mock_http(monkeypatch, handler):
    original = httpx.AsyncClient
    options = []

    def client(**kwargs):
        options.append(kwargs)
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    return options


@pytest.mark.parametrize("provider", ["openai", "anthropic", "mock"])
async def test_provider_system_payload(provider, monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        if provider == "anthropic":
            return httpx.Response(200, text='data: {"type":"content_block_delta","delta":{"text":"ok"}}\n\n')
        return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n')

    options = mock_http(monkeypatch, handler)
    result = [v async for v in providers.stream_chat(provider, base_url="http://127.0.0.1:3296", api_key=encrypt_credential("mysecret"),
              model="test", messages=[{"role": "system", "content": "old"}, {"role": "user", "content": "hello"}], system="【设计上下文】\nrequired")]
    assert result
    if provider == "mock":
        assert not requests and "required" in "".join(result)
    else:
        payload = json.loads(requests[0].content)
        if provider == "anthropic":
            assert payload["system"] == "【设计上下文】\nrequired"
            assert all(m["role"] != "system" for m in payload["messages"])
            assert requests[0].headers["x-api-key"] == "mysecret"
        else:
            assert [m for m in payload["messages"] if m["role"] == "system"] == [{"role": "system", "content": "【设计上下文】\nrequired"}]
            assert requests[0].headers["authorization"] == "Bearer mysecret"
        assert options[0]["follow_redirects"] is False
        assert "trust_env" not in options[0]


@pytest.mark.parametrize("status", [301, 302, 307, 401, 500])
@pytest.mark.parametrize("kind", ["gateway", "openai", "anthropic"])
async def test_redirects_and_errors_are_safe(status, kind, monkeypatch, caplog):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="mysecret enc:v1:cipher upstream-private-body", headers={"location": "http://169.254.169.254/secret"})

    monkeypatch.setattr("app.services.altium.gateway_client.RETRY_BACKOFF_SECONDS", (0, 0))
    options = mock_http(monkeypatch, handler)
    with pytest.raises((GatewayError, providers.ProviderError)) as caught:
        if kind == "gateway":
            await GatewayClient("http://127.0.0.1:3296", encrypt_credential("mysecret")).health()
        else:
            _ = [v async for v in providers.stream_chat(kind, base_url="http://127.0.0.1:3296", api_key=encrypt_credential("mysecret"), model="test", messages=[])]
    expected_calls = 3 if kind == "gateway" and status >= 500 else 1
    assert len(calls) == expected_calls and options[0]["follow_redirects"] is False
    if kind == "gateway":
        assert options[0]["trust_env"] is False
    output = str(caught.value) + caplog.text
    for secret in ("mysecret", "enc:v1:cipher", "upstream-private-body", "169.254"):
        assert secret not in output
    assert str(status) in output and "requestId=" in output


async def test_transport_exception_sanitized(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("https://secret:password@private/ full-body", request=request)

    mock_http(monkeypatch, handler)
    with pytest.raises(providers.ProviderError, match="transport") as caught:
        _ = [v async for v in providers.stream_chat("openai", base_url="http://127.0.0.1:3296", api_key="", model="test", messages=[])]
    assert "password" not in str(caught.value)


async def test_unapproved_no_http(monkeypatch):
    calls = []
    mock_http(monkeypatch, lambda req: calls.append(req))
    with pytest.raises(OutboundError):
        await GatewayClient("http://192.168.99.1").health()
    with pytest.raises(OutboundError):
        _ = [v async for v in providers.stream_chat("openai", base_url="http://192.168.99.1", api_key="", model="test", messages=[])]
    assert not calls
