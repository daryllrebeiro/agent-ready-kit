"""Unit tests for GitHub PR comment formatting."""

from packages.cli.pr_comment import format_pr_comment
from packages.core.schemas import ComponentStatus, Score, ScoreComponent


def test_format_pr_comment():
    comp = ScoreComponent(
        name="llms_txt",
        display_name="llms.txt Compliance",
        score=95.0,
        weight=0.30,
        status=ComponentStatus.PASS,
        details="Valid llms.txt found",
    )
    score = Score(
        url="https://pr-preview.example.com",
        version="score_v0.1",
        overall_score=88.0,
        grade="A",
        components=[comp],
        summary="PR is agent-ready.",
        recommendations=["Add FAQ schema"],
    )

    comment_pass = format_pr_comment(score, min_score=80.0)
    assert "Passed" in comment_pass
    assert "https://pr-preview.example.com" in comment_pass
    assert "88.0/100" in comment_pass
    assert "Actionable Remediation Checklist" in comment_pass

    comment_fail = format_pr_comment(score, min_score=95.0)
    assert "FAILED" in comment_fail
