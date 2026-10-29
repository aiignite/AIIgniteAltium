import asyncio
import ipaddress
import posixpath
import socket
from urllib.parse import urlsplit, urlunsplit

from fastapi import HTTPException

from app.config import settings


class OutboundError(HTTPException):
    def __init__(self):
        super().__init__(400, "outbound_target_not_allowed")


def normalize_base_url(value: str) -> str:
    try:
        if not value or any(c.isspace() or ord(c) < 32 for c in value) or any(c in value for c in "\\%?#"):
            raise ValueError
        parts = urlsplit(value)
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname or parts.username is not None or parts.password is not None:
            raise ValueError
        host = parts.hostname.rstrip(".").lower().encode("idna").decode("ascii")
        if ":" in host:
            host = f"[{ipaddress.IPv6Address(host).compressed}]"
        port = parts.port
        if port == 0:
            raise ValueError
        authority = host if port is None or port == {"http": 80, "https": 443}[parts.scheme.lower()] else f"{host}:{port}"
        path = posixpath.normpath("/" + parts.path.lstrip("/")).rstrip("/")
        return urlunsplit((parts.scheme.lower(), authority, path, "", ""))
    except (ValueError, UnicodeError):
        raise OutboundError() from None


def display_base_url(value: str) -> str:
    try:
        return normalize_base_url(value) if value else ""
    except OutboundError:
        return ""


def approved_base_url(value: str) -> str:
    normalized = normalize_base_url(value)
    if normalized not in {normalize_base_url(url) for url in settings.outbound_allowed_urls}:
        raise OutboundError()
    return normalized


def _check_address(value: str) -> None:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        raise OutboundError() from None
    if str(address) in {"fd00:ec2::254", "168.63.129.16"}:
        raise OutboundError()
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            _check_address(str(address.ipv4_mapped))
            return
        if address.sixtofour or address.teredo or address.is_site_local:
            raise OutboundError()
    if address.is_link_local or address.is_unspecified or address.is_multicast or (address.is_reserved and not address.is_loopback):
        raise OutboundError()
    private = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16") if address.version == 4 else ("fc00::/7",)
    if not (address.is_global or address.is_loopback or any(address in ipaddress.ip_network(n) for n in private)):
        raise OutboundError()


async def validate_outbound_url(value: str, *, allow_private: bool = False) -> str:
    """校验出站地址；allow_private 仅绕过白名单（仍拒绝链路本地/元数据等特殊地址）。

    白名单用于云端 provider；本地推理（ollama / llama.cpp）在显式开启
    ``ai_allow_private_model_hosts`` 时允许私网/回环地址。
    """
    try:
        normalized = approved_base_url(value)
    except OutboundError:
        if not allow_private:
            raise
        normalized = normalize_base_url(value)
    parts = urlsplit(normalized)
    try:
        address = ipaddress.ip_address(parts.hostname)
    except ValueError:
        try:
            results = await asyncio.get_running_loop().getaddrinfo(
                parts.hostname, parts.port or (443 if parts.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        except (OSError, UnicodeError):
            raise OutboundError() from None
        if not results:
            raise OutboundError()
        for result in results:
            _check_address(result[4][0])
    else:
        _check_address(str(address))
    return normalized
