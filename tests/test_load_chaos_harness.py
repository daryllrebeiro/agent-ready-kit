"""Multi-Tenant Concurrency and Chaos Spike Load Test Harness."""

import concurrent.futures
import time
import pytest
from packages.core.pipeline.budget_enforcer import (
    BudgetEnforcer,
    BudgetExceededError,
    GlobalSpendCircuitBreakerTripped,
)
from packages.core.probes.redis_cache import DistributedProbeCache, MockRedisClient


def test_concurrent_multi_tenant_spike_load_and_atomic_counters():
    """Simulates 100 concurrent tenants making rapid budget checks and usage increments."""
    mock_redis = MockRedisClient()
    cache = DistributedProbeCache(redis_client=mock_redis)
    enforcer = BudgetEnforcer(cache=cache)

    num_tenants = 100
    units_per_tenant = 5

    def worker_task(tenant_idx: int):
        tenant_id = f"tenant_load_test_{tenant_idx}"
        # Step 1: Pre-call budget reservation (Free tier: 100 units limit)
        res = enforcer.check_and_reserve_budget(
            tenant_id=tenant_id,
            plan_tier="free",
            units_needed=units_per_tenant,
        )
        return res["allowed"], res["remaining_budget"]

    # Execute all 100 tenants concurrently across a thread pool
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(worker_task, i) for i in range(num_tenants)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 100
    # Every individual tenant used 5 units out of 100 -> remaining should be 95
    for allowed, remaining in results:
        assert allowed is True
        assert remaining == 95


def test_concurrent_global_spend_circuit_breaker_trip_and_isolation():
    """Verifies that a massive concurrent spike across many tenants trips the global breaker reliably."""
    mock_redis = MockRedisClient()
    cache = DistributedProbeCache(redis_client=mock_redis)
    # Configure low global velocity threshold (200 units) to trigger during 100-tenant burst
    enforcer = BudgetEnforcer(cache=cache, global_monthly_max_units=200)

    num_tenants = 100
    trip_count = 0
    success_count = 0

    def spike_worker(tenant_idx: int):
        tenant_id = f"tenant_spike_{tenant_idx}"
        try:
            res = enforcer.check_and_reserve_budget(
                tenant_id=tenant_id,
                plan_tier="enterprise",
                units_needed=10,  # 100 * 10 = 1000 units total (exceeds 200 threshold)
            )
            if res["allowed"]:
                return "ALLOWED"
            return "BLOCKED"
        except GlobalSpendCircuitBreakerTripped:
            return "CIRCUIT_TRIPPED"

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(spike_worker, i) for i in range(num_tenants)]
        for f in concurrent.futures.as_completed(futures):
            outcome = f.result()
            if outcome == "CIRCUIT_TRIPPED":
                trip_count += 1
            elif outcome == "ALLOWED":
                success_count += 1

    # First ~20 calls should succeed until 200 threshold is reached, then subsequent calls trip
    assert success_count > 0
    assert trip_count > 0
    assert (success_count + trip_count) == num_tenants
