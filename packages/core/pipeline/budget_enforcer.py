"""Pre-Call Budget Enforcer & Abuse Controls.

Verifies tenant monthly quotas in Redis before issuing upstream LLM probe API calls.
Enforces hard stops to prevent spend runaway, global circuit breakers, and sub-limits for multipliers.
"""

from typing import Any

from packages.core.billing.stripe_engine import TIER_LIMITS
from packages.core.probes.redis_cache import DistributedProbeCache


class BudgetExceededError(Exception):
    """Raised when tenant has exhausted their monthly probe budget."""

    def __init__(self, tenant_id: str, limit: int, current: int, upgrade_url: str | None = None):
        self.tenant_id = tenant_id
        self.limit = limit
        self.current = current
        self.upgrade_url = upgrade_url or f"https://app.agentready.dev/billing/upgrade?tenant_id={tenant_id}"
        super().__init__(
            f"Monthly probe budget exceeded for tenant '{tenant_id}'. "
            f"Limit: {limit}, Current Usage: {current}. Upgrade your plan at {self.upgrade_url}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": "BUDGET_EXCEEDED",
            "tenant_id": self.tenant_id,
            "monthly_limit": self.limit,
            "current_usage": self.current,
            "upgrade_url": self.upgrade_url,
        }


class GlobalSpendCircuitBreakerTripped(Exception):
    """Raised when aggregate system-wide API spend velocity exceeds safeguard threshold."""


class BudgetEnforcer:
    """Pre-call budget enforcement coordinator."""

    def __init__(
        self,
        cache: DistributedProbeCache | None = None,
        global_monthly_max_units: int = 500000,
    ):
        self.cache = cache or DistributedProbeCache()
        self.global_monthly_max_units = global_monthly_max_units
        self._global_usage_key = "agentready:global:spend:counter"

    def check_and_reserve_budget(
        self,
        tenant_id: str,
        plan_tier: str = "free",
        units_needed: int = 1,
        is_simulation_or_multilingual: bool = False,
    ) -> dict[str, Any]:
        """Pre-flight check before calling upstream LLM providers.

        Raises BudgetExceededError if tenant has exceeded their monthly allowance.
        """
        # 1. Look up plan limits
        tier_cfg = TIER_LIMITS.get(plan_tier.lower(), TIER_LIMITS["free"])
        monthly_limit = tier_cfg["monthly_probe_budget"]

        # 2-3. Atomic tenant reservation (single check-and-increment: no race,
        # and denied requests never inflate the counter).
        allowed, current_usage = self.cache.reserve_tenant_budget(tenant_id, monthly_limit, units_needed)
        if not allowed:
            raise BudgetExceededError(tenant_id, monthly_limit, current_usage)

        # 3b. Sub-limits for persona simulations & multilingual on Free tier.
        # current_usage includes this reservation; refund it on denial so a
        # sub-limit refusal never strands reserved units.
        if plan_tier.lower() == "free" and is_simulation_or_multilingual and current_usage > 20:
            self.cache.refund_tenant_budget(tenant_id, units_needed)
            raise BudgetExceededError(tenant_id, 20, current_usage - units_needed)

        # 4. Global system-wide circuit breaker, also atomic: a tripped
        # request reserves nothing (previously incrby ran before the trip
        # decision and permanently inflated the counter on every denial).
        global_allowed, _ = self.cache.reserve_units_atomic(
            self._global_usage_key, self.global_monthly_max_units, units_needed
        )
        if not global_allowed:
            raise GlobalSpendCircuitBreakerTripped("System-wide spend safeguard tripped.")

        new_total = current_usage

        return {
            "allowed": True,
            "tenant_id": tenant_id,
            "units_reserved": units_needed,
            "remaining_budget": max(0, monthly_limit - new_total),
            "plan_tier": plan_tier,
        }
