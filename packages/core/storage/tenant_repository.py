"""Tenant-isolated repository ensuring query-level multi-tenant boundaries."""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from packages.core.auth.context import TenantContext
from packages.core.schemas import ProbeResult, Score


def init_multitenant_db(conn: sqlite3.Connection) -> None:
    """Initialize multi-tenant SaaS tables."""
    with conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS organizations (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            tier TEXT NOT NULL DEFAULT 'growth',
            monthly_quota INTEGER NOT NULL DEFAULT 500,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id TEXT NOT NULL,
            key_hash TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tenant_domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id TEXT NOT NULL,
            domain_url TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_scanned_at TEXT,
            UNIQUE(org_id, domain_url),
            FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tenant_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id TEXT NOT NULL,
            domain_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            version TEXT NOT NULL,
            overall_score REAL NOT NULL,
            grade TEXT NOT NULL,
            score_data_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (domain_id) REFERENCES tenant_domains(id) ON DELETE CASCADE,
            FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tenant_probes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id TEXT NOT NULL,
            domain_id INTEGER,
            provider TEXT NOT NULL,
            prompt TEXT NOT NULL,
            raw_response TEXT NOT NULL,
            cited_domains_json TEXT NOT NULL,
            latency_ms REAL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (domain_id) REFERENCES tenant_domains(id) ON DELETE SET NULL,
            FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_tenant_domains ON tenant_domains(org_id);
        CREATE INDEX IF NOT EXISTS idx_tenant_scores ON tenant_scores(org_id, domain_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_tenant_probes ON tenant_probes(org_id, domain_id, created_at DESC);
        """)


class MultiTenantRepository:
    """Repository strictly enforcing tenant isolation at the data access layer."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        init_multitenant_db(self.conn)

    def create_organization(self, org_id: str, name: str, tier: str = "growth", monthly_quota: int = 500) -> Dict[str, Any]:
        """Provision a new organization."""
        now = datetime.now(timezone.utc).isoformat()
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO organizations (id, name, tier, monthly_quota, created_at) VALUES (?, ?, ?, ?, ?)",
            (org_id, name, tier, monthly_quota, now),
        )
        self.conn.commit()
        return {"id": org_id, "name": name, "tier": tier, "monthly_quota": monthly_quota}

    def register_api_key(self, org_id: str, key_hash: str, name: str = "Default Key") -> int:
        """Register an API key hash for an organization."""
        now = datetime.now(timezone.utc).isoformat()
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO api_keys (org_id, key_hash, name, created_at) VALUES (?, ?, ?, ?)",
            (org_id, key_hash, name, now),
        )
        self.conn.commit()
        return cursor.lastrowid

    def add_domain(self, ctx: TenantContext, domain_url: str) -> Dict[str, Any]:
        """Add domain belonging strictly to the authenticated tenant."""
        if not ctx.can_modify_domains():
            raise PermissionError(f"User with role {ctx.role} cannot add domains.")

        norm_url = domain_url.strip().rstrip("/").lower()
        now = datetime.now(timezone.utc).isoformat()
        cursor = self.conn.cursor()

        # Check domain count quota
        cursor.execute("SELECT COUNT(*) as cnt FROM tenant_domains WHERE org_id = ?", (ctx.org_id,))
        count = cursor.fetchone()["cnt"]
        if count >= ctx.max_domains:
            raise ValueError(f"Domain limit reached ({count}/{ctx.max_domains}) for tier {ctx.tier}.")

        cursor.execute(
            "INSERT INTO tenant_domains (org_id, domain_url, created_at) VALUES (?, ?, ?)",
            (ctx.org_id, norm_url, now),
        )
        self.conn.commit()
        return {"id": cursor.lastrowid, "org_id": ctx.org_id, "domain_url": norm_url}

    def list_domains(self, ctx: TenantContext) -> List[Dict[str, Any]]:
        """List domains strictly scoped to ctx.org_id."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM tenant_domains WHERE org_id = ? ORDER BY created_at DESC",
            (ctx.org_id,),
        )
        return [dict(r) for r in cursor.fetchall()]

    def get_domain(self, ctx: TenantContext, domain_id: int) -> Optional[Dict[str, Any]]:
        """Get single domain verifying org_id ownership."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM tenant_domains WHERE id = ? AND org_id = ?",
            (domain_id, ctx.org_id),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def save_score(self, ctx: TenantContext, domain_id: int, score: Score) -> int:
        """Persist a score report ensuring domain belongs to the active tenant."""
        domain = self.get_domain(ctx, domain_id)
        if not domain:
            raise PermissionError("Access denied: Target domain does not belong to this organization.")

        now = datetime.now(timezone.utc).isoformat()
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO tenant_scores (
                org_id, domain_id, url, version, overall_score, grade, score_data_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ctx.org_id,
                domain_id,
                score.url,
                score.version,
                score.overall_score,
                score.grade,
                score.model_dump_json(),
                now,
            ),
        )
        score_id = cursor.lastrowid
        cursor.execute(
            "UPDATE tenant_domains SET last_scanned_at = ? WHERE id = ? AND org_id = ?",
            (now, domain_id, ctx.org_id),
        )
        self.conn.commit()
        return score_id

    def list_scores(self, ctx: TenantContext, domain_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """List scores strictly scoped to ctx.org_id."""
        domain = self.get_domain(ctx, domain_id)
        if not domain:
            raise PermissionError("Access denied: Domain does not belong to this organization.")

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM tenant_scores WHERE org_id = ? AND domain_id = ? ORDER BY created_at DESC LIMIT ?",
            (ctx.org_id, domain_id, limit),
        )
        return [dict(r) for r in cursor.fetchall()]

    def save_probe(self, ctx: TenantContext, domain_id: int, probe_res: ProbeResult) -> int:
        """Save probe result enforcing tenant boundary."""
        domain = self.get_domain(ctx, domain_id)
        if not domain:
            raise PermissionError("Access denied: Domain does not belong to this organization.")

        now = datetime.now(timezone.utc).isoformat()
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO tenant_probes (
                org_id, domain_id, provider, prompt, raw_response, cited_domains_json, latency_ms, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ctx.org_id,
                domain_id,
                probe_res.provider,
                probe_res.prompt,
                probe_res.raw_response,
                json.dumps(probe_res.cited_domains),
                probe_res.latency_ms,
                now,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid
