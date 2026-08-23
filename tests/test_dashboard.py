"""Unit tests for dashboard HTTP server API endpoints."""

import json
import threading
import time
from http.client import HTTPConnection
from http.server import HTTPServer
import pytest
from apps.web.server import DashboardAPIHandler
from packages.core.storage.db import init_db
from packages.core.storage.repository import StorageRepository


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


def test_dashboard_api_domains(test_server):
    conn = HTTPConnection("127.0.0.1", test_server)
    conn.request("GET", "/api/domains")
    resp = conn.getresponse()
    assert resp.status == 200
    data = json.loads(resp.read().decode("utf-8"))
    assert isinstance(data, list)


def test_dashboard_api_static_html(test_server):
    conn = HTTPConnection("127.0.0.1", test_server)
    conn.request("GET", "/index.html")
    resp = conn.getresponse()
    assert resp.status == 200
    html = resp.read().decode("utf-8")
    assert "AgentReady" in html
    assert "signalsGrid" in html
