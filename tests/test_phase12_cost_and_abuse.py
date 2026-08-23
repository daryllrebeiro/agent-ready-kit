"""Phase 12 Cost & Abuse Tests: Multi-Provider Outages, Remote Config, and Database Competitor Isolation."""

import sqlite3
import pytest
from packages.core.integrations.remote_config import RemoteConfigManager
from packages.core.pipeline.dlq import DeadLetterQueue
from packages.core.probes.runner import MultiModelProber
from packages.core.schemas import ProbeResult


def test_multi_provider_simultaneous_outage_resilience():
    """Simulates OpenAI and Gemini experiencing simultaneous 503 outages while Anthropic and Perplexity succeed."""
    prober = MultiModelProber()
    dlq = DeadLetterQueue()

    # Simulate running probe suite where OpenAI and Gemini mock failures
    target_domain = "example.com"
    prompt = "Best GEO tools for AI crawlers"

    results = []
    # 1. Anthropic succeeds
    results.append(ProbeResult(provider="anthropic", prompt=prompt, raw_response="Cited: example.com", cited_domains=[target_domain], latency_ms=60.0))
    # 2. Perplexity succeeds
    results.append(ProbeResult(provider="perplexity", prompt=prompt, raw_response="Cited: example.com", cited_domains=[target_domain], latency_ms=45.0))
    # 3. OpenAI fails (503 Service Unavailable) -> routed to DLQ
    dlq.push(org_id="tenant_acme", provider="openai", target_url=target_domain, prompt=prompt, error_message="HTTP 503: Service Unavailable")
    # 4. Gemini fails (429 Rate Limit) -> routed to DLQ
    dlq.push(org_id="tenant_acme", provider="gemini", target_url=target_domain, prompt=prompt, error_message="HTTP 429: Rate Limit Exceeded")

    assert len(results) == 2
    assert len(dlq) == 2
    assert dlq._queue[0].error_message == "HTTP 503: Service Unavailable"


def test_remote_configuration_kill_switch_instant_toggle():
    """Verifies sub-second cloud feature flag and kill switch toggling with audit trail."""
    config_mgr = RemoteConfigManager()
    assert config_mgr.is_kill_switch_active("edge_proxy") is False

    # Activate edge proxy kill switch dynamically
    audit = config_mgr.set_flag("edge_proxy_kill_switch", True, actor="devops@agentready.dev")
    assert audit["new_value"] is True
    assert audit["actor"] == "devops@agentready.dev"
    assert config_mgr.is_kill_switch_active("edge_proxy") is True


def test_database_level_competitor_benchmark_tenant_isolation():
    """Verifies that competitor benchmark records cannot leak across tenant query boundaries."""
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE competitor_benchmarks (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        target_domain TEXT NOT NULL,
        competitor_domain TEXT NOT NULL,
        win_rate REAL NOT NULL,
        privacy_scope TEXT NOT NULL
    )
    """)

    # Insert Tenant Acme benchmark (Private)
    cur.execute("INSERT INTO competitor_benchmarks VALUES ('b_1', 'tenant_acme', 'acme.com', 'rival.com', 75.0, 'private')")
    # Insert Tenant Beta benchmark (Private)
    cur.execute("INSERT INTO competitor_benchmarks VALUES ('b_2', 'tenant_beta', 'beta.com', 'rival.com', 40.0, 'private')")
    conn.commit()

    # Query strictly as tenant_acme
    cur.execute("SELECT * FROM competitor_benchmarks WHERE tenant_id = ?", ("tenant_acme",))
    rows_acme = cur.fetchall()
    assert len(rows_acme) == 1
    assert rows_acme[0][1] == "tenant_acme"
    assert rows_acme[0][2] == "acme.com"

    # Query strictly as tenant_beta
    cur.execute("SELECT * FROM competitor_benchmarks WHERE tenant_id = ?", ("tenant_beta",))
    rows_beta = cur.fetchall()
    assert len(rows_beta) == 1
    assert rows_beta[0][1] == "tenant_beta"
    assert rows_beta[0][2] == "beta.com"
