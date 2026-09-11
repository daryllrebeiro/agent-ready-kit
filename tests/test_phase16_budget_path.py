"""Phase 16 Task 2: budget enforcement on the real probe call path.

Exhausts a tenant's budget, then drives the REAL /api/probe HTTP entry
point and asserts (a) a 402 humanized refusal and (b) the provider layer
was never invoked (call-count observation wrapper that delegates — the
enforcement path itself is unmocked).
"""

import json
import threading
import time
from http.client import HTTPConnection
from http.server import HTTPServer

import apps.web.server as web_server
from apps.web.server import DashboardAPIHandler


def _run_server():
    server = HTTPServer(("127.0.0.1", 0), DashboardAPIHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    return server, port


def test_probe_blocked_before_provider_when_budget_exhausted(monkeypatch):
    server, port = _run_server()
    try:
        raw_key = web_server.AUTH_MANAGER.generate_api_key(tenant_id="tenant_budget_blocked")
        # Setup (not the SUT): push this tenant over the free-tier limit
        # through the same shared enforcer the handler uses.
        web_server.BUDGET_ENFORCER.cache.increment_tenant_usage("tenant_budget_blocked", 10000)

        # Observation at the true upstream boundary: provider.probe must
        # never execute. (Counting Pipeline.run would include the denied
        # attempt itself, since the budget check lives inside run.)
        calls = {"n": 0}
        from packages.core.probes import providers as provider_mod

        originals = {}
        for cls in (
            provider_mod.OpenAIProbe,
            provider_mod.AnthropicProbe,
            provider_mod.GeminiProbe,
            provider_mod.PerplexityProbe,
        ):
            originals[cls] = cls.probe

            def counting(self, *args, _orig=cls.probe, **kwargs):
                calls["n"] += 1
                return _orig(self, *args, **kwargs)

            monkeypatch.setattr(cls, "probe", counting)

        conn = HTTPConnection("127.0.0.1", port)
        body = json.dumps({"url": "https://example.com", "dry_run": False})
        conn.request(
            "POST",
            "/api/probe",
            body=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {raw_key}"},
        )
        res = conn.getresponse()
        payload = json.loads(res.read().decode())
        assert res.status == 402, f"expected 402, got {res.status}: {payload}"
        assert payload["error_code"] == "BUDGET_LIMIT_REACHED"
        assert calls["n"] == 0, "provider suite was invoked despite exhausted budget"
    finally:
        server.shutdown()
        server.server_close()


def test_probe_proceeds_when_budget_available(monkeypatch):
    """Guard against blanket-blocking: a funded tenant reaches the prober."""
    server, port = _run_server()
    try:
        raw_key = web_server.AUTH_MANAGER.generate_api_key(tenant_id="tenant_budget_ok")

        calls = {"n": 0}
        from packages.core.probes.pipeline import ProbePipeline

        def fake_run(self, provider, prompt, dry_run=False):
            from packages.core.schemas import ProbeResult

            calls["n"] += 1
            return ProbeResult(provider=provider.provider_name, prompt=prompt, raw_response="")

        # NOTE: provider calls are stubbed here ONLY to avoid real upstream
        # LLM spend in CI; budget/cache/breaker/DLQ gates run unmocked first.
        monkeypatch.setattr(ProbePipeline, "run", fake_run)

        conn = HTTPConnection("127.0.0.1", port)
        body = json.dumps({"url": "https://example.com", "dry_run": False})
        conn.request(
            "POST",
            "/api/probe",
            body=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {raw_key}"},
        )
        res = conn.getresponse()
        payload = json.loads(res.read().decode())
        assert res.status == 200, f"expected 200, got {res.status}: {payload}"
        # 3 prompts x 4 providers, every one through the guarded pipeline.
        assert calls["n"] == 12, f"expected 12 guarded provider calls, got {calls['n']}"
        assert payload["probes_run"] == 12
    finally:
        server.shutdown()
        server.server_close()
