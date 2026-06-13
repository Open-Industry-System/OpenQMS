"""MES credential encryption and security utilities.

Provides:
- SHA-256 API Key hashing (inbound)
- Fernet symmetric encryption (outbound credentials)
- Config sanitization for API responses
"""

import hashlib
import hmac
import os

from cryptography.fernet import Fernet

# ---- Fernet singleton ----
_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """Lazy-initialize Fernet from MES_ENCRYPTION_KEY env var."""
    global _fernet
    if _fernet is None:
        key = os.environ.get("MES_ENCRYPTION_KEY")
        if not key:
            raise RuntimeError(
                "MES_ENCRYPTION_KEY environment variable is not set. "
                "It must be a 32-byte base64-encoded Fernet key."
            )
        _fernet = Fernet(key.encode("utf-8"))
    return _fernet


# ---- API Key hash (inbound) ----
def hash_api_key(api_key: str) -> str:
    """SHA-256 hash of plaintext API Key."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def verify_api_key(api_key: str, api_key_hash: str) -> bool:
    """Verify plaintext API Key against stored hash using hmac.compare_digest (timing-safe)."""
    computed = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    return hmac.compare_digest(computed, api_key_hash)


# ---- Fernet encryption (outbound credentials) ----
def encrypt_credential(plaintext: str) -> str:
    """Encrypt outbound credential."""
    fernet = _get_fernet()
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_credential(ciphertext: str) -> str:
    """Decrypt outbound credential. Only called at runtime during push_quality_event."""
    fernet = _get_fernet()
    return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


# ---- Response sanitization ----
def sanitize_config(config: dict) -> dict:
    """Sanitize config for API responses.

    Whitelist strategy: remove entire auth_config (all credential fields are sensitive).
    Also scrub any top-level keys ending with _encrypted or _hash.
    """
    sanitized = {}
    for key, value in config.items():
        if key == "auth_config":
            continue
        if key.endswith("_encrypted") or key.endswith("_hash"):
            continue
        sanitized[key] = value
    return sanitized
