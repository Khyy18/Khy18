"""AES-256-GCM encryption at rest with versioned key rotation support."""

import base64
import os
import re
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.config import settings

_VERSION_PREFIX_RE = re.compile(r"^v(\d+):(.+)$")


def _get_key(version: int) -> Optional[bytes]:
    """Return the raw 32-byte key for the given version, or None if not configured."""
    key_b64 = ""
    if version == 1:
        key_b64 = settings.ENCRYPTION_KEY_V1 or settings.ENCRYPTION_KEY
    elif version == 2:
        key_b64 = settings.ENCRYPTION_KEY_V2
    else:
        # Try generic attribute for future versions
        key_b64 = getattr(settings, f"ENCRYPTION_KEY_V{version}", "")

    if not key_b64:
        return None
    try:
        raw = base64.urlsafe_b64decode(key_b64)
        if len(raw) == 32:
            return raw
        return None
    except Exception:
        try:
            raw = base64.b64decode(key_b64)
            if len(raw) == 32:
                return raw
            return None
        except Exception:
            return None


def _current_version() -> int:
    """Return the current encryption key version."""
    return settings.ENCRYPTION_KEY_VERSION


def encrypt_field(plaintext: str, key: bytes, aad: Optional[bytes] = None) -> str:
    """Encrypt plaintext using AES-256-GCM.

    Returns base64(nonce + ciphertext + tag) as a string.
    Nonce is 12 bytes, generated randomly for each call.
    If aad (associated authenticated data) is provided, it is bound to the ciphertext.
    """
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad)
    # ct includes ciphertext + 16-byte tag appended by AESGCM
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt_field(encrypted: str, key: bytes, aad: Optional[bytes] = None) -> str:
    """Decrypt an AES-256-GCM encrypted value.

    Expects base64(nonce + ciphertext + tag).
    If aad is provided, it must match the AAD used during encryption.
    For backward compatibility, if decryption with AAD fails due to InvalidTag,
    retries without AAD (for data encrypted before AAD was added).
    """
    from cryptography.exceptions import InvalidTag

    raw = base64.b64decode(encrypted)
    nonce = raw[:12]
    ct = raw[12:]
    aesgcm = AESGCM(key)
    if aad is not None:
        try:
            plaintext = aesgcm.decrypt(nonce, ct, aad)
            return plaintext.decode("utf-8")
        except InvalidTag:
            # Backward compatibility: retry without AAD for data encrypted before AAD was added
            import logging
            logging.getLogger(__name__).warning(
                "Decryption with AAD failed (InvalidTag), retrying without AAD for backward compatibility"
            )
            plaintext = aesgcm.decrypt(nonce, ct, None)
            return plaintext.decode("utf-8")
    plaintext = aesgcm.decrypt(nonce, ct, None)
    return plaintext.decode("utf-8")


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string with the current version key.

    Returns 'vN:base64data' format. If no key is configured, returns
    plaintext unchanged (dev mode). Uses the version string as AAD.
    """
    version = _current_version()
    key = _get_key(version)
    if key is None:
        return plaintext
    version_aad = f"v{version}".encode("utf-8")
    encrypted = encrypt_field(plaintext, key, aad=version_aad)
    return f"v{version}:{encrypted}"


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a ciphertext string, detecting version prefix.

    Supports:
    - 'vN:base64data' format (AES-256-GCM versioned)
    - Legacy Fernet format (fallback)
    - Plain text passthrough if decryption fails or no key configured
    """
    if not ciphertext:
        return ciphertext

    # Check for versioned format
    match = _VERSION_PREFIX_RE.match(ciphertext)
    if match:
        version = int(match.group(1))
        data = match.group(2)
        key = _get_key(version)
        if key is None:
            # No key for this version, return as-is
            return ciphertext
        try:
            version_aad = f"v{version}".encode("utf-8")
            return decrypt_field(data, key, aad=version_aad)
        except Exception:
            return ciphertext

    # No version prefix - try legacy Fernet decryption
    fernet_key = settings.ENCRYPTION_KEY
    if fernet_key:
        try:
            f = Fernet(fernet_key.encode() if isinstance(fernet_key, str) else fernet_key)
            return f.decrypt(ciphertext.encode()).decode()
        except Exception:
            pass

    # If all else fails, return as-is (plain text or dev mode)
    return ciphertext
