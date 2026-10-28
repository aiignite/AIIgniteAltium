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


def encrypt_credential(value: str) -> str:
    if not value:
        return ""
    return PREFIX + _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_credential(value: str) -> str:
    if not value:
        return ""
    if not value.startswith(PREFIX):
        raise CredentialError()
    try:
        return _fernet().decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError):
        raise CredentialError() from None


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
