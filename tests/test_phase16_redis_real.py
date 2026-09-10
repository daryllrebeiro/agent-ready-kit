"""Phase 16 Task 4: real Redis wiring verification + fail-open test.

Verifies (a) budget enforcement uses real Redis, (b) dedup cache hits real Redis,
and (c) when Redis is killed mid-test, the application fails open (allows
through with degraded-mode counter incremented) rather than hard-crashing.
"""

import pytest
import subprocess
import time
import threading
import json
from http.client import HTTPConnection

import apps.web.server as web_server
from apps.web.server import DashboardAPIHandler
from packages.core.probes.redis_connection import connect_real
from packages.core.probes.redis_cache import DistributedProbeCache


@pytest.mark.integration
def test_real_redis_wired_for_budget_and_cache():
    """Real Redis is reachable; budget + cache ops hit the real server."""
    r = connect_real()
    assert r.ping(), "real Redis not reachable"

    # Budget counter via real Redis - clean up first
    cache = DistributedProbeCache(redis_client=r)
    # Clean up any existing test keys
    for key in r.keys("agentready:budget:tenant_redis_proof*"):
        r.delete(key)
    for key in r.keys("agentready:dedup:tenant_redis_proof*"):
        r.delete(key)

    before = cache.increment_tenant_usage("tenant_redis_proof", 1)
    assert before == 1
    after = cache.increment_tenant_usage("tenant_redis_proof", 2)
    assert after == 3

    # Dedup cache round-trip via real Redis
    from packages.core.schemas import ProbeResult
    pr = ProbeResult(provider="redis_proof", prompt="p", raw_response="r")
    cache.store_cached_probe("tenant_redis_proof", "redis_proof", "p", pr)
    got = cache.get_cached_probe("tenant_redis_proof", "redis_proof", "p")
    assert got is not None
    assert got.provider == "redis_proof"

    print("REAL-REDIS WIRED: budget + cache OK")


@pytest.mark.integration
def test_redis_kill_mid_test_fails_open():
    """Kill the Redis container mid-test, verify application fails open.

    This is the critical test that the mock-based `simulate_network_partition`
    flag could never genuinely prove — we literally `docker kill` the Redis
    container and confirm the app's degraded-mode counter increments and
    requests still complete (no hard crash, no unhandled exception).
    """
    # Skip if not running in Docker context (best-effort; CI can opt-in)
    try:
        subprocess.run(["docker", "ps", "-q", "-f", "name=agentready-redis"], check=True, capture_output=True)
    except Exception:
        pytest.skip("Docker not available; cannot test real Redis kill")

    # 1. Baseline: real Redis is up, budget + cache work
    r = connect_real()
    assert r.ping()
    cache = DistributedProbeCache(redis_client=r)
    cache.increment_tenant_usage("tenant_kill_test", 1)

    # 2. Kill Redis
    subprocess.run(["docker", "kill", "agentready-redis"], check=True)
    time.sleep(1)  # let TCP connections notice

    # 3. Operations should fail-open (return defaults, increment degraded_mode_events)
    degraded_before = cache.degraded_mode_events
    usage = cache.increment_tenant_usage("tenant_kill_test", 1)
    # fail-open returns the units_needed as fallback (see redis_cache.py:121)
    assert usage == 1
    assert cache.degraded_mode_events == degraded_before + 1

    # 4. Cache get/store also fail-open
    from packages.core.schemas import ProbeResult
    pr = ProbeResult(provider="kill_test", prompt="p", raw_response="r")
    got = cache.get_cached_probe("tenant_kill_test", "kill_test", "p")
    assert got is None
    assert cache.degraded_mode_events == degraded_before + 2
    cache.store_cached_probe("tenant_kill_test", "kill_test", "p", pr)
    assert cache.degraded_mode_events == degraded_before + 3

    # 5. Restart Redis for subsequent tests
    subprocess.run(["docker", "start", "agentready-redis"], check=True)
    time.sleep(1)
    assert connect_real().ping()

    print("REAL-REDIS FAIL-OPEN: verified")


if __name__ == "__main__":
    test_real_redis_wired_for_budget_and_cache()
    test_redis_kill_mid_test_fails_open()