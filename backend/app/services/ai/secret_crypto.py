"""API Key 加密 / 解密 / 掩码（对齐 AIDriveNote secret_crypto 约定）。

- 落库只存密文：``enc:v1:<fernet token>``
- 加密统一走 ``system.credentials``（专用 CREDENTIAL_ENCRYPTION_KEY，缺失时 fail-closed）
- 解密兼容历史派生密钥；历史明文自动识别（返回原文），由迁移逻辑负责升级回写
- 对外一律只暴露掩码 ``key_hint``，任何响应/日志不得出现明文
"""

from __future__ import annotations

import logging

PREFIX = "enc:v1:"

logger = logging.getLogger(__name__)


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
    from app.services.system.credentials import encrypt_credential

    return encrypt_credential(plain)


def decrypt_secret(value: str | None) -> str:
    """解密；历史明文原样返回；损坏密文返回空串（宁可失败也不把密文当 Key 发出去）。"""
    if not value:
        return ""
    if not is_encrypted(value):
        return str(value)
    from app.services.system.credentials import try_decrypt

    plain = try_decrypt(str(value))
    if plain is None:
        logger.warning("api key 解密失败（密钥可能已更换）")
        return ""
    return plain


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
