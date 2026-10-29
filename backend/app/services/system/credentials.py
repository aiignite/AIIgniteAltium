import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from app.config import settings

PREFIX = "enc:v1:"


class CredentialError(HTTPException):
    def __init__(self):
        super().__init__(503, "credential_unavailable: configure the encryption key or run credential migration")


def _fernet() -> Fernet:
    try:
        if not settings.credential_encryption_key:
            raise ValueError
        return Fernet(settings.credential_encryption_key.encode("ascii"))
    except (ValueError, TypeError, UnicodeError):
        raise CredentialError() from None


def _legacy_fernet() -> Fernet:
    """历史派生密钥（secret_crypto 旧实现）：用于读取未迁移的密文。"""
    material = settings.ai_secret_key or settings.secret_key
    digest = hashlib.sha256(f"aidrive-altium|{material}".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _decrypt_with(value: str, fernet: Fernet) -> str | None:
    try:
        return fernet.decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError):
        return None


def try_decrypt(value: str) -> str | None:
    """依次尝试专用密钥与历史派生密钥；无法解密返回 None。"""
    if not value:
        return ""
    if not value.startswith(PREFIX):
        return None
    for factory in (_fernet, _legacy_fernet):
        try:
            plain = _decrypt_with(value, factory())
        except CredentialError:
            continue
        if plain is not None:
            return plain
    return None


def encrypt_credential(value: str) -> str:
    if not value:
        return ""
    if value.startswith(PREFIX):
        return value
    return PREFIX + _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_credential(value: str) -> str:
    plain = try_decrypt(value)
    if plain is None:
        raise CredentialError()
    return plain


def validate_credential(value: str) -> None:
    decrypt_credential(value)


async def migrate_credentials(db) -> int:
    from sqlalchemy import select

    from app.models.ai.ai_model import AIModelConfig
    from app.models.altium.connection import GatewayConnection

    replacements = []
    try:
        for model, field in ((AIModelConfig, "api_key"), (GatewayConnection, "api_token")):
            rows = (await db.execute(select(model).with_for_update())).scalars()
            for row in rows:
                value = getattr(row, field)
                if not value:
                    continue
                if value.startswith("enc:"):
                    validate_credential(value)
                else:
                    encrypted = encrypt_credential(value)
                    validate_credential(encrypted)
                    replacements.append((row, field, encrypted))
        for row, field, value in replacements:
            setattr(row, field, value)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return len(replacements)
