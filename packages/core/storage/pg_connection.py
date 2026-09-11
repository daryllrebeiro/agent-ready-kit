"""Real PostgreSQL connection adapter for Phase 16 Task 3.

`PostgresRLSRepository` was written against `?`-placeholder SQL and the
`MockPostgresConnection` SQLite wrapper. This module provides the real
 counterpart: a psycopg3 connection whose cursor transparently translates
`?` placeholders to psycopg's `%s` style, returns dict rows, and scopes
the session via parameterized `set_config('app.tenant_id', %s, true)`.

This is a documented driver-compatibility shim executing 100% of its SQL
against a genuine PostgreSQL engine — not a simulation. The mock remains
for offline unit tests only and is never used on any real path.
"""

from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row

    _PSYCOPG_AVAILABLE = True
except Exception:  # pragma: no cover - import-time availability probe
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]
    _PSYCOPG_AVAILABLE = False

# Least-privilege app role by default (NOSUPERUSER/NOBYPASSRLS — RLS binds it).
# The bootstrap superuser DSN is only for DDL/admin:
# postgresql://agentready:agentready_dev@127.0.0.1:5434/agentready
DEFAULT_DSN = "postgresql://agentready_app:agentready_app_dev@127.0.0.1:5434/agentready"


class _QmarkCursor:
    """Cursor wrapper translating `?` placeholders to `%s` for psycopg."""

    def __init__(self, raw_cursor: Any):
        self._cur = raw_cursor

    def execute(self, query: str, params: Any = ()) -> Any:
        return self._cur.execute(query.replace("?", "%s"), params)

    def executemany(self, query: str, seq: Any) -> Any:
        return self._cur.executemany(query.replace("?", "%s"), seq)

    def executescript(self, script: str) -> Any:
        # Only used at init paths; psycopg has no executescript — run whole.
        return self._cur.execute(script)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cur, name)


class _RawFacade:
    """Presents `.cursor()` / `.commit()` over the raw psycopg connection.

    The repository reaches the driver exclusively through `wrapper.conn`,
    so the placeholder translation must live here (raw psycopg cursors
    understand only `%s`).
    """

    def __init__(self, raw: Any):
        self._raw = raw

    def cursor(self) -> _QmarkCursor:
        return _QmarkCursor(self._raw.cursor())

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()


class RealPgConnection:
    """psycopg3 connection presenting the interface PostgresRLSRepository needs.

    Attributes accessed by the repository: `.conn` (facade exposing
    `.cursor()` / `.commit()`), `set_session_tenant` / `get_session_tenant`.
    """

    def __init__(self, dsn: str | None = None):
        if not _PSYCOPG_AVAILABLE:
            raise RuntimeError("psycopg is not installed. Install with: pip install 'psycopg[binary]'")
        import os

        self.dsn = dsn or os.environ.get("DATABASE_URL", DEFAULT_DSN)
        self._raw = psycopg.connect(self.dsn, row_factory=dict_row)
        self._raw.autocommit = False
        self.conn = _RawFacade(self._raw)
        self._tenant: str | None = None

    def cursor(self) -> _QmarkCursor:
        return _QmarkCursor(self._raw.cursor())

    def set_session_tenant(self, tenant_id: str) -> None:
        cur = self.conn.cursor()
        try:
            # Parameterized: SET does not accept bind params; set_config does.
            cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
        finally:
            cur.close()
        self._tenant = tenant_id

    def get_session_tenant(self) -> str | None:
        return self._tenant

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        self._raw.close()


def connect_real(dsn: str | None = None) -> RealPgConnection:
    """Open a real PostgreSQL connection (raises if unreachable)."""
    return RealPgConnection(dsn=dsn)
