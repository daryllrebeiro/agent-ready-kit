"""Unit tests for competitor benchmark engine."""

from packages.core.competitors.benchmark import CompetitorBenchmarkEngine


def test_competitor_benchmark_comparison():
    engine = CompetitorBenchmarkEngine()
    result = engine.compare_domains(
        target_url="https://agentready.dev",
        competitor_urls=["https://competitor-a.com", "https://competitor-b.com"],
        dry_run=True,
    )

    assert result["target_domain"] == "agentready.dev"
    assert "win_status" in result
    assert "target_citation_share_pct" in result
    assert len(result["readiness_ranking"]) == 3
    assert len(result["citation_counts"]) == 3
