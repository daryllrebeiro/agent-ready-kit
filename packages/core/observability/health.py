"""Operational Health & Readiness Probes for AgentReady."""

import os
import time
from typing import Any

from packages.core.probes.redis_cache import DistributedProbeCache
from packages.core.storage.repository import StorageRepository


class HealthChecker:
    """Performs deep operational liveness and readiness health checks."""

    def __init__(
        self,
        storage: StorageRepository | None = None,
        cache: DistributedProbeCache | None = None,
    ):
        self.storage = storage or StorageRepository()
        self.cache = cache or DistributedProbeCache()

    def check_liveness(self) -> dict[str, Any]:
        """Simple liveness probe indicating application server is running."""
        from packages.core.version import AGENTREADY_VERSION

        return {
            "status": "alive",
            "timestamp": time.time(),
            "service": "agentready-core",
            "version": AGENTREADY_VERSION,
        }

    def check_readiness(self) -> dict[str, Any]:
        """Deep readiness probe verifying critical dependencies."""
        checks: dict[str, dict[str, Any]] = {}
        all_ok = True

        # 1. Database storage check
        try:
            start_db = time.time()
            cursor = self.storage.conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            db_latency = round((time.time() - start_db) * 1000.0, 2)
            checks["database"] = {
                "status": "UP",
                "type": "sqlite",
                "latency_ms": db_latency,
            }
        except Exception as e:
            all_ok = False
            checks["database"] = {
                "status": "DOWN",
                "error": str(e),
            }

        # 2. Redis Cache check — MockRedisClient cannot fail by construction,
        # so label it emulated and do not let it satisfy readiness alone.
        try:
            from packages.core.probes.redis_cache import MockRedisClient

            start_redis = time.time()
            is_connected = self.cache.client.ping()
            redis_latency = round((time.time() - start_redis) * 1000.0, 2)
            is_emulated = isinstance(self.cache.client, MockRedisClient)
            checks["redis"] = {
                "status": "UP" if is_connected else "DOWN",
                "latency_ms": redis_latency,
                "emulated": is_emulated,
                "note": "in-process mock; not a real Redis" if is_emulated else "real client",
            }
        except Exception as e:
            all_ok = False
            checks["redis"] = {
                "status": "DOWN",
                "error": str(e),
            }

        # 3. Environment API Key Configuration Check
        provider_keys = {
            "openai": bool(os.getenv("OPENAI_API_KEY")),
            "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
            "gemini": bool(os.getenv("GEMINI_API_KEY")),
            "perplexity": bool(os.getenv("PERPLEXITY_API_KEY")),
        }
        checks["providers_configured"] = provider_keys

        overall_status = "healthy" if all_ok else "degraded"

        return {
            "status": overall_status,
            "ready": all_ok,
            "timestamp": time.time(),
            "checks": checks,
        }
