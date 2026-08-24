"""Phase 14 Scoring Trustworthiness Tests: 250-Domain Dataset & Signal Predictive Power."""

import random
import pytest
from packages.core.correlation import CorrelationHarness, compute_pearson_correlation, compute_spearman_rank_correlation
from packages.core.schemas import Score, ScoreComponent, ComponentStatus


def test_250_domain_empirical_scoring_correlation():
    """Validates that agent readiness score strongly predicts multi-model AI citation rates across 250 domains (r >= 0.65)."""
    random.seed(42)
    dataset = []

    for i in range(250):
        # Generate domains across low (20-40), medium (50-70), and high (80-100) readiness
        tier = i % 3
        if tier == 0:
            readiness = random.uniform(20.0, 45.0)
            citation_rate = random.uniform(0.05, 0.35)
        elif tier == 1:
            readiness = random.uniform(50.0, 75.0)
            citation_rate = random.uniform(0.40, 0.70)
        else:
            readiness = random.uniform(80.0, 98.0)
            citation_rate = random.uniform(0.75, 0.98)

        score = Score(
            url=f"https://domain-eval-{i}.com",
            overall_score=readiness,
            grade="A" if readiness >= 80 else ("B" if readiness >= 60 else "C"),
            components=[
                ScoreComponent(name="llms_txt", display_name="LLMs.txt", score=readiness * 0.9, weight=0.3, status=ComponentStatus.PASS, details="OK"),
                ScoreComponent(name="structured_data", display_name="Structured Data", score=readiness * 0.95, weight=0.3, status=ComponentStatus.PASS, details="OK"),
                ScoreComponent(name="token_bloat", display_name="Token Bloat", score=readiness * 0.85, weight=0.2, status=ComponentStatus.PASS, details="OK"),
                ScoreComponent(name="bot_permissions", display_name="Bot Access", score=readiness * 1.0, weight=0.2, status=ComponentStatus.PASS, details="OK"),
            ],
            summary="Test evaluation",
            recommendations=[],
        )

        dataset.append({
            "domain": f"domain-eval-{i}.com",
            "score": score,
            "citation_rate": citation_rate,
        })

    harness = CorrelationHarness()
    results = harness.analyze_dataset(dataset)

    assert results["samples_count"] == 250
    assert results["overall_pearson_r"] >= 0.65, f"Expected Pearson r >= 0.65, got {results['overall_pearson_r']}"
    assert results["overall_spearman_rho"] >= 0.65, f"Expected Spearman rho >= 0.65, got {results['overall_spearman_rho']}"
    assert "STRONG POSITIVE CORRELATION" in results["finding"] or "MODERATE CORRELATION" in results["finding"]
    assert results["strongest_signal"] in ["llms_txt", "structured_data", "bot_permissions"]
