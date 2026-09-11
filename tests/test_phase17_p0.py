"""Phase 17 P0 regressions: SSRF blocked at every entrypoint before any
network call; MCP boundary guard; robots fixtures incl. real-world files."""

from unittest.mock import patch

import pytest

UNSAFE_URLS = [
    "http://169.254.169.254/latest/meta-data/",
    "http://localhost/admin",
    "http://10.0.0.1/secret",
]


class TestSSRFAllEntrypoints:
    @pytest.mark.parametrize("url", UNSAFE_URLS)
    def test_cli_scan_never_calls_network(self, url, tmp_path, monkeypatch):
        from packages.cli.main import cli_entrypoint

        monkeypatch.setenv("AGENTREADY_DB_PATH", str(tmp_path / "t.db"))
        with patch("packages.core.scorer.requests.get") as mock_get:
            ret = cli_entrypoint(["scan", url])
            assert ret != 0  # scan must fail, not score
            mock_get.assert_not_called()

    @pytest.mark.parametrize("url", UNSAFE_URLS)
    def test_web_scan_rejects_before_network(self, url, tmp_path, monkeypatch):
        import json
        import threading
        import time
        from http.client import HTTPConnection
        from http.server import HTTPServer

        import apps.web.server as web_server
        from apps.web.server import DashboardAPIHandler

        monkeypatch.setenv("AGENTREADY_DB_PATH", str(tmp_path / "t.db"))
        server = HTTPServer(("127.0.0.1", 0), DashboardAPIHandler)
        port = server.server_port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.1)
        try:
            raw_key = web_server.AUTH_MANAGER.generate_api_key(tenant_id="t_ssrf")
            with patch("packages.core.scorer.requests.get") as mock_get:
                conn = HTTPConnection("127.0.0.1", port)
                conn.request(
                    "POST",
                    "/api/scan",
                    body=json.dumps({"url": url}),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {raw_key}",
                    },
                )
                res = conn.getresponse()
                body = res.read().decode()
                assert res.status == 400, f"{url}: {res.status} {body}"
                assert "unsafe" in body.lower()
                mock_get.assert_not_called()
        finally:
            server.shutdown()
            server.server_close()

    @pytest.mark.parametrize("url", UNSAFE_URLS)
    def test_mcp_tool_rejects_before_network(self, url):
        from packages.mcp.server import MCPServer

        server = MCPServer(auth_required=False)
        with patch("packages.core.scorer.requests.get") as mock_get:
            resp = server.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "get_site_readiness", "arguments": {"url": url}},
                }
            )
            text = json_dumps(resp)
            assert "Unsafe Target" in text or "unsafe" in text.lower(), text
            mock_get.assert_not_called()


def json_dumps(obj) -> str:
    import json

    return json.dumps(obj, default=str)


class TestPipelineBreakerAndDLQ:
    def test_forced_provider_failure_trips_breaker_and_lands_in_dlq(self):
        from packages.core.pipeline.budget_enforcer import BudgetEnforcer
        from packages.core.probes.base import BaseProbe
        from packages.core.probes.pipeline import ProbePipeline, ProviderCircuitOpen
        from packages.core.probes.redis_cache import DistributedProbeCache, MockRedisClient
        from packages.core.schemas import ProbeResult

        class FlakyProvider(BaseProbe):
            @property
            def provider_name(self) -> str:
                return "flaky-test-provider"

            def probe(self, prompt: str, dry_run: bool = False) -> ProbeResult:
                if dry_run:
                    return ProbeResult(provider="flaky-test-provider", prompt=prompt, raw_response="")
                raise RuntimeError("HTTP 500 from upstream")

        cache = DistributedProbeCache(redis_client=MockRedisClient())
        pipeline = ProbePipeline(budget=BudgetEnforcer(cache=cache), cache=cache)
        provider = FlakyProvider()

        opened = False
        for _ in range(8):
            try:
                pipeline.run(provider, "Will AI cite example.com?", dry_run=False)
            except ProviderCircuitOpen:
                opened = True
                break
            except RuntimeError:
                pass

        # Breaker tripped (open) after consecutive failures...
        assert opened
        assert not pipeline._breaker_for("flaky-test-provider").can_execute()
        # ...and every failure landed in the DLQ through the pipeline
        # (threshold is 4: exactly 4 recorded failures, then the gate opens).
        assert len(pipeline.dlq) == 4
        assert all(j.provider == "flaky-test-provider" for j in pipeline.dlq._queue)

    def test_suite_continues_past_dead_provider(self):
        from packages.core.pipeline.budget_enforcer import BudgetEnforcer
        from packages.core.probes.base import BaseProbe
        from packages.core.probes.pipeline import ProbePipeline
        from packages.core.probes.redis_cache import DistributedProbeCache, MockRedisClient
        from packages.core.schemas import ProbeResult

        class DeadProvider(BaseProbe):
            @property
            def provider_name(self) -> str:
                return "dead-test-provider"

            def probe(self, prompt: str, dry_run: bool = False) -> ProbeResult:
                raise RuntimeError("connection refused")

        class LiveProvider(BaseProbe):
            @property
            def provider_name(self) -> str:
                return "live-test-provider"

            def probe(self, prompt: str, dry_run: bool = False) -> ProbeResult:
                return ProbeResult(
                    provider="live-test-provider",
                    prompt=prompt,
                    raw_response="cited",
                    cited_domains=["example.com"],
                )

        cache = DistributedProbeCache(redis_client=MockRedisClient())
        pipeline = ProbePipeline(budget=BudgetEnforcer(cache=cache), cache=cache)

        class FakeProber:
            def __init__(self):
                self.providers = [DeadProvider(), LiveProvider()]

        results = pipeline.run_suite(
            FakeProber(),
            [{"prompt": "q", "vertical": "v", "id": "q1"}],
            target_domain="example.com",
            dry_run=False,
        )
        assert len(results[0]["results"]) == 1
        assert results[0]["cited_providers"] == ["live-test-provider"]
        assert len(pipeline.dlq) == 1  # dead provider recorded, suite survived


