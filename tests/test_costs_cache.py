"""Unit tests for probe cost estimation and TTL caching layer."""

import time
from packages.core.pipeline.costs import CostAuditor
from packages.core.probes.cache import ProbeCache
from packages.core.schemas import ProbeResult


def test_cost_auditor():
    cost = CostAuditor.estimate_probe_cost("openai", input_tokens=500, output_tokens=500)
    assert cost > 0.001
    assert cost < 0.05

    margin = CostAuditor.calculate_tenant_margin(tier_monthly_price=99.0, probes_executed=100)
    assert margin["gross_profit"] > 90.0
    assert margin["margin_pct"] > 90.0


def test_probe_cache_hit_and_ttl():
    cache = ProbeCache(default_ttl_seconds=0.1)
    dummy_res = ProbeResult(
        provider="perplexity",
        prompt="sample prompt",
        raw_response="sample response",
        cited_domains=["example.com"],
        extracted_urls=[],
    )

    # Initially cache miss
    assert cache.get("perplexity", "sample prompt") is None

    # Set cache
    cache.set("perplexity", "sample prompt", dummy_res)
    hit = cache.get("perplexity", "sample prompt")
    assert hit is not None
    assert hit.raw_response == "sample response"
    assert cache.hit_rate() > 0.0

    # Wait for TTL expiry
    time.sleep(0.15)
    assert cache.get("perplexity", "sample prompt") is None
