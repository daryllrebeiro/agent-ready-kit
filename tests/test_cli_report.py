"""Unit tests for CLI report command (deferred to Phase 17+).

The `report` command is NOT in the v1 CLI surface (Phase 16 Task 7).
It remains in the codebase but is hidden from the v1 CLI surface.
This test verifies it is correctly excluded from v1.
"""

from packages.cli.main import cli_entrypoint


def test_cli_report_command_not_in_v1_surface():
    """The `report` command is deferred to Phase 17+ and not in v1 CLI."""
    # The v1 parser only accepts: scan, probe, generate, dashboard, auth
    # Passing 'report' should cause argparse to exit with error code 2

    try:
        cli_entrypoint(["report", "https://example.com"])
        assert False, "report command should not be accepted in v1"
    except SystemExit as e:
        assert e.code == 2, f"expected exit code 2, got {e.code}"
