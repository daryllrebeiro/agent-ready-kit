"""Unit tests for multilingual /llms.txt generator."""

import tempfile
from packages.core.generator_i18n import MultilingualLLMsGenerator


def test_multilingual_llms_generator_bundle():
    gen = MultilingualLLMsGenerator()
    bundle = gen.generate_multilingual_bundle(
        site_name="Acme AI",
        root_url="https://acme.ai",
        languages=["en", "es", "ja", "de"],
    )

    assert "llms.txt" in bundle
    assert "es/llms.txt" in bundle
    assert "ja/llms.txt" in bundle
    assert "de/llms.txt" in bundle

    assert "Acme AI" in bundle["llms.txt"]
    assert "Documentación" in bundle["es/llms.txt"]
    assert "ドキュメント" in bundle["ja/llms.txt"]

    with tempfile.TemporaryDirectory() as tmpdir:
        written = gen.write_bundle_to_disk(bundle, tmpdir)
        assert len(written) == 5  # root llms.txt + 4 localized languages
