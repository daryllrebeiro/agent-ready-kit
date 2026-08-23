"""Unit and integration tests for AgentReady CLI."""

import json
import os
from unittest.mock import patch
from packages.cli.main import cli_entrypoint
from packages.core.schemas import ComponentStatus, Score, ScoreComponent

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")


def read_fixture(subpath: str) -> str:
    with open(os.path.join(FIXTURES_DIR, subpath), "r", encoding="utf-8") as f:
        return f.read()


@patch("packages.core.scorer.Scorer.score_url")
def test_cli_scan_min_score_success(mock_score_url):
    mock_score = Score(
        url="https://agentready.dev",
        version="score_v0.1",
        overall_score=88.5,
        grade="A",
        components=[
            ScoreComponent(
                name="llms_txt",
                display_name="llms.txt Compliance",
                score=90.0,
                weight=0.30,
                status=ComponentStatus.PASS,
            )
        ],
        summary="Excellent Agent Readiness.",
        recommendations=[],
    )
    mock_score_url.return_value = mock_score

    exit_code = cli_entrypoint(["scan", "https://agentready.dev", "--min-score", "80.0"])
    assert exit_code == 0


@patch("packages.core.scorer.Scorer.score_url")
def test_cli_scan_min_score_failure(mock_score_url):
    mock_score = Score(
        url="https://poor-site.com",
        version="score_v0.1",
        overall_score=42.0,
        grade="D",
        components=[
            ScoreComponent(
                name="llms_txt",
                display_name="llms.txt Compliance",
                score=0.0,
                weight=0.30,
                status=ComponentStatus.FAIL,
            )
        ],
        summary="Low Agent Readiness.",
        recommendations=["Add llms.txt"],
    )
    mock_score_url.return_value = mock_score

    # Should exit with 1 because 42.0 < 75.0
    exit_code = cli_entrypoint(["scan", "https://poor-site.com", "--min-score", "75.0"])
    assert exit_code == 1


@patch("packages.core.scorer.Scorer.score_url")
def test_cli_scan_json_output_file(mock_score_url, tmp_path):
    mock_score = Score(
        url="https://test.com",
        version="score_v0.1",
        overall_score=92.0,
        grade="A+",
        components=[],
        summary="Great",
        recommendations=[],
    )
    mock_score_url.return_value = mock_score

    output_file = str(tmp_path / "report.json")
    exit_code = cli_entrypoint(["scan", "https://test.com", "--json", "--output", output_file])
    assert exit_code == 0
    assert os.path.exists(output_file)

    with open(output_file, "r") as f:
        data = json.load(f)
        assert data["overall_score"] == 92.0
        assert data["grade"] == "A+"


def test_cli_generate(tmp_path):
    out_dir = str(tmp_path / "gen_output")
    exit_code = cli_entrypoint([
        "generate",
        "--url", "https://myproduct.com",
        "--name", "MyProduct",
        "--description", "AI-powered developer platform.",
        "--output-dir", out_dir,
    ])

    assert exit_code == 0
    llms_file = os.path.join(out_dir, "llms.txt")
    schema_file = os.path.join(out_dir, "schema-ld.json")

    assert os.path.exists(llms_file)
    assert os.path.exists(schema_file)

    with open(llms_file, "r", encoding="utf-8") as f:
        content = f.read()
        assert "# MyProduct" in content
        assert "> AI-powered developer platform." in content
