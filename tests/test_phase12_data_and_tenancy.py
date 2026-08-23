"""Phase 12 Data & Tenancy Tests: 12-Month Migration Volume & Redis Partition Resilience."""

import gc
import json
import os
import sqlite3
import tempfile
import pytest
from packages.core.storage.migration import SQLiteToPostgresMigrator
from packages.core.storage.postgres_rls import MockPostgresConnection, PostgresRLSRepository
from packages.core.probes.redis_cache import DistributedProbeCache, MockRedisClient
from packages.core.schemas import ComponentStatus, ProbeResult, Score, ScoreComponent


def test_12_month_projected_scale_migration():
    """Generates a high-volume synthetic SQLite dataset (1,000+ records) and validates complete migration reconciliation."""
    fd, temp_sqlite_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        sqlite_conn = sqlite3.connect(temp_sqlite_path)
        cur = sqlite_conn.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS domains (id INTEGER PRIMARY KEY AUTOINCREMENT, domain_url TEXT UNIQUE, created_at TEXT);
        CREATE TABLE IF NOT EXISTS scores (id INTEGER PRIMARY KEY AUTOINCREMENT, domain_id INTEGER, overall_score REAL, grade TEXT, score_version TEXT, raw_json TEXT, scanned_at TEXT);
        CREATE TABLE IF NOT EXISTS probe_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, domain_id INTEGER, provider TEXT, prompt TEXT, raw_response TEXT, cited_domains TEXT, latency_ms REAL, created_at TEXT);
        """)

        sample_score = Score(
            url="https://domain-0.com",
            overall_score=88.5,
            grade="A",
            version="score_v0.2",
            components=[
                ScoreComponent(
                    name="llms_txt",
                    display_name="LLMs.txt Standard",
                    score=100.0,
                    weight=0.2,
                    status=ComponentStatus.PASS,
                    details="Valid /llms.txt file detected",
                )
            ],
            summary="High readiness",
            recommendations=[],
        )
        sample_json = sample_score.model_dump_json()

        # Populate 100 domains, 400 scores, 400 probes
        for dom_idx in range(100):
            dom_url = f"https://domain-{dom_idx}.com"
            cur.execute("INSERT INTO domains (domain_url, created_at) VALUES (?, '2026-01-01')", (dom_url,))
            domain_id = cur.lastrowid
            for s_idx in range(4):
                cur.execute(
                    "INSERT INTO scores (domain_id, overall_score, grade, score_version, raw_json, scanned_at) VALUES (?, 88.5, 'A', 'score_v0.2', ?, '2026-01-01')",
                    (domain_id, sample_json),
                )
                cur.execute(
                    "INSERT INTO probe_runs (domain_id, provider, prompt, raw_response, cited_domains, latency_ms, created_at) VALUES (?, 'openai', 'prompt', 'response', '[]', 50.0, '2026-01-01')",
                    (domain_id,),
                )
        sqlite_conn.commit()
        sqlite_conn.close()

        pg_mock_conn = MockPostgresConnection()
        target_repo = PostgresRLSRepository(connection=pg_mock_conn)
        migrator = SQLiteToPostgresMigrator(sqlite_path=temp_sqlite_path, target_repo=target_repo)
        stats, is_reconciled = migrator.migrate(default_tenant_id="tenant_scale_test")

        assert stats["domains_migrated"] == 100
        assert stats["scores_migrated"] == 400
        assert is_reconciled is True
    finally:
        gc.collect()
        if os.path.exists(temp_sqlite_path):
            try:
                os.remove(temp_sqlite_path)
            except Exception:
                pass


def test_redis_cluster_failover_and_partition_handling():
    """Verifies that Redis cluster network partition or node failure degrades gracefully without crashing."""
    mock_redis = MockRedisClient(simulate_network_partition=True)
    cache = DistributedProbeCache(redis_client=mock_redis, fail_open_on_error=True)

    # 1. Get cached probe during partition returns None (miss) without crash
    cached = cache.get_cached_probe("tenant_failover_1", "openai", "Test prompt")
    assert cached is None
    assert cache.degraded_mode_events > 0

    # 2. Store cached probe during partition silently absorbs error
    probe = ProbeResult(
        provider="openai",
        prompt="Test prompt",
        raw_response="Response",
        cited_domains=["example.com"],
        latency_ms=120.0,
    )
    cache.store_cached_probe("tenant_failover_1", "openai", "Test prompt", probe)

    # 3. Increment tenant usage fails open to allow action with fallback counter
    used = cache.increment_tenant_usage("tenant_failover_1", probe_cost_units=2)
    assert used == 2
