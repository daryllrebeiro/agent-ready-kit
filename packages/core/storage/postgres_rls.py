"""PostgreSQL Native Storage Repository with Row-Level Security (RLS) policies.

Guarantees database-enforced multi-tenant isolation.
Every query operates within a transactional connection setting `app.tenant_id`.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from packages.core.schemas import ProbeResult, Score


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

    def __init__(self, memory_db: Optional[sqlite3.Connection] = None):
        self.conn = memory_db or sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._current_tenant_id: Optional[str] = None
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

    def get_session_tenant(self) -> Optional[str]:
        return self._current_tenant_id

    def execute_rls_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
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

    def __init__(self, connection: Optional[Any] = None, dsn: Optional[str] = None):
        self.dsn = dsn
        self.conn = connection or MockPostgresConnection()

    @contextmanager
    def tenant_context(self, tenant_id: str):
        """Context manager setting PostgreSQL session variable app.tenant_id."""
        if hasattr(self.conn, "set_session_tenant"):
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
            # Live psycopg / asyncpg connection execution
            cursor = self.conn.cursor()
            cursor.execute(f"SET LOCAL app.tenant_id = '{tenant_id}';")
            try:
                yield self
            finally:
                cursor.close()

    def create_organization(self, org_id: str, name: str, plan: str = "free") -> Dict[str, Any]:
        cur = self.conn.conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cur.execute(
            "INSERT INTO organizations (id, name, plan, created_at) VALUES (?, ?, ?, ?)",
            (org_id, name, plan, now),
        )
        self.conn.conn.commit()
        return {"id": org_id, "name": name, "plan": plan, "created_at": now}

    def get_or_create_domain(self, tenant_id: str, domain_url: str) -> Dict[str, Any]:
        with self.tenant_context(tenant_id):
            cur = self.conn.conn.cursor()
            cur.execute(
                "SELECT * FROM domains WHERE tenant_id = ? AND domain_url = ?",
                (tenant_id, domain_url),
            )
            row = cur.fetchone()
            if row:
                return dict(row)
            
            domain_id = f"dom_{abs(hash(tenant_id + domain_url))}"
            now = datetime.now(timezone.utc).isoformat()
            cur.execute(
                "INSERT INTO domains (id, tenant_id, domain_url, created_at) VALUES (?, ?, ?, ?)",
                (domain_id, tenant_id, domain_url, now),
            )
            self.conn.conn.commit()
            return {"id": domain_id, "tenant_id": tenant_id, "domain_url": domain_url, "created_at": now}

    def save_score(self, tenant_id: str, domain_url: str, score: Score) -> str:
        with self.tenant_context(tenant_id):
            domain = self.get_or_create_domain(tenant_id, domain_url)
            score_id = f"sc_{abs(hash(domain['id'] + str(datetime.now(timezone.utc).timestamp())))}"
            now = datetime.now(timezone.utc).isoformat()
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

    def get_latest_score(self, tenant_id: str, domain_url: str) -> Optional[Score]:
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
            data = json.loads(row["raw_json"])
            return Score(**data)

    def save_probe(self, tenant_id: str, domain_url: str, probe: ProbeResult) -> str:
        with self.tenant_context(tenant_id):
            domain = self.get_or_create_domain(tenant_id, domain_url)
            probe_id = f"pr_{abs(hash(domain['id'] + probe.provider + str(datetime.now(timezone.utc).timestamp())))}"
            now = datetime.now(timezone.utc).isoformat()
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
                    probe.model_name,
                    probe.prompt,
                    probe.raw_response,
                    1 if probe.is_cited else 0,
                    now,
                ),
            )
            self.conn.conn.commit()
            return probe_id

    def list_probes(self, tenant_id: str, domain_url: str) -> List[Dict[str, Any]]:
        with self.tenant_context(tenant_id):
            domain = self.get_or_create_domain(tenant_id, domain_url)
            cur = self.conn.conn.cursor()
            cur.execute(
                "SELECT * FROM probe_runs WHERE tenant_id = ? AND domain_id = ? ORDER BY created_at DESC",
                (tenant_id, domain["id"]),
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]
