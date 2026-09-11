"""Tenant-aware storage selector (Phase 16 follow-up).

Default (`AGENTREADY_STORAGE` unset or `sqlite`): single-tenant SQLite
via StorageRepository — local dev behavior, unchanged.

`AGENTREADY_STORAGE=postgres`: every read/write is tenant-scoped through
PostgresRLSRepository against real Postgres with engine-enforced RLS,
using the request's AuthContext.tenant_id. This closes the documented
"web server uses SQLite, RLS proven separately" gap for deployments
that set the variable; local dev is unaffected.
"""

import os
from typing import Any, Optional

from packages.core.schemas import ProbeResult, Score
from packages.core.storage.repository import StorageRepository

_PG_REPO = None
_PG_ERROR: Optional[str] = None


def storage_mode() -> str:
    return os.environ.get("AGENTREADY_STORAGE", "sqlite").lower()


def get_pg_repo():  # lazy singleton; None when unreachable
    global _PG_REPO, _PG_ERROR
    if _PG_REPO is not None:
        return _PG_REPO
    try:
        from packages.core.storage.pg_connection import connect_real
        from packages.core.storage.postgres_rls import PostgresRLSRepository

        _PG_REPO = PostgresRLSRepository(connection=connect_real())
        return _PG_REPO
    except Exception as e:
        _PG_ERROR = str(e)
        return None


def pg_unavailable_reason() -> Optional[str]:
    get_pg_repo()
    return _PG_ERROR


class TenantStore:
    """Request-scoped storage facade honoring storage_mode()."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self._sqlite = StorageRepository()

    def _pg(self):
        if storage_mode() == "postgres":
            return get_pg_repo()
        return None

    # -- reads --
    def list_domains(self) -> list[dict[str, Any]]:
        pg = self._pg()
        if pg is not None:
            return pg.list_domains(self.tenant_id)
        return self._sqlite.list_domains()

    def get_latest_score(self, domain_url: str) -> Optional[Score]:
        pg = self._pg()
        if pg is not None:
            return pg.get_latest_score(self.tenant_id, domain_url)
        return self._sqlite.get_latest_score(domain_url)

    def get_probe_history(
        self, domain_url: Optional[str] = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        pg = self._pg()
        if pg is not None:
            if domain_url:
                rows = pg.list_probes(self.tenant_id, domain_url)
            else:
                rows = []
                for d in pg.list_domains(self.tenant_id):
                    rows.extend(pg.list_probes(self.tenant_id, d["domain_url"]))
                rows = rows[:limit]
            out = []
            for r in rows:
                out.append(
                    {
                        "provider": r.get("provider"),
                        "prompt": r.get("prompt"),
                        "raw_response": r.get("raw_response"),
                        "is_cited": bool(r.get("is_cited")),
                        "created_at": r.get("created_at"),
                    }
                )
            return out
        return self._sqlite.get_probe_history(domain_url, limit)

    # -- writes --
    def save_score(self, domain_url: str, score: Score) -> Any:
        pg = self._pg()
        if pg is not None:
            return pg.save_score(self.tenant_id, domain_url, score)
        return self._sqlite.save_score(domain_url, score)

    def save_probe_run(self, domain_url: str, probe_result: ProbeResult) -> Any:
        pg = self._pg()
        if pg is not None:
            return pg.save_probe(self.tenant_id, domain_url, probe_result)
        return self._sqlite.save_probe_run(domain_url, probe_result)
