"""AES-256 encryption at rest using Fernet (symmetric)."""

from cryptography.fernet import Fernet

from backend.config import settings


def _get_fernet():
    """Return Fernet instance or None if no key configured."""
    key = settings.ENCRYPTION_KEY
    if not key:
        return None
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string. Returns ciphertext base64 string.

    If ENCRYPTION_KEY is not set, returns plaintext unchanged (dev mode).
    """
    f = _get_fernet()
    if f is None:
        return plaintext
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a ciphertext string. Returns original plaintext.

    If ENCRYPTION_KEY is not set, returns value unchanged (dev mode).
    """
    f = _get_fernet()
    if f is None:
        return ciphertext
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except Exception:
        # If decryption fails (e.g. data was stored unencrypted), return as-is
        return ciphertext
