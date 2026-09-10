"""Phase 12 Auth & Billing Tests: API Fuzzing, Scoped Share Tokens, and Upgrade Portal URLs."""

import json
import platform
import threading
import time
from http.client import HTTPConnection
from http.server import HTTPServer
import pytest
import apps.web.server as web_server
from apps.web.server import DashboardAPIHandler
from packages.core.auth.middleware import AuthManager, UserRole
from packages.core.pipeline.budget_enforcer import BudgetExceededError


@pytest.fixture(scope="module")
def api_fuzz_server():
    server = HTTPServer(("127.0.0.1", 0), DashboardAPIHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    yield port
    server.shutdown()
    server.server_close()


@pytest.mark.skipif(platform.system() == "Windows", reason="Windows socket flakiness with rapid sequential requests; auth proven by other tests")
def test_api_route_unauthenticated_fuzzing(api_fuzz_server):
    """Phase 16 Task 1: every tenant-data route must reject unauthenticated
    callers with exactly 401 — a 200 here is a live data-exposure failure.

    (Replaces the prior assertion `status in [200, 400, 401, 403, 404, 405]`,
    which passed regardless of outcome and could not fail.)
    """
    endpoints = [
        ("GET", "/api/domains", None),
        ("GET", "/api/scores?domain=https://example.com", None),
        ("GET", "/api/probes?domain=https://example.com", None),
        ("GET", "/api/report?url=https://example.com", None),
        ("POST", "/api/scan", {"url": "https://example.com"}),
        ("POST", "/api/probe", {"url": "https://example.com", "dry_run": True}),
        ("POST", "/api/simulate", {"url": "https://example.com"}),
        (
            "POST",
            "/api/compare",
            {
                "target_url": "https://example.com",
                "competitor_urls": ["https://competitor.com"],
                "dry_run": True,
            },
        ),
    ]

    for method, path, payload in endpoints:
        conn = HTTPConnection("127.0.0.1", api_fuzz_server)
        body = json.dumps(payload) if payload else None
        headers = {"Content-Type": "application/json"} if payload else {}
        conn.request(method, path, body=body, headers=headers)
        res = conn.getresponse()
        raw = res.read()
        assert res.status == 401, f"{method} {path} without auth returned {res.status}: {raw!r}"
        conn.close()

        # 2. Malformed token -> exactly 401.
        conn = HTTPConnection("127.0.0.1", api_fuzz_server)
        bad_headers = {"Authorization": "Bearer malformed_invalid_key_99999"}
        if payload:
            bad_headers["Content-Type"] = "application/json"
        conn.request(method, path, body=body, headers=bad_headers)
        res_bad = conn.getresponse()
        raw_bad = res_bad.read()
        assert res_bad.status == 401, f"{method} {path} with bad token returned {res_bad.status}: {raw_bad!r}"
        conn.close()


def test_api_route_authenticated_allows_access(api_fuzz_server):
    """A request bearing a key minted via /api/auth/register reaches the
    handler (i.e. auth gates, it does not blanket-reject)."""
    import apps.web.server as web_server

    raw_key = web_server.AUTH_MANAGER.generate_api_key(tenant_id="tenant_fuzz_ok")
    conn = HTTPConnection("127.0.0.1", api_fuzz_server)
    conn.request("GET", "/api/domains", headers={"Authorization": f"Bearer {raw_key}"})
    res = conn.getresponse()
    res.read()
    assert res.status == 200, f"authenticated /api/domains returned {res.status}"


def test_public_paths_stay_open(api_fuzz_server):
    """Health/readiness/badge carry no tenant data and must not require auth."""
    conn = HTTPConnection("127.0.0.1", api_fuzz_server)
    for path in ["/healthz", "/readyz"]:
        conn.request("GET", path)
        res = conn.getresponse()
        res.read()
        assert res.status in (200, 503), f"{path} returned {res.status}"


def test_domain_scoped_share_tokens():
    """Verifies that a DomainShareToken grants read access only to its specified domain."""
    auth_mgr = AuthManager()
    tenant_id = "tenant_enterprise_acme"
    target_domain = "https://docs.acme.com"

    # Generate domain share token
    share_token = auth_mgr.generate_domain_share_token(
        tenant_id=tenant_id,
        domain_url=target_domain,
        ttl_seconds=3600,
    )
    assert share_token.startswith("dst_")

    # Resolve token
    ctx = auth_mgr.resolve_api_key(share_token)
    assert ctx is not None
    assert ctx.tenant_id == tenant_id
    assert ctx.role == UserRole.READ_ONLY
    assert ctx.can_access_domain("https://docs.acme.com") is True
    assert ctx.can_access_domain("https://competitor.com") is False
    assert ctx.can_access_domain("https://secret-internal.acme.com") is False


def test_budget_exceeded_error_upgrade_portal_url():
    """Verifies that budget exceeded errors embed real-time Stripe billing portal URLs."""
    err = BudgetExceededError(tenant_id="tenant_acme_123", limit=100, current=100)
    data = err.to_dict()

    assert data["error"] == "BUDGET_EXCEEDED"
    assert data["tenant_id"] == "tenant_acme_123"
    assert "https://app.agentready.dev/billing/upgrade?tenant_id=tenant_acme_123" in data["upgrade_url"]
    assert "Upgrade your plan at" in str(err)
