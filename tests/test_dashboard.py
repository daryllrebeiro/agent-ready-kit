"""Unit tests for dashboard HTTP server API endpoints (Phase 16: auth-gated)."""

import json
import threading
import time
from http.client import HTTPConnection
from http.server import HTTPServer

import pytest

import apps.web.server as web_server
from apps.web.server import DashboardAPIHandler


@pytest.fixture(scope="module")
def test_server():
    # Start test server on random available port
    server = HTTPServer(("127.0.0.1", 0), DashboardAPIHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    yield port
    server.shutdown()
    server.server_close()


def test_dashboard_api_domains_requires_auth(test_server):
    """Phase 16 Task 1: /api/domains requires authentication."""
    conn = HTTPConnection("127.0.0.1", test_server)
    conn.request("GET", "/api/domains")
    resp = conn.getresponse()
    assert resp.status == 401, f"expected 401 for unauthenticated request, got {resp.status}"


def test_dashboard_api_domains_authenticated(test_server):
    """Authenticated request to /api/domains succeeds."""
    # Use the server's AuthManager to mint a key
    api_key = web_server.AUTH_MANAGER.generate_api_key(tenant_id="test_dashboard_tenant")
    conn = HTTPConnection("127.0.0.1", test_server)
    conn.request("GET", "/api/domains", headers={"Authorization": f"Bearer {api_key}"})
    resp = conn.getresponse()
    assert resp.status == 200
    data = json.loads(resp.read().decode("utf-8"))
    assert isinstance(data, list)


def test_dashboard_api_static_html(test_server):
    """Static HTML files remain public (no auth required)."""
    conn = HTTPConnection("127.0.0.1", test_server)
    conn.request("GET", "/index.html")
    resp = conn.getresponse()
    assert resp.status == 200
    html = resp.read().decode("utf-8")
    assert "AgentReady" in html
    assert "signalsGrid" in html
