"""Unit tests for probe scheduler daemon."""

from packages.core.probes.scheduler import ProbeSchedulerDaemon


def test_probe_scheduler_daemon_lifecycle():
    daemon = ProbeSchedulerDaemon()
    daemon.register_domain("example.com")
    daemon.register_domain("agentready.dev")

    cycle = daemon.execute_probe_cycle(max_prompts_per_domain=1, dry_run=True)

    assert cycle["domains_probed"] == 2
    assert "example.com" in cycle["domain_results"]
    assert "agentready.dev" in cycle["domain_results"]

    velocity = daemon.calculate_citation_velocity(
        "example.com", current_rate_pct=75.0, previous_rate_pct=50.0
    )
    assert velocity["velocity_delta"] == 25.0
    assert velocity["trend"] == "INCREASING"


def test_probe_scheduler_persists_runs_when_not_dry_run(tmp_path, monkeypatch):
    """Phase 17 regression: execute_probe_cycle used to iterate a nonexistent
    'probes' key and call a nonexistent save_probe_result — persisting
    nothing while reporting success. Without env API keys, providers fall
    back to simulated responses, so this runs offline."""

    from packages.core.storage.repository import StorageRepository

    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "PERPLEXITY_API_KEY"):
        monkeypatch.delenv(var, raising=False)

    db_path = str(tmp_path / "sched.db")
    daemon = ProbeSchedulerDaemon(storage_repo=StorageRepository(db_path=db_path))
    daemon.register_domain("https://example.com")

    cycle = daemon.execute_probe_cycle(max_prompts_per_domain=1, dry_run=False)

    stored = daemon.storage.get_probe_history("https://example.com")
    assert len(stored) == len(daemon.prober.providers), (
        f"expected one stored run per provider, got {len(stored)}"
    )
    assert cycle["domain_results"]["https://example.com"]["total_probes"] == len(stored)
