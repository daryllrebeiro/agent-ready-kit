"""Unit tests for Pre-Call Budget Enforcement & Rate Limits."""

import pytest
from packages.core.pipeline.budget_enforcer import (
    BudgetEnforcer,
    BudgetExceededError,
    GlobalSpendCircuitBreakerTripped,
)
from packages.core.probes.redis_cache import DistributedProbeCache, MockRedisClient


def test_budget_enforcer_free_tier_limits():
    mock_redis = MockRedisClient()
    cache = DistributedProbeCache(redis_client=mock_redis)
    enforcer = BudgetEnforcer(cache=cache)

    tenant_id = "tenant_free_user"

    # 1. Normal reserve within budget (free limit is 100)
    res = enforcer.check_and_reserve_budget(tenant_id, plan_tier="free", units_needed=10)
    assert res["allowed"] is True
    assert res["remaining_budget"] == 90

    # 2. Exceeding monthly limit
    with pytest.raises(BudgetExceededError, match="Monthly probe budget exceeded"):
        enforcer.check_and_reserve_budget(tenant_id, plan_tier="free", units_needed=95)


def test_budget_enforcer_sub_limits_on_free_tier():
    mock_redis = MockRedisClient()
    cache = DistributedProbeCache(redis_client=mock_redis)
    enforcer = BudgetEnforcer(cache=cache)

    tenant_id = "tenant_sublimit"

    # Multilingual/simulation sub-limit on free plan is 20
    with pytest.raises(BudgetExceededError):
        enforcer.check_and_reserve_budget(
            tenant_id,
            plan_tier="free",
            units_needed=25,
            is_simulation_or_multilingual=True,
        )


def test_budget_enforcer_global_spend_circuit_breaker():
    mock_redis = MockRedisClient()
    cache = DistributedProbeCache(redis_client=mock_redis)
    enforcer = BudgetEnforcer(cache=cache, global_monthly_max_units=50)

    # Trigger global spend circuit breaker
    with pytest.raises(GlobalSpendCircuitBreakerTripped):
        enforcer.check_and_reserve_budget("tenant_heavy", plan_tier="enterprise", units_needed=60)
