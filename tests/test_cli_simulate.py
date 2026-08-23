"""Unit tests for CLI agentready simulate command."""

from packages.cli.main import cli_entrypoint


def test_cli_simulate_command():
    ret = cli_entrypoint(["simulate", "https://example.com"])
    assert ret == 0
