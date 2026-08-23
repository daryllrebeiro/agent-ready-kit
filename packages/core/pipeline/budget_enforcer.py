"""Pre-Call Budget Enforcer & Abuse Controls.

Verifies tenant monthly quotas in Redis before issuing upstream LLM probe API calls.
Enforces hard stops to prevent spend runaway, global circuit breakers, and sub-limits for multipliers.
"""

from typing import Any, Dict, Optional
from packages.core.billing.stripe_engine import TIER_LIMITS
from packages.core.probes.redis_cache import DistributedProbeCache


class BudgetExceededError(Exception):
    """Raised when tenant has exhausted their monthly probe budget."""
    def __init__(self, tenant_id: str, limit: int, current: int, upgrade_url: Optional[str] = None):
        self.tenant_id = tenant_id
        self.limit = limit
        self.current = current
        self.upgrade_url = upgrade_url or f"https://app.agentready.dev/billing/upgrade?tenant_id={tenant_id}"
        super().__init__(
            f"Monthly probe budget exceeded for tenant '{tenant_id}'. "
            f"Limit: {limit}, Current Usage: {current}. Upgrade your plan at {self.upgrade_url}"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": "BUDGET_EXCEEDED",
            "tenant_id": self.tenant_id,
            "monthly_limit": self.limit,
            "current_usage": self.current,
            "upgrade_url": self.upgrade_url,
        }


class GlobalSpendCircuitBreakerTripped(Exception):
    """Raised when aggregate system-wide API spend velocity exceeds safeguard threshold."""
    pass


class BudgetEnforcer:
    """Pre-call budget enforcement coordinator."""

    def __init__(
        self,
        cache: Optional[DistributedProbeCache] = None,
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
    ) -> Dict[str, Any]:
        """Pre-flight check before calling upstream LLM providers.
        
        Raises BudgetExceededError if tenant has exceeded their monthly allowance.
        """
        # 1. Look up plan limits
        tier_cfg = TIER_LIMITS.get(plan_tier.lower(), TIER_LIMITS["free"])
        monthly_limit = tier_cfg["monthly_probe_budget"]

        # 2. Check current tenant usage
        current_usage = self.cache.get_tenant_usage(tenant_id)
        if current_usage + units_needed > monthly_limit:
            raise BudgetExceededError(tenant_id, monthly_limit, current_usage)

        # 3. Check Sub-limits for persona simulations & multilingual on Free tier
        if plan_tier.lower() == "free" and is_simulation_or_multilingual:
            if current_usage + units_needed > 20:
                raise BudgetExceededError(
                    tenant_id,
                    20,
                    current_usage,
                )

        # 4. Check Global system-wide circuit breaker
        global_usage = self.cache.client.incrby(self._global_usage_key, units_needed)
        if global_usage > self.global_monthly_max_units:
            raise GlobalSpendCircuitBreakerTripped("System-wide spend safeguard tripped.")

        # 5. Increment tenant usage
        new_total = self.cache.increment_tenant_usage(tenant_id, units_needed)

        return {
            "allowed": True,
            "tenant_id": tenant_id,
            "units_reserved": units_needed,
            "remaining_budget": max(0, monthly_limit - new_total),
            "plan_tier": plan_tier,
        }
