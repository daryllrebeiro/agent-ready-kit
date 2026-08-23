"""API Key generation, secure hashing, and validation for multi-tenant access."""

import hashlib
import hmac
import secrets
from typing import Tuple


def generate_api_key(prefix: str = "ark_live_") -> Tuple[str, str]:
    """Generate a secure raw API key and its SHA-256 hash for database storage."""
    random_bytes = secrets.token_urlsafe(32)
    raw_key = f"{prefix}{random_bytes}"
    key_hash = hash_api_key(raw_key)
    return raw_key, key_hash


def hash_api_key(raw_key: str) -> str:
    """Compute deterministic SHA-256 hash of API key."""
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    """Constant-time comparison to prevent timing attacks."""
    computed_hash = hash_api_key(raw_key)
    return hmac.compare_digest(computed_hash, stored_hash)
