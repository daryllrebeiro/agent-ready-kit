"""Autonomous scheduled probe daemon tracking recurring citation velocity and deltas."""

import time
from typing import Any, Dict, List, Optional
from packages.core.probes.runner import MultiModelProber
from packages.core.storage.repository import StorageRepository


class ProbeSchedulerDaemon:
    """Manages scheduled multi-model probe execution and citation velocity tracking."""

    def __init__(self, storage_repo: Optional[StorageRepository] = None):
        self.storage = storage_repo or StorageRepository()
        self.prober = MultiModelProber()
        self._registered_domains: List[str] = []

    def register_domain(self, domain: str) -> None:
        """Register domain for recurring probing."""
        clean = domain.strip().lower()
        if clean not in self._registered_domains:
            self._registered_domains.append(clean)

    def execute_probe_cycle(self, max_prompts_per_domain: int = 2, dry_run: bool = True) -> Dict[str, Any]:
        """Run single probing cycle across all registered domains."""
        timestamp = time.time()
        cycle_summary: Dict[str, Any] = {
            "timestamp": timestamp,
            "domains_probed": len(self._registered_domains),
            "domain_results": {},
        }

        for domain in self._registered_domains:
            results = self.prober.run_standard_probe_suite(
                target_domain=domain,
                max_prompts=max_prompts_per_domain,
                dry_run=dry_run,
            )

            total_probes = 0
            cited_probes = 0

            for prompt_run in results:
                for provider_name, res in prompt_run.get("probes", {}).items():
                    total_probes += 1
                    if res.is_cited:
                        cited_probes += 1
                    if not dry_run:
                        self.storage.save_probe_result(domain, res)

            citation_rate = round((cited_probes / max(1, total_probes)) * 100.0, 1)

            cycle_summary["domain_results"][domain] = {
                "total_probes": total_probes,
                "cited_probes": cited_probes,
                "citation_rate_pct": citation_rate,
            }

        return cycle_summary

    def calculate_citation_velocity(
        self,
        domain: str,
        current_rate_pct: float,
        previous_rate_pct: float,
    ) -> Dict[str, Any]:
        """Compute citation velocity delta and movement direction."""
        delta = round(current_rate_pct - previous_rate_pct, 1)
        if delta > 0:
            trend = "INCREASING"
        elif delta < 0:
            trend = "DECREASING"
        else:
            trend = "STABLE"

        return {
            "domain": domain,
            "current_rate_pct": current_rate_pct,
            "previous_rate_pct": previous_rate_pct,
            "velocity_delta": delta,
            "trend": trend,
        }