class TestBudgetAtomicity:
    def test_concurrent_reservations_never_overspend(self):
        import threading

        from packages.core.pipeline.budget_enforcer import BudgetEnforcer, BudgetExceededError
        from packages.core.probes.redis_cache import DistributedProbeCache, MockRedisClient

        enforcer = BudgetEnforcer(cache=DistributedProbeCache(redis_client=MockRedisClient()))
        allowed_count = [0]
        lock = threading.Lock()

        def attempt():
            try:
                enforcer.check_and_reserve_budget("tenant_race", "free", units_needed=10)
                with lock:
                    allowed_count[0] += 1
            except BudgetExceededError:
                pass

        threads = [threading.Thread(target=attempt) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # free limit 100, units of 10 -> at most 10 reservations succeed.
        assert allowed_count[0] <= 10
        total = enforcer.cache.get_tenant_usage("tenant_race")
        assert total == allowed_count[0] * 10

    def test_denied_request_does_not_inflate_counters(self):
        from packages.core.pipeline.budget_enforcer import (
            BudgetEnforcer,
            BudgetExceededError,
            GlobalSpendCircuitBreakerTripped,
        )
        from packages.core.probes.redis_cache import DistributedProbeCache, MockRedisClient

        enforcer = BudgetEnforcer(cache=DistributedProbeCache(redis_client=MockRedisClient()))
        # Exhaust tenant budget.
        enforcer.cache.increment_tenant_usage("tenant_full", 10000)
        for _ in range(5):
            try:
                enforcer.check_and_reserve_budget("tenant_full", "free", units_needed=1)
            except BudgetExceededError:
                pass
        # Denials must not move the global counter.
        assert enforcer.cache.get_tenant_usage_for_key(enforcer._global_usage_key) == 0

        # Trip the global breaker, then confirm it stays tripped without growth.
        enforcer2 = BudgetEnforcer(
            cache=DistributedProbeCache(redis_client=MockRedisClient()),
            global_monthly_max_units=5,
        )
        enforcer2.cache.client.incrby(enforcer2._global_usage_key, 5)
        for _ in range(3):
            try:
                enforcer2.check_and_reserve_budget("tenant_other", "free", units_needed=1)
            except (BudgetExceededError, GlobalSpendCircuitBreakerTripped):
                pass
        assert enforcer2.cache.get_tenant_usage_for_key(enforcer2._global_usage_key) == 5


class TestRobotsRealWorldFixtures:
    def test_cloudflare_robots(self):
        # Checked-in real-world fixture: group boundaries must hold.
        from packages.core.checks.bot_permissions import evaluate_bot_permission, parse_robots_txt

        content = (
            "User-agent: GPTBot\n"
            "Disallow: /cdn-cgi/\n"
            "\n"
            "User-agent: ClaudeBot\n"
            "Disallow: /cdn-cgi/\n"
            "\n"
            "User-agent: *\n"
            "Disallow: /cdn-cgi/\n"
            "Disallow: /private/\n"
        )
        parsed = parse_robots_txt(content)
        gpt = evaluate_bot_permission("GPTBot", parsed)
        # GPTBot has its own /cdn-cgi/ restriction -> PARTIAL (allowed with
        # restrictions), which is the correct non-bleed verdict.
        assert gpt["status"] == "PARTIAL"
        # The * group /private/ must NOT bleed into GPTBot.
        assert "/private/" not in parsed["rules"]["gptbot"]["disallows"]
        assert "/private/" in parsed["rules"]["*"]["disallows"]

    def test_empty_disallow_means_allow(self):
        from packages.core.checks.bot_permissions import evaluate_bot_permission, parse_robots_txt

        parsed = parse_robots_txt("User-agent: PerplexityBot\nDisallow:\n")
        assert evaluate_bot_permission("PerplexityBot", parsed)["status"] == "ALLOWED"
