"""Probe orchestration and batch execution."""

from typing import Any, Dict, List, Optional
from packages.core.probes.base import BaseProbe
from packages.core.probes.prompts import STANDARD_PROBE_PROMPTS
from packages.core.probes.providers import AnthropicProbe, GeminiProbe, OpenAIProbe, PerplexityProbe
from packages.core.schemas import ProbeResult


class MultiModelProber:
    """Orchestrates multi-model citation probing across all major LLM search providers."""

    def __init__(self, providers: Optional[List[BaseProbe]] = None):
        self.providers = providers or [
            OpenAIProbe(),
            AnthropicProbe(),
            GeminiProbe(),
            PerplexityProbe(),
        ]

    def probe_prompt(
        self,
        prompt: str,
        target_domain: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Execute a prompt across all providers and check for citations of target_domain."""
        results: List[ProbeResult] = []
        is_cited_by: List[str] = []

        for provider in self.providers:
            res = provider.probe(prompt, dry_run=dry_run)
            results.append(res)
            if target_domain and target_domain.lower() in [d.lower() for d in res.cited_domains]:
                is_cited_by.append(provider.provider_name)

        return {
            "prompt": prompt,
            "target_domain": target_domain,
            "results": results,
            "cited_providers": is_cited_by,
            "citation_rate": len(is_cited_by) / len(self.providers) if self.providers else 0.0,
        }

    def run_standard_probe_suite(
        self,
        target_domain: Optional[str] = None,
        max_prompts: int = 5,
        dry_run: bool = False,
    ) -> List[Dict[str, Any]]:
        """Run standard benchmark prompts across all providers."""
        suite_results = []
        for prompt_meta in STANDARD_PROBE_PROMPTS[:max_prompts]:
            res = self.probe_prompt(
                prompt=prompt_meta["prompt"],
                target_domain=target_domain,
                dry_run=dry_run,
            )
            res["vertical"] = prompt_meta["vertical"]
            res["prompt_id"] = prompt_meta["id"]
            suite_results.append(res)
        return suite_results

    def run_prompt_suite(
        self,
        prompts: List[str],
        dry_run: bool = False,
    ) -> List[ProbeResult]:
        """Run multiple prompts across all providers and return flat list of ProbeResults."""
        all_results: List[ProbeResult] = []
        for p in prompts:
            for provider in self.providers:
                res = provider.probe(p, dry_run=dry_run)
                all_results.append(res)
        return all_results
