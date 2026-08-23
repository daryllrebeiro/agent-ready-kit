"""Competitor Generative Engine Optimization (GEO) benchmarking engine."""

from typing import Any, Dict, List
from packages.core.probes.extractor import extract_domain_from_url
from packages.core.probes.prompts import STANDARD_PROBE_PROMPTS
from packages.core.probes.runner import MultiModelProber
from packages.core.schemas import Score
from packages.core.scorer import Scorer


class CompetitorBenchmarkEngine:
    """Runs head-to-head citation and readiness comparisons between target domain and competitors."""

    def __init__(self):
        self.scorer = Scorer()
        self.prober = MultiModelProber()

    def compare_domains(
        self,
        target_url: str,
        competitor_urls: List[str],
        prompts: List[str] | None = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Execute full head-to-head comparison."""
        all_urls = [target_url] + competitor_urls
        all_domains = [extract_domain_from_url(u) for u in all_urls]
        target_domain = all_domains[0]

        # 1. Score all domains
        scores: Dict[str, Score] = {}
        for u in all_urls:
            scores[u] = self.scorer.score_url(u)

        # 2. Run citation probes across benchmark prompts
        test_prompts = prompts or [p["prompt"] for p in STANDARD_PROBE_PROMPTS[:3]]
        probe_results = self.prober.run_prompt_suite(test_prompts, dry_run=dry_run)

        # 3. Compute domain citation occurrences
        citation_counts: Dict[str, int] = {d: 0 for d in all_domains}
        provider_citations: Dict[str, Dict[str, int]] = {d: {} for d in all_domains}

        for res in probe_results:
            prov = res.provider
            for cited in res.cited_domains:
                for tracked_domain in all_domains:
                    if tracked_domain in cited or cited in tracked_domain:
                        citation_counts[tracked_domain] += 1
                        provider_citations[tracked_domain][prov] = provider_citations[tracked_domain].get(prov, 0) + 1

        total_tracked_citations = sum(citation_counts.values()) or 1
        target_citations = citation_counts.get(target_domain, 0)
        target_share_pct = round((target_citations / total_tracked_citations) * 100.0, 1)

        # 4. Compute win rate against competitors
        max_competitor_citations = max([citation_counts.get(d, 0) for d in all_domains[1:]] or [0])
        win_status = "WINNING" if target_citations > max_competitor_citations else "TIED" if target_citations == max_competitor_citations else "LOSING"

        # 5. Gap analysis
        readiness_ranking = sorted(
            [{"url": u, "domain": extract_domain_from_url(u), "score": scores[u].overall_score, "grade": scores[u].grade} for u in all_urls],
            key=lambda x: x["score"],
            reverse=True,
        )

        return {
            "target_url": target_url,
            "target_domain": target_domain,
            "win_status": win_status,
            "target_citation_share_pct": target_share_pct,
            "citation_counts": citation_counts,
            "provider_breakdown": provider_citations,
            "readiness_ranking": readiness_ranking,
            "total_prompts_tested": len(test_prompts),
        }
