"""Distributed Redis Probe Cache & Rate Counter.

Provides a 6-hour TTL prompt deduplication cache across multiple app/worker instances.
Tracks per-tenant atomic budget counters (tokens, probe counts) to prevent spend runaway.
"""

import hashlib
import json
import time
from typing import Any, Dict, Optional
from packages.core.schemas import ProbeResult


class MockRedisClient:
    """In-memory Redis emulator for testing or environments without live Redis."""

    def __init__(self):
        self._data: Dict[str, str] = {}
        self._ttls: Dict[str, float] = {}
        self._counters: Dict[str, int] = {}

    def get(self, key: str) -> Optional[str]:
        if key in self._ttls and time.time() > self._ttls[key]:
            del self._data[key]
            del self._ttls[key]
            return None
        return self._data.get(key)

    def setex(self, key: str, seconds: int, value: str):
        self._data[key] = value
        self._ttls[key] = time.time() + seconds

    def incrby(self, key: str, amount: int = 1) -> int:
        val = self._counters.get(key, 0) + amount
        self._counters[key] = val
        return val

    def expire(self, key: str, seconds: int):
        self._ttls[key] = time.time() + seconds

    def flushall(self):
        self._data.clear()
        self._ttls.clear()
        self._counters.clear()


class DistributedProbeCache:
    """Redis-backed distributed prompt deduplication and rate counter."""

    def __init__(self, redis_client: Optional[Any] = None, default_ttl_seconds: int = 21600):
        # Default TTL is 6 hours (21600 seconds)
        self.client = redis_client or MockRedisClient()
        self.default_ttl = default_ttl_seconds

    def _generate_cache_key(self, tenant_id: str, provider: str, prompt: str) -> str:
        prompt_hash = hashlib.sha256(prompt.strip().lower().encode("utf-8")).hexdigest()
        return f"agentready:dedup:{tenant_id}:{provider}:{prompt_hash}"

    def get_cached_probe(self, tenant_id: str, provider: str, prompt: str) -> Optional[ProbeResult]:
        key = self._generate_cache_key(tenant_id, provider, prompt)
        raw_val = self.client.get(key)
        if not raw_val:
            return None
        try:
            data = json.loads(raw_val)
            return ProbeResult(**data)
        except Exception:
            return None

    def store_cached_probe(
        self,
        tenant_id: str,
        provider: str,
        prompt: str,
        result: ProbeResult,
        ttl_seconds: Optional[int] = None,
    ):
        key = self._generate_cache_key(tenant_id, provider, prompt)
        ttl = ttl_seconds or self.default_ttl
        payload = result.model_dump_json()
        self.client.setex(key, ttl, payload)

    def increment_tenant_usage(self, tenant_id: str, probe_cost_units: int = 1) -> int:
        """Increments tenant probe counter and returns total units consumed in current cycle."""
        cycle_key = f"agentready:budget:{tenant_id}:{time.strftime('%Y%m')}"
        return self.client.incrby(cycle_key, probe_cost_units)

    def get_tenant_usage(self, tenant_id: str) -> int:
        cycle_key = f"agentready:budget:{tenant_id}:{time.strftime('%Y%m')}"
        val = self.client.get(cycle_key)
        if val is None:
            # Fallback for mock counter
            if hasattr(self.client, "_counters"):
                return self.client._counters.get(cycle_key, 0)
            return 0
        return int(val)
