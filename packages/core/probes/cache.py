"""Probe deduplication and TTL caching layer to optimize probe costs."""

import hashlib
import time
from typing import Dict, Optional, Tuple
from packages.core.schemas import ProbeResult


class ProbeCache:
    """In-memory and durable TTL cache for LLM probe results."""

    def __init__(self, default_ttl_seconds: float = 21600.0):  # Default: 6 hours
        self.default_ttl = default_ttl_seconds
        # Map: cache_key -> (ProbeResult, expiry_timestamp)
        self._cache: Dict[str, Tuple[ProbeResult, float]] = {}
        self.hits = 0
        self.misses = 0

    def _make_key(self, provider: str, prompt: str) -> str:
        prompt_hash = hashlib.sha256(prompt.strip().lower().encode("utf-8")).hexdigest()[:16]
        return f"{provider.lower()}:{prompt_hash}"

    def get(self, provider: str, prompt: str) -> Optional[ProbeResult]:
        """Retrieve cached probe result if not expired."""
        key = self._make_key(provider, prompt)
        entry = self._cache.get(key)
        if not entry:
            self.misses += 1
            return None

        result, expiry = entry
        if time.time() > expiry:
            del self._cache[key]
            self.misses += 1
            return None

        self.hits += 1
        return result

    def set(self, provider: str, prompt: str, result: ProbeResult, ttl_seconds: Optional[float] = None) -> None:
        """Store probe result with TTL."""
        key = self._make_key(provider, prompt)
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        expiry = time.time() + ttl
        self._cache[key] = (result, expiry)

    def hit_rate(self) -> float:
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return round((self.hits / total) * 100.0, 1)

    def clear(self) -> None:
        self._cache.clear()
        self.hits = 0
        self.misses = 0
