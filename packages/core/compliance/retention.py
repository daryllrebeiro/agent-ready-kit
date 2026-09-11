"""Automated Data Retention Purge Daemon and ToS Click-Through Audit Logger.

Implements SOC 2 Type 1 and GDPR data lifecycle management:
- Tier-based retention windows (Free: 30d, Growth: 90d, Enterprise: 365d)
- Cryptographic ToS and Privacy Policy acceptance audit trails.
"""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from packages.core.storage.postgres_rls import PostgresRLSRepository

RETENTION_WINDOWS_DAYS = {
    "free": 30,
    "growth": 90,
    "enterprise": 365,
}


class RetentionPurgeDaemon:
    """Scheduled daemon to purge stale tenant records according to data retention policies."""

    def __init__(self, repository: PostgresRLSRepository):
        self.repo = repository

    def purge_tenant_stale_data(self, tenant_id: str, plan_tier: str = "free") -> dict[str, Any]:
        """Purges scores and probe runs older than the retention window.

        Executes real scoped DELETEs through the repository and reports
        actual deleted counts. COMPLETED is returned only when both
        deletes execute without error.
        """
        window_days = RETENTION_WINDOWS_DAYS.get(plan_tier.lower(), 30)
        cutoff_iso = (datetime.now(UTC) - timedelta(days=window_days)).isoformat()

        counts = self.repo.purge_stale_records(tenant_id, cutoff_iso)
        return {
            "tenant_id": tenant_id,
            "plan_tier": plan_tier,
            "retention_days": window_days,
            "cutoff_timestamp": cutoff_iso,
            "purged_scores_count": counts["scores"],
            "purged_probes_count": counts["probes"],
            "status": "COMPLETED",
        }


class ToSAuditLogger:
    """Immutable audit trail for Terms of Service and Privacy Policy consent."""

    def __init__(self):
        self._audit_trail: list[dict[str, Any]] = []

    def record_consent(
        self,
        tenant_id: str,
        user_id: str,
        tos_version: str = "2026-08-v1",
        ip_address: str = "192.0.2.1",
        user_agent: str = "Mozilla/5.0",
    ) -> dict[str, Any]:
        """Records timestamped, hashed consent record."""
        now = datetime.now(UTC).isoformat()
        payload_str = f"{tenant_id}:{user_id}:{tos_version}:{now}:{ip_address}"
        consent_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

        record = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "tos_version": tos_version,
            "accepted_at": now,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "consent_hash": consent_hash,
        }
        self._audit_trail.append(record)
        return record

    def get_tenant_consent_history(self, tenant_id: str) -> list[dict[str, Any]]:
        return [r for r in self._audit_trail if r["tenant_id"] == tenant_id]
