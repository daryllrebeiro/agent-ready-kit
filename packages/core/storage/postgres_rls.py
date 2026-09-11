"""PostgreSQL Native Storage Repository with Row-Level Security (RLS) policies.

Guarantees database-enforced multi-tenant isolation.
Every query operates within a transactional connection setting `app.tenant_id`.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from packages.core.schemas import ProbeResult, Score

try:
    from packages.core.storage.pg_connection import RealPgConnection
except Exception:  # pragma: no cover - psycopg absent in minimal envs
    RealPgConnection = None  # type: ignore[assignment,misc]

POSTGRES_RLS_SCHEMA_DDL = """
-- Organizations / Tenants Table
CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    plan TEXT NOT NULL DEFAULT 'free',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Domains Table (Tenant-scoped)
CREATE TABLE IF NOT EXISTS domains (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    domain_url TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (tenant_id, domain_url)
);

-- Scores Table (Tenant-scoped)
CREATE TABLE IF NOT EXISTS scores (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    domain_id TEXT NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    overall_score DOUBLE PRECISION NOT NULL,
    grade TEXT NOT NULL,
    score_version TEXT NOT NULL,
    raw_json JSONB NOT NULL,
    scanned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Probe Runs Table (Tenant-scoped)
CREATE TABLE IF NOT EXISTS probe_runs (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    domain_id TEXT NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    model_name TEXT,
    prompt TEXT NOT NULL,
    raw_response TEXT NOT NULL,
    is_cited BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Subscriptions Table (Tenant-scoped)
CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL UNIQUE REFERENCES organizations(id) ON DELETE CASCADE,
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    max_domains INTEGER NOT NULL DEFAULT 5,
    monthly_probe_budget INTEGER NOT NULL DEFAULT 500,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- API Keys Table (global: key hashes resolve tenants; never RLS-gated
-- because the key itself is the credential that establishes tenancy).
-- Only hashes are stored; raw keys are shown once at mint time.
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

-- Enable Native Database Row-Level Security
ALTER TABLE domains ENABLE ROW LEVEL SECURITY;
ALTER TABLE scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE probe_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;

-- Tenant Isolation Policies
DROP POLICY IF EXISTS tenant_isolation_domains ON domains;
CREATE POLICY tenant_isolation_domains ON domains
    FOR ALL USING (tenant_id = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS tenant_isolation_scores ON scores;
CREATE POLICY tenant_isolation_scores ON scores
    FOR ALL USING (tenant_id = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS tenant_isolation_probes ON probe_runs;
CREATE POLICY tenant_isolation_probes ON probe_runs
    FOR ALL USING (tenant_id = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS tenant_isolation_subscriptions ON subscriptions;
CREATE POLICY tenant_isolation_subscriptions ON subscriptions
    FOR ALL USING (tenant_id = current_setting('app.tenant_id', true));
"""


class MockPostgresConnection:
    """Emulates a PostgreSQL connection with native session variables and RLS policy enforcement.

    Used when connecting without a live external PostgreSQL instance (e.g. in standalone unit testing).
    """

    def __init__(self, memory_db: sqlite3.Connection | None = None):
        self.conn = memory_db or sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._current_tenant_id: str | None = None
        self._init_mock_schema()

    def _init_mock_schema(self):
        cur = self.conn.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS organizations (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            plan TEXT NOT NULL DEFAULT 'free',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS domains (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            domain_url TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (tenant_id, domain_url)
        );

        CREATE TABLE IF NOT EXISTS scores (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            domain_id TEXT NOT NULL,
            overall_score REAL NOT NULL,
            grade TEXT NOT NULL,
            score_version TEXT NOT NULL,
            raw_json TEXT NOT NULL,
            scanned_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS probe_runs (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            domain_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            model_name TEXT,
            prompt TEXT NOT NULL,
            raw_response TEXT NOT NULL,
            is_cited INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL UNIQUE,
            stripe_customer_id TEXT,
            stripe_subscription_id TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            max_domains INTEGER NOT NULL DEFAULT 5,
            monthly_probe_budget INTEGER NOT NULL DEFAULT 500,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)
        self.conn.commit()

    def set_session_tenant(self, tenant_id: str):
        self._current_tenant_id = tenant_id

    def get_session_tenant(self) -> str | None:
        return self._current_tenant_id

    def execute_rls_query(self, query: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Executes a query with strict RLS simulation (rejects operations missing tenant_id context)."""
        if not self._current_tenant_id:
            raise PermissionError("RLS Violation: app.tenant_id session variable is not set.")

        cur = self.conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()
        # Enforce RLS filter
        res = []
        for r in rows:
            d = dict(r)
            if "tenant_id" in d and d["tenant_id"] != self._current_tenant_id:
                continue
            res.append(d)
        return res


class PostgresRLSRepository:
    """PostgreSQL Repository with connection-level Row-Level Security."""

    def __init__(self, connection: Any | None = None, dsn: str | None = None):
        self.dsn = dsn
        # Both connection types expose set_session_tenant(); anything else
        # falls into the raw set_config branch of tenant_context.
        self.conn = connection or MockPostgresConnection()

    @contextmanager
    def tenant_context(self, tenant_id: str):
        """Context manager setting PostgreSQL session variable app.tenant_id."""
        session_types: tuple = (MockPostgresConnection,)
        if RealPgConnection is not None:
            session_types = (MockPostgresConnection, RealPgConnection)
        if isinstance(self.conn, session_types):
            prev = self.conn.get_session_tenant()
            self.conn.set_session_tenant(tenant_id)
            try:
                yield self
            finally:
                if prev:
                    self.conn.set_session_tenant(prev)
                else:
                    self.conn.set_session_tenant("")
        else:
            # Foreign live connection without the session interface:
            # parameterized set_config (SET does not allow bind params;
            # f-string interpolation here was injectable).
            raw_conn: Any = self.conn
            cursor = raw_conn.cursor()
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            try:
                yield self
            finally:
                cursor.close()

    def create_organization(self, org_id: str, name: str, plan: str = "free") -> dict[str, Any]:
        cur = self.conn.conn.cursor()
        now = datetime.now(UTC).isoformat()
        cur.execute(
            "INSERT INTO organizations (id, name, plan, created_at) VALUES (?, ?, ?, ?)",
            (org_id, name, plan, now),
        )
        self.conn.conn.commit()
        return {"id": org_id, "name": name, "plan": plan, "created_at": now}

    def get_or_create_domain(self, tenant_id: str, domain_url: str) -> dict[str, Any]:
        with self.tenant_context(tenant_id):
            cur = self.conn.conn.cursor()
            cur.execute(
                "SELECT * FROM domains WHERE tenant_id = ? AND domain_url = ?",
                (tenant_id, domain_url),
            )
            row = cur.fetchone()
            if row:
                return dict(row)

            import uuid

            domain_id = f"dom_{uuid.uuid4().hex[:16]}"
            now = datetime.now(UTC).isoformat()
            cur.execute(
                "INSERT INTO domains (id, tenant_id, domain_url, created_at) VALUES (?, ?, ?, ?)",
                (domain_id, tenant_id, domain_url, now),
            )
            self.conn.conn.commit()
            return {"id": domain_id, "tenant_id": tenant_id, "domain_url": domain_url, "created_at": now}

    def save_score(self, tenant_id: str, domain_url: str, score: Score) -> str:
        with self.tenant_context(tenant_id):
            import uuid

            domain = self.get_or_create_domain(tenant_id, domain_url)
            score_id = f"sc_{uuid.uuid4().hex[:16]}"
            now = datetime.now(UTC).isoformat()
            cur = self.conn.conn.cursor()
            cur.execute(
                """
                INSERT INTO scores (id, tenant_id, domain_id, overall_score, grade, score_version, raw_json, scanned_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    score_id,
                    tenant_id,
                    domain["id"],
                    score.overall_score,
                    score.grade,
                    score.version,
                    score.model_dump_json(),
                    now,
                ),
            )
            self.conn.conn.commit()
            return score_id

    def get_latest_score(self, tenant_id: str, domain_url: str) -> Score | None:
        with self.tenant_context(tenant_id):
            domain = self.get_or_create_domain(tenant_id, domain_url)
            cur = self.conn.conn.cursor()
            cur.execute(
                "SELECT * FROM scores WHERE tenant_id = ? AND domain_id = ? ORDER BY scanned_at DESC LIMIT 1",
                (tenant_id, domain["id"]),
            )
            row = cur.fetchone()
            if not row:
                return None
            # Real Postgres JSONB arrives parsed as dict; SQLite TEXT needs loads.
            raw = row["raw_json"]
            data = raw if isinstance(raw, dict) else json.loads(raw)
            return Score(**data)

    def save_probe(self, tenant_id: str, domain_url: str, probe: ProbeResult) -> str:
        with self.tenant_context(tenant_id):
            import uuid

            domain = self.get_or_create_domain(tenant_id, domain_url)
            probe_id = f"pr_{uuid.uuid4().hex[:16]}"
            now = datetime.now(UTC).isoformat()
            model_name = probe.model_name or (probe.metadata or {}).get("model", probe.provider)
            cur = self.conn.conn.cursor()
            cur.execute(
                """
                INSERT INTO probe_runs (id, tenant_id, domain_id, provider, model_name, prompt, raw_response, is_cited, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    probe_id,
                    tenant_id,
                    domain["id"],
                    probe.provider,
                    model_name,
                    probe.prompt,
                    probe.raw_response,
                    bool(probe.is_cited),
                    now,
                ),
            )
            self.conn.conn.commit()
            return probe_id

    def list_domains(self, tenant_id: str) -> list[dict[str, Any]]:
        with self.tenant_context(tenant_id):
            cur = self.conn.conn.cursor()
            cur.execute(
                "SELECT * FROM domains WHERE tenant_id = ? ORDER BY created_at ASC",
                (tenant_id,),
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    def get_score_history(self, tenant_id: str, domain_url: str, limit: int = 100) -> list[dict[str, Any]]:
        with self.tenant_context(tenant_id):
            domain = self.get_or_create_domain(tenant_id, domain_url)
            cur = self.conn.conn.cursor()
            cur.execute(
                "SELECT * FROM scores WHERE tenant_id = ? AND domain_id = ? ORDER BY scanned_at DESC LIMIT ?",
                (tenant_id, domain["id"], limit),
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    def purge_stale_records(self, tenant_id: str, cutoff_iso: str) -> dict[str, int]:
        """Delete scores/probe_runs older than cutoff_iso for one tenant.

        Returns actual deleted row counts (no simulation). Note the schema
        asymmetry: scores tracks scanned_at, probe_runs tracks created_at.
        Timestamps are ISO-8601 strings, so lexicographic comparison is
        chronological.
        """
        with self.tenant_context(tenant_id):
            cur = self.conn.conn.cursor()
            cur.execute(
                "DELETE FROM scores WHERE tenant_id = ? AND scanned_at < ?",
                (tenant_id, cutoff_iso),
            )
            scores = cur.rowcount
            cur.execute(
                "DELETE FROM probe_runs WHERE tenant_id = ? AND created_at < ?",
                (tenant_id, cutoff_iso),
            )
            probes = cur.rowcount
            self.conn.conn.commit()
            return {"scores": scores, "probes": probes}

    def list_probes(self, tenant_id: str, domain_url: str) -> list[dict[str, Any]]:
        with self.tenant_context(tenant_id):
            domain = self.get_or_create_domain(tenant_id, domain_url)
            cur = self.conn.conn.cursor()
            cur.execute(
                "SELECT * FROM probe_runs WHERE tenant_id = ? AND domain_id = ? ORDER BY created_at DESC",
                (tenant_id, domain["id"]),
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    def upsert_subscription(
        self,
        tenant_id: str,
        status: str,
        tier: str | None = None,
        stripe_customer_id: str | None = None,
        stripe_subscription_id: str | None = None,
    ) -> None:
        """Persist webhook-derived subscription state (Task 5 code-side).

        Called by the Stripe webhook endpoint after signature verification.
        Idempotent: one row per tenant, updated on repeat delivery.
        """
        from packages.core.billing.stripe_engine import TIER_LIMITS

        with self.tenant_context(tenant_id):
            cur = self.conn.conn.cursor()
            cur.execute(
                "SELECT tenant_id FROM subscriptions WHERE tenant_id = ?",
                (tenant_id,),
            )
            row = cur.fetchone()
            tier_key = (tier or "growth").lower()
            limits = TIER_LIMITS.get(tier_key, TIER_LIMITS["growth"])
            now = datetime.now(UTC).isoformat()
            if row is None:
                cur.execute(
                    """INSERT INTO subscriptions
                       (id, tenant_id, stripe_customer_id, stripe_subscription_id,
                        status, max_domains, monthly_probe_budget, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        f"sub_{tenant_id}",
                        tenant_id,
                        stripe_customer_id,
                        stripe_subscription_id,
                        status,
                        limits["max_domains"],
                        limits["monthly_probe_budget"],
                        now,
                        now,
                    ),
                )
            else:
                sets = ["status = ?", "updated_at = ?"]
                params: list = [status, now]
                if tier_key in TIER_LIMITS:
                    sets += ["max_domains = ?", "monthly_probe_budget = ?"]
                    params += [limits["max_domains"], limits["monthly_probe_budget"]]
                if stripe_customer_id:
                    sets.append("stripe_customer_id = ?")
                    params.append(stripe_customer_id)
                if stripe_subscription_id:
                    sets.append("stripe_subscription_id = ?")
                    params.append(stripe_subscription_id)
                params.append(tenant_id)
                cur.execute(
                    f"UPDATE subscriptions SET {', '.join(sets)} WHERE tenant_id = ?",
                    tuple(params),
                )
            self.conn.conn.commit()
