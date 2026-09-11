"""Phase 17 1.4: entrypoint-level smoke tests.

These boot real entrypoints (web server, CLI, worker) against a local
fixture HTTP server. They exist because unit tests of isolated functions
hid an AttributeError-on-every-call (save_probe), a NameError-on-request
(/api/badge Score import), and a dead scheduler persistence loop — none of
which any function-level test exercised.
"""

import json
import threading
import time
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

FIXTURE_ROBOTS = "User-agent: GPTBot\nDisallow:\n\nUser-agent: *\nDisallow: /private/\n"
FIXTURE_HTML = (
    "<html><head><title>Smoke Fixture</title>"
    '<meta name="description" content="smoke fixture">'
    '<script type="application/ld+json">{"@context":"https://schema.org",'
    '"@type":"WebSite","name":"Smoke"}</script></head>'
    "<body><h1>Smoke</h1><main><p>" + "word " * 200 + "</p></main></body></html>"
)
FIXTURE_LLMS = "# Smoke\n> Fixture llms.txt.\n\n## Docs\n\n- [Home](/)\n"


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/robots.txt":
            body, ctype = FIXTURE_ROBOTS.encode(), "text/plain"
        elif self.path in ("/llms.txt", "/llms-full.txt"):
            body, ctype = FIXTURE_LLMS.encode(), "text/markdown"
        else:
            body, ctype = FIXTURE_HTML.encode(), "text/html"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module", autouse=True)
def allow_loopback_fixture(monkeypatch=None):
    """Opt into the documented SSRF escape hatch for fixture traffic only."""
    import os

    os.environ["AGENTREADY_ALLOW_PRIVATE_HOSTS"] = "127.0.0.1,localhost"
    yield
    os.environ.pop("AGENTREADY_ALLOW_PRIVATE_HOSTS", None)


@pytest.fixture(scope="module")
def fixture_site():
    server = HTTPServer(("127.0.0.1", 0), FixtureHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


@pytest.fixture()
def dashboard_server(tmp_path, monkeypatch):
    import apps.web.server as web_server
    from apps.web.server import DashboardAPIHandler

    monkeypatch.setenv("AGENTREADY_DB_PATH", str(tmp_path / "smoke.db"))
    server = HTTPServer(("127.0.0.1", 0), DashboardAPIHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    key = web_server.AUTH_MANAGER.generate_api_key(tenant_id="smoke_tenant")
    yield port, key
    server.shutdown()
    server.server_close()


class TestWebEntrypointSmoke:
    def test_badge_and_scan_against_fixture(self, fixture_site, dashboard_server):
        # Would have caught the /api/badge Score NameError: badge renders
        # without ?domain= crashing the connection.
        port, key = dashboard_server
        conn = HTTPConnection("127.0.0.1", port)

        conn.request("GET", "/api/badge")
        res = conn.getresponse()
        assert res.status == 400, res.status
        payload = json.loads(res.read().decode())
        assert "error" in payload

        conn.request(
            "POST",
            "/api/scan",
            body=json.dumps({"url": fixture_site}),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        )
        res = conn.getresponse()
        payload = json.loads(res.read().decode())
        assert res.status == 200, payload
        assert payload["overall_score"] > 0
        assert len(payload["components"]) == 4


class TestCLIEntrypointSmoke:
    def test_cli_scan_against_fixture(self, fixture_site, tmp_path, monkeypatch, capsys):
        from packages.cli.main import cli_entrypoint

        monkeypatch.setenv("AGENTREADY_DB_PATH", str(tmp_path / "cli_smoke.db"))
        ret = cli_entrypoint(["scan", fixture_site, "--json"])
        assert ret == 0
        out = capsys.readouterr().out
        payload = json.loads(out)
        assert payload["overall_score"] > 0

    def test_cli_scan_refuses_unsafe_target(self, capsys):
        from packages.cli.main import cli_entrypoint

        ret = cli_entrypoint(["scan", "http://169.254.169.254/"])
        assert ret == 2


class TestWorkerEntrypointSmoke:
    def test_worker_cycle_against_fixture(self, fixture_site, tmp_path, monkeypatch):

        from apps.worker.runner import run_worker_cycle
        from packages.core.storage.repository import StorageRepository

        for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "PERPLEXITY_API_KEY"):
            monkeypatch.delenv(var, raising=False)

        db_path = str(tmp_path / "worker_smoke.db")
        repo = StorageRepository(db_path=db_path)
        run_worker_cycle([fixture_site], dry_run=True, max_prompts=1, repo=repo)

        score = repo.get_latest_score(fixture_site)
        assert score is not None and score.overall_score > 0
        probes = repo.get_probe_history(fixture_site)
        # dry-run probes still persist through the worker path.
        assert len(probes) == len(
            __import__("packages.core.probes.runner", fromlist=["MultiModelProber"])
            .MultiModelProber()
            .providers
        )
