"""Unit tests for citation anomaly detector and root cause diagnosis."""

from packages.core.integrations.anomalies import CitationAnomalyDetector
from packages.core.schemas import ComponentStatus, Score, ScoreComponent


def test_citation_anomaly_detection_and_slack_payload():
    detector = CitationAnomalyDetector(drop_threshold_pct=20.0)

    # Mock a score with blocked robots
    mock_score = Score(
        url="https://example.com",
        domain="example.com",
        overall_score=35.0,
        grade="F",
        components=[
            ScoreComponent(
                name="bot_permissions",
                display_name="AI Bot Permissions",
                score=0.0,
                weight=0.25,
                status=ComponentStatus.FAIL,
                evidence={},
                details="Robots blocked",
                recommendations=[],
            )
        ],
    )

    anomaly = detector.detect_citation_drop(
        domain="example.com",
        current_rate_pct=10.0,
        baseline_rate_pct=50.0,
        latest_score=mock_score,
    )

    assert anomaly is not None
    assert anomaly["drop_percentage_points"] == 40.0
    assert anomaly["severity"] == "SEV-2"
    assert any("robots.txt" in d.lower() for d in anomaly["diagnoses"])

    slack_msg = detector.format_slack_anomaly_alert(anomaly)
    assert "SEV-2" in slack_msg["text"]
    assert len(slack_msg["blocks"]) >= 4
