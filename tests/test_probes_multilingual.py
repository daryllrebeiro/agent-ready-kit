"""Unit tests for cross-lingual citation probing."""

from packages.core.probes.multilingual import MultilingualProber


def test_multilingual_prober_dry_run():
    prober = MultilingualProber()
    res = prober.probe_language(target_domain="acme.ai", lang="es", dry_run=True)

    assert res["target_domain"] == "acme.ai"
    assert res["language"] == "es"
    assert res["prompts_tested"] >= 2
    assert len(res["results"]) >= 8  # 2 prompts * 4 providers
