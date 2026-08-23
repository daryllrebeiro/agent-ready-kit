"""Unit tests for citation drift detection and score v0.2 evolution."""

from packages.core.drift import calculate_distribution_drift, upgrade_score_to_v0_2
from packages.core.schemas import ComponentStatus, Score, ScoreComponent


def test_calculate_distribution_drift():
    baseline = {"openai": 50, "anthropic": 30, "gemini": 20}
    # Stable current
    current_stable = {"openai": 49, "anthropic": 31, "gemini": 20}
    res = calculate_distribution_drift(baseline, current_stable)
    assert res["drift_score"] < 0.05
    assert "STABLE" in res["assessment"]

    # Heavy drift
    current_drifted = {"openai": 10, "anthropic": 80, "gemini": 10}
    res_drift = calculate_distribution_drift(baseline, current_drifted)
    assert res_drift["drift_score"] >= 0.25
    assert "SIGNIFICANT DRIFT" in res_drift["assessment"]


def test_upgrade_score_to_v0_2():
    comp_llms = ScoreComponent(
        name="llms_txt",
        display_name="llms.txt",
        score=100.0,
        weight=0.30,
        status=ComponentStatus.PASS,
    )
    score_v1 = Score(
        url="https://agentready.dev",
        version="score_v0.1",
        overall_score=80.0,
        grade="A",
        components=[comp_llms],
        summary="Test",
        recommendations=[],
    )

    score_v2 = upgrade_score_to_v0_2(score_v1)
    assert score_v2.version == "score_v0.2"
    assert score_v2.components[0].weight == 0.35  # Boosted in v0.2
