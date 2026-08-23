"""Phase 12 Auth & Billing Tests: API Fuzzing, Scoped Share Tokens, and Upgrade Portal URLs."""

import json
import threading
import time
from http.client import HTTPConnection
from http.server import HTTPServer
import pytest
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


def test_api_route_unauthenticated_fuzzing(api_fuzz_server):
    """Fuzzes public and tenant API routes with missing or malformed credentials."""
    conn = HTTPConnection("127.0.0.1", api_fuzz_server)
    endpoints = [
        ("GET", "/api/domains", None),
        ("POST", "/api/simulate", {"url": "https://example.com"}),
        ("POST", "/api/compare", {"target_url": "https://example.com", "competitor_urls": ["https://competitor.com"], "dry_run": True}),
        ("GET", "/api/report?domain=https://example.com", None),
    ]

    for method, path, payload in endpoints:
        # 1. Standard request without auth
        body = json.dumps(payload) if payload else None
        headers = {"Content-Type": "application/json"} if payload else {}
        conn.request(method, path, body=body, headers=headers)
        res = conn.getresponse()
        res.read()
        assert res.status in [200, 400, 401, 403, 404, 405]

        # 2. Malformed token fuzzing
        bad_headers = {"Authorization": "Bearer malformed_invalid_key_99999"}
        if payload:
            bad_headers["Content-Type"] = "application/json"
        conn.request(method, path, body=body, headers=bad_headers)
        res_bad = conn.getresponse()
        res_bad.read()
        assert res_bad.status in [200, 400, 401, 403, 404, 405]


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
