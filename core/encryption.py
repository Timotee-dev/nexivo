"""
Symmetric field-level encryption for sensitive data at rest.
Uses Fernet (AES-128-CBC + HMAC-SHA256) via the cryptography library.
The key is derived from FIELD_ENCRYPTION_KEY in settings (a 32-byte
URL-safe base64 secret). All encrypted values are stored as
"enc:<base64-ciphertext>" so plain-text legacy values are still readable
and the prefix makes accidental double-encryption obvious.

Usage:
    from core.encryption import encrypt, decrypt

    # Encrypt before save:
    profile.nin_number = encrypt(raw_nin)

    # Decrypt on read:
    raw_nin = decrypt(profile.nin_number)
"""

import base64

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet():
    key = getattr(settings, "FIELD_ENCRYPTION_KEY", "")
    if not key:
        raise RuntimeError(
            "FIELD_ENCRYPTION_KEY is not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


PREFIX = "enc:"


def encrypt(value: str | None) -> str | None:
    """Encrypts a string and returns a prefixed ciphertext. Idempotent on already-encrypted values."""
    if value is None:
        return None
    if isinstance(value, str) and value.startswith(PREFIX):
        return value  # already encrypted
    token = _fernet().encrypt(str(value).encode())
    return PREFIX + token.decode()


def decrypt(value: str | None) -> str | None:
    """Decrypts a prefixed ciphertext. Returns plain-text values as-is (migration safety)."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.startswith(PREFIX):
        return value  # legacy plain-text value
    try:
        return _fernet().decrypt(value[len(PREFIX):].encode()).decode()
    except InvalidToken:
        return None


def mask(value: str | None, visible: int = 4) -> str:
    """Returns a masked display version, e.g. '••••••7890' for a 10-digit value."""
    if not value:
        return ""
    raw = decrypt(value) or value
    if len(raw) <= visible:
        return "•" * len(raw)
    return "•" * (len(raw) - visible) + raw[-visible:]
