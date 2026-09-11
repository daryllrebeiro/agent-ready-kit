"""Postgres-backed API key store (Phase 16 follow-up: persistent auth).

Fixes the documented limitation of the in-process AuthManager: keys,
revocations, and expiries survive restarts because only SHA-256 hashes
are persisted in the global `api_keys` table. Raw keys are shown once
at mint time and never stored.

No mocks: all operations execute against a real PostgreSQL connection.
"""

import json
import secrets
import time
from datetime import UTC, datetime
from typing import Any

from packages.core.auth.middleware import AuthContext, UserRole
from packages.core.version import API_KEY_PREFIX

API_KEYS_DDL = """
CREATE TABLE IF NOT EXISTS api_keys (
    key_hash TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    org_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    scopes TEXT NOT NULL DEFAULT '["read", "write"]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() + INTERVAL '1 year',
    revoked BOOLEAN NOT NULL DEFAULT FALSE
);
"""


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


class PgAuthManager:
    """AuthManager-compatible key store backed by real Postgres.

    Implements the subset of the AuthManager surface the live request
    path needs: generate / resolve / revoke / share tokens are NOT
    persisted here (share tokens remain process-scoped by design and
    are short-lived); API keys are fully persistent.
    """

    def __init__(self, connection: Any):
        self.conn = connection
        self._share_tokens: dict[str, dict[str, Any]] = {}
        self._ensure_schema()

    @staticmethod
    def hash_key(raw_key: str) -> str:
        from packages.core.auth.middleware import AuthManager

        return AuthManager.hash_key(raw_key)

    def _ensure_schema(self) -> None:
        # Least-privilege app role has no CREATE; the table is created by
        # migration/DDL as superuser. Verify presence and fail with an
        # actionable message instead of attempting DDL at runtime.
        cur = self.conn.conn.cursor()
        cur.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'api_keys'"
        )
        if cur.fetchone() is None:
            raise RuntimeError(
                "api_keys table missing: run POSTGRES_RLS_SCHEMA_DDL "
                "(incl. api_keys) once as the superuser role, then retry"
            )

    def generate_api_key(
        self,
        tenant_id: str,
        org_id: str | None = None,
        role: UserRole = UserRole.MEMBER,
        scopes: list[str] | None = None,
    ) -> str:
        raw_key = f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"
        hashed = self.hash_key(raw_key)
        cur = self.conn.conn.cursor()
        # FK api_keys_tenant_id_fkey requires the org row: create idempotently.
        cur.execute(
            "INSERT INTO organizations (id, name, plan) VALUES (?, ?, 'free') "
            "ON CONFLICT (id) DO NOTHING",
            (tenant_id, tenant_id),
        )
        cur.execute(
            "INSERT INTO api_keys (key_hash, tenant_id, org_id, role, scopes, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                hashed,
                tenant_id,
                org_id or tenant_id,
                role.value if isinstance(role, UserRole) else str(role),
                json.dumps(list(scopes or ["read", "write"])),
                _utcnow_iso(),
            ),
        )
        self.conn.commit()
        return raw_key

    def revoke_api_key(self, raw_key: str) -> bool:
        cur = self.conn.conn.cursor()
        cur.execute(
            "UPDATE api_keys SET revoked = TRUE WHERE key_hash = ?",
            (self.hash_key(raw_key),),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def resolve_api_key(self, raw_key: str) -> AuthContext | None:
        if not raw_key:
            return None
        hashed = self.hash_key(raw_key.strip())

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

        cur = self.conn.conn.cursor()
        cur.execute(
            "SELECT tenant_id, org_id, role, scopes, revoked, expires_at "
            "FROM api_keys WHERE key_hash = ?",
            (hashed,),
        )
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("revoked"):
            return None
        try:
            expires = datetime.fromisoformat(str(d.get("expires_at")))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            if expires <= datetime.now(UTC):
                return None
        except Exception:
            return None
        role = UserRole(d.get("role") or "member")
        try:
            scopes = set(json.loads(d.get("scopes") or "[]"))
        except Exception:
            scopes = {"read", "write"}
        return AuthContext(
            tenant_id=d["tenant_id"],
            org_id=d.get("org_id") or d["tenant_id"],
            role=role,
            scopes=scopes,
        )

    def authenticate_header(self, auth_header: str | None) -> AuthContext | None:
        if not auth_header:
            return None
        scheme, _, credentials = auth_header.partition(" ")
        if scheme.lower() != "bearer" or not credentials.strip():
            return None
        return self.resolve_api_key(credentials.strip())

    def generate_domain_share_token(
        self, tenant_id: str, domain_url: str, ttl_seconds: int = 86400
    ) -> str:
        raw_token = f"dst_{secrets.token_urlsafe(24)}"
        hashed = self.hash_key(raw_token)
        self._share_tokens[hashed] = {
            "tenant_id": tenant_id,
            "domain_url": domain_url,
            "expires_at": time.time() + ttl_seconds,
            "revoked": False,
        }
        return raw_token
