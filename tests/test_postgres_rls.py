"""Unit tests for PostgreSQL Native Row-Level Security (RLS) and Migration."""

import pytest

from packages.core.schemas import Score, ScoreComponent
from packages.core.storage.migration import SQLiteToPostgresMigrator
from packages.core.storage.postgres_rls import (
    POSTGRES_RLS_SCHEMA_DDL,
    MockPostgresConnection,
    PostgresRLSRepository,
)


def test_postgres_rls_ddl_and_policies_structure():
    assert "CREATE TABLE IF NOT EXISTS organizations" in POSTGRES_RLS_SCHEMA_DDL
    assert "ALTER TABLE domains ENABLE ROW LEVEL SECURITY;" in POSTGRES_RLS_SCHEMA_DDL
    assert "CREATE POLICY tenant_isolation_domains" in POSTGRES_RLS_SCHEMA_DDL
    assert "CREATE POLICY tenant_isolation_scores" in POSTGRES_RLS_SCHEMA_DDL


def test_postgres_rls_multi_tenant_isolation_boundary():
    repo = PostgresRLSRepository()

    # Create two distinct organizations
    repo.create_organization("org_alpha", "Alpha Corp", "enterprise")
    repo.create_organization("org_beta", "Beta LLC", "growth")

    score_alpha = Score(
        url="https://alpha.com",
        overall_score=88.0,
        grade="B",
        components=[
            ScoreComponent(
                name="structured_data",
                display_name="Structured Data",
                weight=0.25,
                score=88.0,
                status="PASS",
                details="Alpha schema valid",
            )
        ],
        recommendations=["Expand schema"],
    )

    score_beta = Score(
        url="https://beta.com",
        overall_score=94.0,
        grade="A",
        components=[
            ScoreComponent(
                name="structured_data",
                display_name="Structured Data",
                weight=0.25,
                score=94.0,
                status="PASS",
                details="Beta schema valid",
            )
        ],
        recommendations=[],
    )

    # Save scores under their respective tenants
    repo.save_score("org_alpha", "https://alpha.com", score_alpha)
    repo.save_score("org_beta", "https://beta.com", score_beta)

    # 1. Verify tenant alpha can read only alpha score
    retrieved_alpha = repo.get_latest_score("org_alpha", "https://alpha.com")
    assert retrieved_alpha is not None
    assert retrieved_alpha.overall_score == 88.0

    # 2. Verify tenant alpha cannot read beta's score
    cross_read = repo.get_latest_score("org_alpha", "https://beta.com")
    # Querying https://beta.com under org_alpha should yield None because domain was created for beta
    assert cross_read is None

    # 3. Verify mock RLS query engine rejects access without tenant session
    mock_conn = MockPostgresConnection()
    with pytest.raises(PermissionError, match="RLS Violation"):
        mock_conn.execute_rls_query("SELECT * FROM scores")


def test_sqlite_to_postgres_migration(tmp_path):
    # Seed via the real SQLite repository schema (db.py: domains/scores with
    # components_json) — the migrator reads that schema, not the legacy
    # raw_json layout. See M1 P0-1.3.

    from packages.core.storage.repository import StorageRepository

    db_file = str(tmp_path / "test_source.db")
    repo = StorageRepository(db_path=db_file)
    sample_score = Score(
        url="https://migrated.com",
        overall_score=85.0,
        grade="B",
        components=[],
        recommendations=[],
    )
    repo.save_score("https://migrated.com", sample_score)
    repo.conn.commit()
    repo.conn.close()

    target_repo = PostgresRLSRepository()
    migrator = SQLiteToPostgresMigrator(db_file, target_repo)
    stats, is_reconciled = migrator.migrate("org_migrated")

    assert is_reconciled is True
    assert stats["domains_migrated"] == 1
    assert stats["scores_migrated"] == 1

    migrated_score = target_repo.get_latest_score("org_migrated", "https://migrated.com")
    assert migrated_score is not None
    assert migrated_score.overall_score == 85.0
