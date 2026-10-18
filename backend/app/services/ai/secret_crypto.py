"""API Key 加密 / 解密 / 掩码（对齐 AIDriveNote secret_crypto 约定）。

- 落库只存密文：``enc:v1:<fernet token>``
- 读取时解密；历史明文自动识别（返回原文），由 seed/迁移逻辑负责升级回写
- 对外一律只暴露掩码 ``key_hint``，任何响应/日志不得出现明文
"""

from __future__ import annotations

import base64
import hashlib
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

logger = logging.getLogger(__name__)

PREFIX = "enc:v1:"


@lru_cache(maxsize=4)
def _fernet_for(material: str) -> Fernet:
    digest = hashlib.sha256(f"aidrive-altium|{material}".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _fernet() -> Fernet:
    return _fernet_for(settings.ai_secret_key or settings.secret_key)


def is_encrypted(value: str | None) -> bool:
    return bool(value) and str(value).startswith(PREFIX)


def needs_upgrade(value: str | None) -> bool:
    """非空且不是密文 → 历史明文，需要升级。"""
    return bool(value) and not is_encrypted(value)


def encrypt_secret(plain: str | None) -> str:
    if not plain:
        return ""
    if is_encrypted(plain):
        return str(plain)
    token = _fernet().encrypt(plain.encode("utf-8")).decode("ascii")
    return f"{PREFIX}{token}"


def decrypt_secret(value: str | None) -> str:
    """解密；历史明文原样返回；损坏密文返回空串（宁可失败也不把密文当 Key 发出去）。"""
    if not value:
        return ""
    if not is_encrypted(value):
        return str(value)
    try:
        return _fernet().decrypt(str(value)[len(PREFIX) :].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError) as exc:
        logger.warning("api key 解密失败（密钥可能已更换）: %s", exc)
        return ""


def mask_secret(plain: str | None) -> str:
    """掩码：保留后 4 位；过短则全部遮蔽。"""
    if not plain:
        return ""
    text = str(plain)
    if len(text) <= 4:
        return "*" * len(text)
    if len(text) <= 8:
        return "****" + text[-2:]
    return "****" + text[-4:]
