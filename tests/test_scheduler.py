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

    velocity = daemon.calculate_citation_velocity("example.com", current_rate_pct=75.0, previous_rate_pct=50.0)
    assert velocity["velocity_delta"] == 25.0
    assert velocity["trend"] == "INCREASING"
