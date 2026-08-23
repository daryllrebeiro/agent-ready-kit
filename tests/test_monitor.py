"""Unit tests for score delta tracker and monitoring."""

from packages.core.monitor.tracker import ScoreDeltaTracker
from packages.core.schemas import ComponentStatus, Score, ScoreComponent


def test_score_delta_tracker_regression():
    c_base = ScoreComponent(name="llms_txt", display_name="llms.txt", score=100.0, weight=0.3, status=ComponentStatus.PASS)
    c_curr = ScoreComponent(name="llms_txt", display_name="llms.txt", score=0.0, weight=0.3, status=ComponentStatus.FAIL)

    base = Score(url="https://site.com", version="v0.1", overall_score=90.0, grade="A+", components=[c_base], summary="Good", recommendations=[])
    curr = Score(url="https://site.com", version="v0.1", overall_score=60.0, grade="C", components=[c_curr], summary="Degraded", recommendations=[])

    delta = ScoreDeltaTracker.compute_delta(base, curr)
    assert delta["change_type"] == "REGRESSION"
    assert delta["overall_score_delta"] == -30.0
    assert delta["grade_changed"] is True
    assert len(delta["regressions"]) == 1
    assert delta["regressions"][0]["component"] == "llms.txt"
