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

        # Observation wrapper only: counts + delegates. If enforcement works,
        # the count stays 0 because the handler returns before probing.
        calls = {"n": 0}
        from packages.core.probes.runner import MultiModelProber

        orig = MultiModelProber.run_standard_probe_suite

        def counting(self, *args, **kwargs):
            calls["n"] += 1
            return orig(self, *args, **kwargs)

        monkeypatch.setattr(MultiModelProber, "run_standard_probe_suite", counting)

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
        from packages.core.probes.runner import MultiModelProber

        def fake_suite(self, *args, **kwargs):
            calls["n"] += 1
            return []

        # NOTE: the suite itself is stubbed here ONLY to avoid real upstream
        # LLM spend in CI; the budget gate under test runs unmocked before it.
        monkeypatch.setattr(MultiModelProber, "run_standard_probe_suite", fake_suite)

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
        assert calls["n"] == 1
    finally:
        server.shutdown()
        server.server_close()
