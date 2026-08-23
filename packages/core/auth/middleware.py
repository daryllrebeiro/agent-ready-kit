"""Unified Authentication & RBAC Middleware.

Resolves incoming credentials (Bearer API Keys, session tokens) into an AuthContext
that supplies `tenant_id` to PostgreSQL Row-Level Security sessions.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class UserRole(str, Enum):
    ADMIN = "admin"
    MEMBER = "member"
    READ_ONLY = "read_only"


@dataclass
class AuthContext:
    """Security context derived from validated credentials."""
    tenant_id: str
    org_id: str
    user_id: Optional[str] = None
    role: UserRole = UserRole.MEMBER
    scopes: Set[str] = field(default_factory=lambda: {"read", "write"})
    authenticated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def has_permission(self, required_role: UserRole) -> bool:
        hierarchy = {
            UserRole.READ_ONLY: 1,
            UserRole.MEMBER: 2,
            UserRole.ADMIN: 3,
        }
        return hierarchy.get(self.role, 0) >= hierarchy.get(required_role, 0)


class AuthManager:
    """Handles API key generation, SHA-256 hashing, and tenant credential resolution."""

    def __init__(self):
        # In-memory store mapping hashed_key -> credential metadata (or backed by DB)
        self._key_store: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()

    def generate_api_key(
        self,
        tenant_id: str,
        org_id: Optional[str] = None,
        role: UserRole = UserRole.MEMBER,
        scopes: Optional[List[str]] = None,
    ) -> str:
        """Generates a secure API key (prefix `ak_live_`) and stores its SHA-256 hash."""
        random_secret = secrets.token_urlsafe(32)
        raw_key = f"ak_live_{random_secret}"
        hashed = self.hash_key(raw_key)

        self._key_store[hashed] = {
            "tenant_id": tenant_id,
            "org_id": org_id or tenant_id,
            "role": role,
            "scopes": set(scopes or ["read", "write"]),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "revoked": False,
        }
        return raw_key

    def revoke_api_key(self, raw_key: str) -> bool:
        hashed = self.hash_key(raw_key)
        if hashed in self._key_store:
            self._key_store[hashed]["revoked"] = True
            return True
        return False

    def resolve_api_key(self, raw_key: str) -> Optional[AuthContext]:
        """Resolves a raw API key directly and returns AuthContext if valid."""
        if not raw_key:
            return None
        hashed = self.hash_key(raw_key.strip())
        meta = self._key_store.get(hashed)
        if not meta or meta.get("revoked"):
            return None

        return AuthContext(
            tenant_id=meta["tenant_id"],
            org_id=meta["org_id"],
            role=meta["role"],
            scopes=meta["scopes"],
        )

    def authenticate_header(self, auth_header: Optional[str]) -> Optional[AuthContext]:
        """Parses Authorization header ('Bearer <key>') and returns AuthContext if valid."""
        if not auth_header:
            return None

        parts = auth_header.strip().split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None

        return self.resolve_api_key(parts[1])
