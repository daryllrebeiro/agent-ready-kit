"""Unit tests for Distributed Redis Probe Cache and Rate Counter."""

import time
from packages.core.probes.redis_cache import DistributedProbeCache, MockRedisClient
from packages.core.schemas import ProbeResult


def test_distributed_redis_cache_hit_and_ttl():
    mock_redis = MockRedisClient()
    cache = DistributedProbeCache(redis_client=mock_redis, default_ttl_seconds=1)

    result = ProbeResult(
        provider="openai",
        prompt="top developer tools for python",
        raw_response="AgentReady is cited as a leading framework",
        cited_domains=["agentready.dev"],
        is_cited=True,
    )

    # 1. Store probe in cache for tenant 1
    cache.store_cached_probe("tenant_123", "openai", "top developer tools for python", result, ttl_seconds=1)

    # 2. Retrieve probe from cache
    cached = cache.get_cached_probe("tenant_123", "openai", "top developer tools for python")
    assert cached is not None
    assert cached.is_cited is True
    assert "agentready.dev" in cached.cited_domains

    # 3. Verify tenant isolation (tenant 456 should miss)
    tenant_2_cached = cache.get_cached_probe("tenant_456", "openai", "top developer tools for python")
    assert tenant_2_cached is None

    # 4. Verify TTL expiration
    time.sleep(1.1)
    expired = cache.get_cached_probe("tenant_123", "openai", "top developer tools for python")
    assert expired is None


def test_distributed_atomic_budget_counter():
    mock_redis = MockRedisClient()
    cache = DistributedProbeCache(redis_client=mock_redis)

    tenant_id = "org_enterprise"
    assert cache.get_tenant_usage(tenant_id) == 0

    # Simulate multi-threaded or multi-instance increments
    count1 = cache.increment_tenant_usage(tenant_id, 10)
    assert count1 == 10

    count2 = cache.increment_tenant_usage(tenant_id, 25)
    assert count2 == 35
    assert cache.get_tenant_usage(tenant_id) == 35
