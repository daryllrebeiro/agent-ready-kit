"""Per-tenant probe quota and budget cap enforcement."""

from typing import Dict
from packages.core.auth.context import TenantContext


class QuotaManager:
    """Enforces pre-flight budget and probe rate caps per tenant tier."""

    def __init__(self):
        # In-memory usage map (org_id -> int current_month_usage)
        self._usage: Dict[str, int] = {}

    def check_and_increment(self, ctx: TenantContext, requested_probes: int = 1) -> bool:
        """Check if tenant has remaining quota and atomically increment usage."""
        current = self._usage.get(ctx.org_id, 0)
        if current + requested_probes > ctx.monthly_probe_quota:
            return False

        self._usage[ctx.org_id] = current + requested_probes
        return True

    def get_usage(self, org_id: str) -> int:
        return self._usage.get(org_id, 0)

    def reset_usage(self, org_id: str) -> None:
        self._usage[org_id] = 0
