"""Unit tests for citation extractor, provider wrappers, and multi-model probing."""

from packages.core.probes.extractor import extract_citations, extract_domain_from_url
from packages.core.probes.providers import AnthropicProbe, GeminiProbe, OpenAIProbe, PerplexityProbe
from packages.core.probes.runner import MultiModelProber


def test_extract_domain_from_url():
    assert extract_domain_from_url("https://www.agentready.dev/docs/quickstart") == "agentready.dev"
    assert extract_domain_from_url("http://example.com:8080/page") == "example.com"
    assert extract_domain_from_url("llmstxt.org") == "llmstxt.org"


def test_extract_citations_comprehensive():
    sample_text = """
    Check out the tool at https://agentready.dev/score and docs at [LLMs Spec](https://llmstxt.org).
    According to source: github.com/modelcontextprotocol, MCP is great.
    Also read stripe.com/docs for payments.
    """
    res = extract_citations(sample_text)

    assert "https://agentready.dev/score" in res["urls"]
    assert "https://llmstxt.org" in res["urls"]
    assert "agentready.dev" in res["domains"]
    assert "llmstxt.org" in res["domains"]
    assert "stripe.com" in res["domains"]


def test_provider_probes_dry_run():
    providers = [OpenAIProbe(), AnthropicProbe(), GeminiProbe(), PerplexityProbe()]
    for p in providers:
        res = p.probe("What are the best agent ready platforms?", dry_run=True)
        assert res.provider == p.provider_name
        assert len(res.raw_response) > 0
        assert res.latency_ms is not None
        assert isinstance(res.cited_domains, list)


def test_multimodel_prober_suite():
    prober = MultiModelProber()
    suite = prober.run_standard_probe_suite(target_domain="agentready.dev", max_prompts=2, dry_run=True)

    assert len(suite) == 2
    for run in suite:
        assert "prompt" in run
        assert len(run["results"]) == 4  # 4 providers
        assert isinstance(run["cited_providers"], list)
