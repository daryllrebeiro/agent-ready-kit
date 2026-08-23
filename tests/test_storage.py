"""Unit tests for SQLite storage layer and repository."""

import os
import pytest
from packages.core.schemas import ComponentStatus, ProbeResult, Score, ScoreComponent
from packages.core.storage.db import get_connection, init_db
from packages.core.storage.repository import StorageRepository


@pytest.fixture
def temp_repo(tmp_path):
    db_file = str(tmp_path / "test.db")
    conn = init_db(db_path=db_file)
    return StorageRepository(conn=conn)


def test_get_or_create_domain(temp_repo):
    d1 = temp_repo.get_or_create_domain("https://example.com/")
    assert d1["domain_url"] == "https://example.com"

    d2 = temp_repo.get_or_create_domain("https://example.com")
    assert d1["id"] == d2["id"]


def test_save_and_retrieve_score(temp_repo):
    comp = ScoreComponent(
        name="llms_txt",
        display_name="llms.txt Compliance",
        score=90.0,
        weight=0.30,
        status=ComponentStatus.PASS,
        details="Found valid llms.txt",
    )
    score = Score(
        url="https://agentready.dev",
        version="score_v0.1",
        overall_score=90.0,
        grade="A",
        components=[comp],
        summary="High readiness",
        recommendations=["Update regularly"],
    )

    score_id = temp_repo.save_score("https://agentready.dev", score)
    assert score_id > 0

    retrieved = temp_repo.get_latest_score("https://agentready.dev")
    assert retrieved is not None
    assert retrieved.overall_score == 90.0
    assert retrieved.grade == "A"
    assert len(retrieved.components) == 1
    assert retrieved.components[0].name == "llms_txt"


def test_save_and_retrieve_probe(temp_repo):
    probe = ProbeResult(
        provider="openai",
        prompt="best tools",
        raw_response="https://agentready.dev is top",
        cited_domains=["agentready.dev"],
        extracted_urls=["https://agentready.dev"],
        latency_ms=120.0,
    )

    p_id = temp_repo.save_probe_run("https://agentready.dev", probe)
    assert p_id > 0

    probes = temp_repo.get_probe_history("https://agentready.dev")
    assert len(probes) == 1
    assert probes[0]["provider"] == "openai"
    assert "agentready.dev" in probes[0]["cited_domains"]
