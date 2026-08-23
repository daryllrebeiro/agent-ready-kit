"""Unit tests for CLI agentready report command."""

import os
import tempfile
from packages.cli.main import cli_entrypoint


def test_cli_report_command_with_output_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_file = os.path.join(tmpdir, "report.md")
        ret = cli_entrypoint(["report", "https://example.com", "--output", out_file])
        assert ret == 0
        assert os.path.exists(out_file)
        with open(out_file, "r", encoding="utf-8") as f:
            content = f.read()
            assert "Executive AI Agent Health Report" in content
