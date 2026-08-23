"""Unified Authentication, RBAC & Scoped Domain Share Token Middleware.

Resolves incoming credentials (Bearer API Keys, session tokens, scoped share tokens) into an AuthContext
that supplies `tenant_id` to PostgreSQL Row-Level Security sessions.
"""

import hashlib
import hmac
import secrets
import time
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
    scoped_domain: Optional[str] = None

    def has_permission(self, required_role: UserRole) -> bool:
        hierarchy = {
            UserRole.READ_ONLY: 1,
            UserRole.MEMBER: 2,
            UserRole.ADMIN: 3,
        }
        return hierarchy.get(self.role, 0) >= hierarchy.get(required_role, 0)

    def can_access_domain(self, domain_url: str) -> bool:
        if not self.scoped_domain:
            return True
        return self.scoped_domain.lower() in domain_url.lower()


class AuthManager:
    """Handles API key generation, SHA-256 hashing, tenant credential resolution, and domain share tokens."""

    def __init__(self):
        self._key_store: Dict[str, Dict[str, Any]] = {}
        self._share_tokens: Dict[str, Dict[str, Any]] = {}

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

    def generate_domain_share_token(
        self,
        tenant_id: str,
        domain_url: str,
        ttl_seconds: int = 86400,
    ) -> str:
        """Generates a single-domain scoped read-only share token (prefix `dst_`)."""
        raw_token = f"dst_{secrets.token_urlsafe(24)}"
        hashed = self.hash_key(raw_token)
        self._share_tokens[hashed] = {
            "tenant_id": tenant_id,
            "domain_url": domain_url,
            "expires_at": time.time() + ttl_seconds,
            "revoked": False,
        }
        return raw_token

    def revoke_api_key(self, raw_key: str) -> bool:
        hashed = self.hash_key(raw_key)
        if hashed in self._key_store:
            self._key_store[hashed]["revoked"] = True
            return True
        return False

    def resolve_api_key(self, raw_key: str) -> Optional[AuthContext]:
        """Resolves a raw API key or scoped share token directly into an AuthContext."""
        if not raw_key:
            return None
        hashed = self.hash_key(raw_key.strip())

        # 1. Check scoped domain share tokens
        if raw_key.startswith("dst_"):
            token_meta = self._share_tokens.get(hashed)
            if not token_meta or token_meta.get("revoked") or time.time() > token_meta["expires_at"]:
                return None
            return AuthContext(
                tenant_id=token_meta["tenant_id"],
                org_id=token_meta["tenant_id"],
                role=UserRole.READ_ONLY,
                scopes={"read:domain"},
                scoped_domain=token_meta["domain_url"],
            )

        # 2. Check regular organization API keys
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
