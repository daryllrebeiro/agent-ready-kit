"""Unit tests for automated remediation FixerEngine."""

import os
from packages.core.fixer.engine import FixerEngine


def test_fixer_engine_generation(tmp_path):
    fixer = FixerEngine()
    fixes = fixer.generate_all_fixes("https://mysite.com", site_name="MySite", site_description="AI platform")

    assert "llms.txt" in fixes
    assert "llms-full.txt" in fixes
    assert "robots.txt" in fixes
    assert "schema-ld.json" in fixes

    assert "# MySite" in fixes["llms.txt"]
    assert "GPTBot" in fixes["robots.txt"]
    assert "ClaudeBot" in fixes["robots.txt"]
    assert "https://schema.org" in fixes["schema-ld.json"]

    out_dir = str(tmp_path / "fixes")
    written = fixer.apply_fixes_to_directory(fixes, out_dir)

    for fname in ["llms.txt", "robots.txt", "schema-ld.json"]:
        assert os.path.exists(written[fname])
