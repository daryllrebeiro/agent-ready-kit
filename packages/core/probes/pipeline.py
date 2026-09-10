"""Guarded probe pipeline: single composition root for live probe spend.

M1b (IMPLEMENTATION_PLAN.md 1.5): every live provider call passes through
budget -> dedup cache -> circuit breaker -> provider -> cache store, with
failures captured in the DLQ. In-process adapters now; Redis impl later
behind the same DistributedProbeCache interface.
"""

from dataclasses import dataclass, field

from packages.core.pipeline.budget_enforcer import BudgetEnforcer
from packages.core.pipeline.circuit_breaker import CircuitBreaker
from packages.core.pipeline.dlq import DeadLetterQueue
from packages.core.probes.base import BaseProbe
from packages.core.probes.redis_cache import DistributedProbeCache
from packages.core.schemas import ProbeResult


class ProviderCircuitOpen(Exception):
    """Raised when a provider's circuit breaker refuses execution."""


@dataclass
class ProbePipeline:
    """Compose the existing guard stack around provider calls."""

    budget: BudgetEnforcer = field(default_factory=BudgetEnforcer)
    cache: DistributedProbeCache = field(default_factory=DistributedProbeCache)
    breakers: dict[str, CircuitBreaker] | None = None
    dlq: DeadLetterQueue = field(default_factory=DeadLetterQueue)
    tenant_id: str = "local"
    org_id: str = "local"
    target_url: str = ""
    plan_tier: str = "free"

    def __post_init__(self) -> None:
        self.breakers = self.breakers or {}
        # Share one cache client between budget accounting and dedup cache so
        # usage reservations are visible to both (separate Mock clients would
        # silently diverge and budget checks would never trip).
        try:
            self.budget.cache = self.cache
        except Exception:
            pass

    def _breaker_for(self, provider_name: str) -> CircuitBreaker:
        if provider_name not in self.breakers:
            self.breakers[provider_name] = CircuitBreaker(name=provider_name)
        return self.breakers[provider_name]

    def run(self, provider: BaseProbe, prompt: str, dry_run: bool = False) -> ProbeResult:
        """Execute one guarded probe. Budget is checked pre-spend; dry runs
        skip budget reservation (no spend) but still honor cache/breaker."""
        if not dry_run:
            self.budget.check_and_reserve_budget(self.tenant_id, self.plan_tier)

        cached = self.cache.get_cached_probe(self.tenant_id, provider.provider_name, prompt)
        if cached is not None:
            return cached

        breaker = self._breaker_for(provider.provider_name)
        if not breaker.can_execute():
            raise ProviderCircuitOpen(provider.provider_name)

        try:
            result = provider.probe(prompt, dry_run=dry_run)
            # Provider-level API errors are recorded as ProbeResults containing
            # "[API Error" text — treat as failure for breaker/DLQ purposes so
            # flaky providers cannot pollute citation stats silently.
            if not dry_run and result.raw_response.startswith(("[API Error", "[Exception]")):
                raise RuntimeError(result.raw_response[:500])
            breaker.record_success()
            if not dry_run:
                self.cache.store_cached_probe(self.tenant_id, provider.provider_name, prompt, result)
            return result
        except ProviderCircuitOpen:
            raise
        except Exception as e:
            breaker.record_failure()
            if not dry_run:
                self.dlq.push(self.org_id, provider.provider_name, self.target_url, prompt, str(e))
            raise
