import base64
import hashlib
from cryptography.fernet import Fernet

from app.config import get_settings

settings = get_settings()


def _fernet() -> Fernet:
    seed = (settings.TOKEN_ENCRYPTION_KEY or settings.SECRET_KEY).encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(seed).digest())
    return Fernet(key)


def encrypt_text(value: str) -> str:
    if not value:
        return value
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_text(value: str | None) -> str | None:
    if not value:
        return value
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except Exception:  # noqa: BLE001
        # Backward compatibility for legacy plain-text tokens.
        return value
