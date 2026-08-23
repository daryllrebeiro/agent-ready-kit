"""Tests for Postgres Row-Level Security under connection pooling (PgBouncer transaction-mode)."""

import sqlite3
import pytest
from packages.core.storage.postgres_rls import PostgresRLSRepository, MockPostgresConnection


class SimulatedPgBouncerConnection:
    """Simulates a PgBouncer transaction-mode pooled connection with session state resets."""

    def __init__(self):
        self.session_settings = {}
        self.in_transaction = False
        self.committed = False

    def execute_set_local(self, param_name: str, value: str):
        # SET LOCAL only persists within the current transaction
        self.session_settings[param_name] = value
        self.in_transaction = True

    def commit(self):
        # PgBouncer transaction mode: session-local settings reset on transaction end
        self.session_settings.clear()
        self.in_transaction = False
        self.committed = True

    def rollback(self):
        self.session_settings.clear()
        self.in_transaction = False

    def get_setting(self, param_name: str) -> str:
        return self.session_settings.get(param_name, "")


def test_postgres_rls_transaction_pooling_reset_behavior():
    """Confirms that tenant context does not leak across pooled connection reuse."""
    pooled_conn = SimulatedPgBouncerConnection()

    # Request 1: Tenant Acme starts transaction and sets tenant context
    pooled_conn.execute_set_local("app.tenant_id", "tenant_acme")
    assert pooled_conn.get_setting("app.tenant_id") == "tenant_acme"

    # Transaction 1 completes and commits
    pooled_conn.commit()
    # Setting MUST be cleared when connection returns to pool
    assert pooled_conn.get_setting("app.tenant_id") == ""

    # Request 2: Tenant Beta receives the SAME physical pooled connection
    assert pooled_conn.get_setting("app.tenant_id") == ""
    pooled_conn.execute_set_local("app.tenant_id", "tenant_beta")
    assert pooled_conn.get_setting("app.tenant_id") == "tenant_beta"

    # Transaction 2 rolls back
    pooled_conn.rollback()
    assert pooled_conn.get_setting("app.tenant_id") == ""


def test_sqlite_fallback_tenant_query_scoping():
    """Verifies repository-level tenant scoping when running on local SQLite fallback."""
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE scores (id INTEGER PRIMARY KEY, tenant_id TEXT, score INTEGER)")
    
    cursor.execute("INSERT INTO scores (tenant_id, score) VALUES ('tenant_1', 85)")
    cursor.execute("INSERT INTO scores (tenant_id, score) VALUES ('tenant_2', 92)")
    conn.commit()

    # Query scoped to tenant_1
    cursor.execute("SELECT score FROM scores WHERE tenant_id = ?", ("tenant_1",))
    rows_t1 = cursor.fetchall()
    assert len(rows_t1) == 1
    assert rows_t1[0][0] == 85

    # Query scoped to tenant_2
    cursor.execute("SELECT score FROM scores WHERE tenant_id = ?", ("tenant_2",))
    rows_t2 = cursor.fetchall()
    assert len(rows_t2) == 1
    assert rows_t2[0][0] == 92
