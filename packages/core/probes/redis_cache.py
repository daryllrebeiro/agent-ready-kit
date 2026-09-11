"""Distributed Redis Probe Cache & Rate Counter with Failover and Partition Resilience.

Provides a 6-hour TTL prompt deduplication cache across multiple app/worker instances.
Tracks per-tenant atomic budget counters (tokens, probe counts) to prevent spend runaway.
Includes graceful fail-open degradation during Redis cluster failover or network partition.
"""

import hashlib
import json
import time
from typing import Any

from packages.core.schemas import ProbeResult


class MockRedisClient:
    """In-memory Redis emulator with node failure / partition simulation for testing."""

    def __init__(self, simulate_network_partition: bool = False):
        self._data: dict[str, str] = {}
        self._ttls: dict[str, float] = {}
        self._counters: dict[str, int] = {}
        self.simulate_network_partition = simulate_network_partition

    def _check_partition(self):
        if self.simulate_network_partition:
            raise ConnectionError(
                "Redis Cluster Error: CLUSTERDOWN The cluster is down (Simulated Split-Brain)"
            )

    def get(self, key: str) -> str | None:
        self._check_partition()
        if key in self._ttls and time.time() > self._ttls[key]:
            del self._data[key]
            del self._ttls[key]
            return None
        return self._data.get(key)

    def setex(self, key: str, seconds: int, value: str):
        self._check_partition()
        self._data[key] = value
        self._ttls[key] = time.time() + seconds

    def incrby(self, key: str, amount: int = 1) -> int:
        self._check_partition()
        val = self._counters.get(key, 0) + amount
        self._counters[key] = val
        return val

    def expire(self, key: str, seconds: int):
        self._check_partition()
        self._ttls[key] = time.time() + seconds

    def ping(self) -> bool:
        self._check_partition()
        return True

    def flushall(self):
        self._data.clear()
        self._ttls.clear()
        self._counters.clear()


class DistributedProbeCache:
    """Redis-backed distributed prompt deduplication and rate counter with partition resilience."""

    def __init__(
        self,
        redis_client: Any | None = None,
        default_ttl_seconds: int = 21600,
        fail_open_on_error: bool = True,
    ):
        # Default TTL is 6 hours (21600 seconds)
        # No explicit client -> shared real Redis when reachable, else the
        # pre-existing in-process mock (offline behavior, flagged emulated).
        if redis_client is None:
            from packages.core.probes.redis_connection import connect_shared

            redis_client = connect_shared()
        self.client = redis_client
        self.default_ttl = default_ttl_seconds
        self.fail_open_on_error = fail_open_on_error
        self.degraded_mode_events: int = 0

    @property
    def emulated(self) -> bool:
        """True when backed by the in-process mock (honest readiness)."""
        return isinstance(self.client, MockRedisClient)

    def _generate_cache_key(self, tenant_id: str, provider: str, prompt: str) -> str:
        prompt_hash = hashlib.sha256(prompt.strip().lower().encode("utf-8")).hexdigest()
        return f"agentready:dedup:{tenant_id}:{provider}:{prompt_hash}"

    def get_cached_probe(self, tenant_id: str, provider: str, prompt: str) -> ProbeResult | None:
        key = self._generate_cache_key(tenant_id, provider, prompt)
        try:
            raw_val = self.client.get(key)
            if not raw_val:
                return None
            data = json.loads(raw_val)
            return ProbeResult(**data)
        except Exception:
            if self.fail_open_on_error:
                self.degraded_mode_events += 1
                return None
            raise

    def store_cached_probe(
        self,
        tenant_id: str,
        provider: str,
        prompt: str,
        result: ProbeResult,
        ttl_seconds: int | None = None,
    ):
        key = self._generate_cache_key(tenant_id, provider, prompt)
        ttl = ttl_seconds or self.default_ttl
        payload = result.model_dump_json()
        try:
            self.client.setex(key, ttl, payload)
        except Exception:
            if self.fail_open_on_error:
                self.degraded_mode_events += 1
                return
            raise

    def increment_tenant_usage(self, tenant_id: str, probe_cost_units: int = 1) -> int:
        """Increments tenant probe counter and returns total units consumed in current cycle."""
        cycle_key = f"agentready:budget:{tenant_id}:{time.strftime('%Y%m')}"
        try:
            return self.client.incrby(cycle_key, probe_cost_units)
        except Exception:
            if self.fail_open_on_error:
                self.degraded_mode_events += 1
                return probe_cost_units  # Allow with warning fallback
            raise

    _RESERVE_LUA = """
    local current = tonumber(redis.call('GET', KEYS[1]) or '0')
    if current + tonumber(ARGV[1]) > tonumber(ARGV[2]) then
        return {0, current}
    end
    return {1, redis.call('INCRBY', KEYS[1], ARGV[1])}
    """

    def reserve_units_atomic(self, key: str, limit: int, units: int) -> tuple[bool, int]:
        """Atomically reserve `units` against `limit`; returns (allowed, new_total).

        Real Redis: single Lua script (no check-then-act race). In-process
        mock: guarded by a threading lock (same atomicity contract within
        the process). On transport failure with fail-open: allows with the
        requested units as the reported total and counts a degraded event.
        """
        try:
            if hasattr(self.client, "eval"):
                allowed, total = self.client.eval(self._RESERVE_LUA, 1, key, units, limit)
                return bool(allowed), int(total)
            lock = getattr(self.client, "_reserve_lock", None)
            if lock is None:
                import threading

                lock = threading.Lock()
                try:
                    self.client._reserve_lock = lock
                except Exception:
                    pass
            with lock:
                current = self.get_tenant_usage_for_key(key)
                if current + units > limit:
                    return False, current
                return True, self.client.incrby(key, units)
        except Exception:
            if self.fail_open_on_error:
                self.degraded_mode_events += 1
                return True, units
            raise

    def reserve_tenant_budget(self, tenant_id: str, limit: int, units: int) -> tuple[bool, int]:
        """Atomic tenant-budget reservation for the current cycle month."""
        cycle_key = f"agentready:budget:{tenant_id}:{time.strftime('%Y%m')}"
        allowed, total = self.reserve_units_atomic(cycle_key, limit, units)
        return allowed, total

    def refund_tenant_budget(self, tenant_id: str, units: int) -> None:
        """Return previously reserved units (best effort, never raises)."""
        cycle_key = f"agentready:budget:{tenant_id}:{time.strftime('%Y%m')}"
        try:
            self.client.incrby(cycle_key, -units)
        except Exception:
            pass

    def get_tenant_usage_for_key(self, key: str) -> int:
        """Read a raw counter key (cycle keys are built by callers)."""
        try:
            val = self.client.get(key)
            if val is None:
                if hasattr(self.client, "_counters"):
                    return self.client._counters.get(key, 0)
                return 0
            return int(val)
        except Exception:
            if self.fail_open_on_error:
                self.degraded_mode_events += 1
                return 0
            raise

    def get_tenant_usage(self, tenant_id: str) -> int:
        cycle_key = f"agentready:budget:{tenant_id}:{time.strftime('%Y%m')}"
        try:
            val = self.client.get(cycle_key)
            if val is None:
                if hasattr(self.client, "_counters"):
                    return self.client._counters.get(cycle_key, 0)
                return 0
            return int(val)
        except Exception:
            if self.fail_open_on_error:
                self.degraded_mode_events += 1
                return 0
            raise
