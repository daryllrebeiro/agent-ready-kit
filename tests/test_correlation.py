"""Unit tests for Pearson/Spearman correlation math and calibration harness."""

from packages.core.correlation import (
    CorrelationHarness,
    compute_pearson_correlation,
    compute_spearman_rank_correlation,
)


def test_pearson_correlation_perfect():
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [10.0, 20.0, 30.0, 40.0, 50.0]
    r = compute_pearson_correlation(x, y)
    assert r == 1.0


def test_pearson_correlation_negative():
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [50.0, 40.0, 30.0, 20.0, 10.0]
    r = compute_pearson_correlation(x, y)
    assert r == -1.0


def test_spearman_rank_correlation():
    x = [10.0, 20.0, 30.0, 40.0, 50.0]
    y = [5.0, 6.0, 7.0, 8.0, 9.0]
    rho = compute_spearman_rank_correlation(x, y)
    assert rho == 1.0


def test_correlation_harness_dataset():
    harness = CorrelationHarness()
    samples = [
        {"score": {"overall_score": 90.0, "components": [{"name": "llms_txt", "score": 90}, {"name": "structured_data", "score": 90}, {"name": "token_bloat", "score": 90}, {"name": "bot_permissions", "score": 90}]}, "citation_rate": 0.90},
        {"score": {"overall_score": 70.0, "components": [{"name": "llms_txt", "score": 70}, {"name": "structured_data", "score": 70}, {"name": "token_bloat", "score": 70}, {"name": "bot_permissions", "score": 70}]}, "citation_rate": 0.70},
        {"score": {"overall_score": 30.0, "components": [{"name": "llms_txt", "score": 30}, {"name": "structured_data", "score": 30}, {"name": "token_bloat", "score": 30}, {"name": "bot_permissions", "score": 30}]}, "citation_rate": 0.20},
    ]

    res = harness.analyze_dataset(samples)
    assert res["overall_pearson_r"] > 0.90
    assert "STRONG POSITIVE CORRELATION" in res["finding"]
