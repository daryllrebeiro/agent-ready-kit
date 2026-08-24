"""Phase 13 Compliance & Enterprise Tests: Retention Purge, Data Export, and ToS Consent."""

import pytest
from packages.core.compliance.retention import RetentionPurgeDaemon, ToSAuditLogger
from packages.core.compliance.exporter import TenantDataExporter
from packages.core.storage.postgres_rls import MockPostgresConnection, PostgresRLSRepository
from packages.core.schemas import Score, ScoreComponent, ComponentStatus


def test_retention_purge_lifecycle_policies():
    """Verifies retention cutoff calculations across free, growth, and enterprise tiers."""
    pg_conn = MockPostgresConnection()
    repo = PostgresRLSRepository(connection=pg_conn)
    daemon = RetentionPurgeDaemon(repository=repo)

    # 1. Free tier (30 days)
    free_purge = daemon.purge_tenant_stale_data("tenant_free", plan_tier="free")
    assert free_purge["retention_days"] == 30
    assert free_purge["status"] == "COMPLETED"

    # 2. Growth tier (90 days)
    growth_purge = daemon.purge_tenant_stale_data("tenant_growth", plan_tier="growth")
    assert growth_purge["retention_days"] == 90

    # 3. Enterprise tier (365 days)
    ent_purge = daemon.purge_tenant_stale_data("tenant_ent", plan_tier="enterprise")
    assert ent_purge["retention_days"] == 365


def test_tenant_data_export_portability_and_isolation():
    """Verifies that self-service data export includes all tenant assets and never leaks cross-tenant records."""
    pg_conn = MockPostgresConnection()
    repo = PostgresRLSRepository(connection=pg_conn)

    # Setup Tenant Alpha
    repo.create_organization("tenant_alpha", "Alpha Corp", "enterprise")
    repo.get_or_create_domain("tenant_alpha", "https://alpha.com")
    score_alpha = Score(
        url="https://alpha.com",
        overall_score=92.0,
        grade="A",
        components=[ScoreComponent(name="robots_txt", display_name="Robots.txt", score=100.0, weight=0.2, status=ComponentStatus.PASS, details="OK")],
    )
    repo.save_score("tenant_alpha", "https://alpha.com", score_alpha)

    # Setup Tenant Beta
    repo.create_organization("tenant_beta", "Beta Corp", "growth")
    repo.get_or_create_domain("tenant_beta", "https://beta.com")

    # Run Exporter for Tenant Alpha
    exporter = TenantDataExporter(repository=repo)
    export_alpha = exporter.export_tenant_data_bundle("tenant_alpha")

    assert export_alpha["export_metadata"]["tenant_id"] == "tenant_alpha"
    assert export_alpha["domains_count"] == 1
    assert export_alpha["domains"][0]["domain_url"] == "https://alpha.com"
    assert len(export_alpha["domains"][0]["scores"]) == 1

    # Assert Tenant Beta data is not present in Alpha's export bundle
    export_str = str(export_alpha)
    assert "https://beta.com" not in export_str
    assert "tenant_beta" not in export_str


def test_tos_click_through_audit_logger():
    """Verifies cryptographic click-through consent recording for enterprise legal compliance."""
    logger = ToSAuditLogger()
    record = logger.record_consent(
        tenant_id="tenant_acme",
        user_id="user_admin_1",
        tos_version="2026-08-v2",
        ip_address="203.0.113.195",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    )

    assert record["tenant_id"] == "tenant_acme"
    assert record["tos_version"] == "2026-08-v2"
    assert len(record["consent_hash"]) == 64  # SHA-256 hex string

    history = logger.get_tenant_consent_history("tenant_acme")
    assert len(history) == 1
    assert history[0]["consent_hash"] == record["consent_hash"]
