"""Unit tests for Web Dashboard v2.0 API endpoints (/api/simulate, /api/compare, /api/report)."""

import json
import threading
import time
from http.client import HTTPConnection
from http.server import HTTPServer
import pytest
from apps.web.server import DashboardAPIHandler


@pytest.fixture(scope="module")
def web_v2_server():
    server = HTTPServer(("127.0.0.1", 0), DashboardAPIHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    yield port
    server.shutdown()
    server.server_close()


def test_api_simulate_endpoint(web_v2_server):
    conn = HTTPConnection("127.0.0.1", web_v2_server)
    payload = json.dumps({"url": "https://example.com"})
    conn.request("POST", "/api/simulate", body=payload, headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    assert resp.status == 200
    data = json.loads(resp.read().decode("utf-8"))
    assert "overall_compatibility" in data
    assert "personas" in data


def test_api_compare_endpoint(web_v2_server):
    conn = HTTPConnection("127.0.0.1", web_v2_server)
    payload = json.dumps({
        "target_url": "https://example.com",
        "competitor_urls": ["https://competitor.com"],
        "dry_run": True,
    })
    conn.request("POST", "/api/compare", body=payload, headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    assert resp.status == 200
    data = json.loads(resp.read().decode("utf-8"))
    assert "target_domain" in data
    assert "win_status" in data
    assert "readiness_ranking" in data


def test_api_report_endpoint(web_v2_server):
    conn = HTTPConnection("127.0.0.1", web_v2_server)
    conn.request("GET", "/api/report?url=https://example.com")
    resp = conn.getresponse()
    assert resp.status == 200
    assert "text/markdown" in resp.headers.get("Content-Type", "")
    content = resp.read().decode("utf-8")
    assert "Executive AI Agent Health Report" in content
