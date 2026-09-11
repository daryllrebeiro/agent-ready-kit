"""Real Redis connection adapter for Phase 16 Task 4.

Provides a redis-py client presenting the same interface the mock exposes
(`get`, `setex`, `incrby`, `expire`, `ping`, `flushall`), so
`DistributedProbeCache` and `BudgetEnforcer` need no code changes.
"""

import os
from typing import Any, Optional

try:
    import redis
    _REDIS_AVAILABLE = True
except Exception:  # pragma: no cover
    redis = None  # type: ignore[assignment]
    _REDIS_AVAILABLE = False

DEFAULT_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6380/0")


def connect_real(url: Optional[str] = None) -> "redis.Redis":
    """Open a real Redis connection (raises if unreachable)."""
    if not _REDIS_AVAILABLE:
        raise RuntimeError("redis-py not installed. Install with: pip install redis")
    client = redis.Redis.from_url(url or DEFAULT_URL, decode_responses=True)
    client.ping()  # fail fast: unreachable Redis must not masquerade as healthy
    return client


def connect_shared() -> Any:
    """Shared-cache client for CLI/worker/budget paths.

    Returns a real Redis client when REDIS_URL (or the default local URL)
    is reachable, else the in-process MockRedisClient. The fallback is the
    pre-existing offline behavior — callers MUST surface which backend won
    via DistributedProbeCache.emulated so readiness stays honest.
    """
    try:
        return connect_real()
    except Exception:
        from packages.core.probes.redis_cache import MockRedisClient

        return MockRedisClient()