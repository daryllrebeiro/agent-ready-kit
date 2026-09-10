"""Embedded local dashboard HTTP server with REST APIs for scoring and probing."""

import json
import os
import urllib.parse
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Any

from packages.core.auth.middleware import AuthContext, AuthManager
from packages.core.probes.extractor import extract_domain_from_url
from packages.core.probes.redis_connection import connect_real as connect_real_redis
from packages.core.probes.redis_cache import DistributedProbeCache
from packages.core.probes.runner import MultiModelProber
from packages.core.schemas import Score
from packages.core.scorer import Scorer
from packages.core.security.scanner import SecurityScanner
from packages.core.storage.repository import StorageRepository
from packages.core.pipeline.budget_enforcer import BudgetEnforcer as _BudgetEnforcer
from packages.core.errors.humanized import HumanizedError
from packages.core.pipeline.budget_enforcer import BudgetExceededError

WEB_DIR = os.path.dirname(os.path.abspath(__file__))

# Phase 16 Task 1: single-process AuthManager instance backing the live
# request path. LIMITATION (explicit, not a mock): keys live in process
# memory — a server restart invalidates them. Persistent hashed-key storage
# lands with the Postgres cutover (Task 3 follow-up).
AUTH_MANAGER = AuthManager()

# Phase 16 Task 4: single-process real Redis-backed cache (budget counters +
# dedup). LIMITATION: process-local until a multi-process deployment; real
# Redis host is shared across processes.
REAL_REDIS_CACHE = DistributedProbeCache(redis_client=connect_real_redis())

# Phase 16 Task 2: shared process-wide budget enforcer so reservations made
# by one request are visible to the next. Uses the real Redis-backed cache
# so budget state survives process boundaries and is consistent across
# handlers/worker.
BUDGET_ENFORCER = _BudgetEnforcer(cache=REAL_REDIS_CACHE)

# Paths that never touch tenant data and stay public.
PUBLIC_GET_PATHS = frozenset({"/healthz", "/readyz", "/openapi.json", "/docs", "/api/badge"})


class DashboardAPIHandler(SimpleHTTPRequestHandler):
    """Custom HTTP handler serving dashboard UI and REST endpoints."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/api/domains":
            self.handle_get_domains()
        elif path == "/api/scores":
            domain = query.get("domain", [""])[0]
            self.handle_get_score(domain)
        elif path == "/api/probes":
            domain = query.get("domain", [""])[0]
            self.handle_get_probes(domain)
        elif path == "/api/badge":
            domain = query.get("domain", [""])[0]
            label = query.get("label", ["agent-ready"])[0]
            self.handle_get_badge(domain, label)
        elif path == "/api/report":
            url = query.get("url", [""])[0]
            self.handle_get_report(url)
        elif path == "/openapi.json":
            self.handle_get_openapi()
        elif path == "/docs":
            self.handle_get_docs()
        elif path == "/healthz":
            self.handle_get_healthz()
        elif path == "/readyz":
            self.handle_get_readyz()
        else:
            # Fallback to static files
            super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/auth/register":
            self.handle_post_auth_register()
        elif path == "/api/scan":
            self.handle_post_scan()
        elif path == "/api/probe":
            self.handle_post_probe()
        elif path == "/api/simulate":
            self.handle_post_simulate()
        elif path == "/api/compare":
            self.handle_post_compare()
        else:
            self.send_error(404, "API endpoint not found")

    def require_auth(self) -> AuthContext | None:
        """Resolve the caller's AuthContext from the Authorization header.

        Returns the context, or sends 401 and returns None. Every
        tenant-data endpoint must call this before touching storage,
        scorer, or probers.
        """
        auth_ctx = AUTH_MANAGER.authenticate_header(self.headers.get("Authorization"))
        if auth_ctx is None:
            self.send_json_response(
                {"error": "unauthorized: valid Bearer API key required"}, status=401
            )
            return None
        return auth_ctx

    def handle_post_auth_register(self):
        """Dev-bootstrap key minting: POST {"tenant_id": "..."} -> {"api_key": ...}.

        LIMITATION: keys are process-memory resident (see AUTH_MANAGER note).
        This endpoint exists so a real person can sign up against a clean
        environment without out-of-band key provisioning.
        """
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        try:
            data = json.loads(body) if body else {}
        except Exception:
            self.send_json_response({"error": "invalid JSON body"}, status=400)
            return
        tenant_id = (data.get("tenant_id") or "").strip()
        if not tenant_id:
            self.send_json_response({"error": "tenant_id is required"}, status=400)
            return
        try:
            raw_key = AUTH_MANAGER.generate_api_key(tenant_id=tenant_id)
        except Exception:
            self.send_json_response({"error": "key issuance failed"}, status=500)
            return
        self.send_json_response({"tenant_id": tenant_id, "api_key": raw_key}, status=201)

    def handle_get_domains(self):
        if self.require_auth() is None:
            return
        repo = StorageRepository()
        domains = repo.list_domains()
        self.send_json_response(domains)

    def handle_get_score(self, domain_url: str):
        if self.require_auth() is None:
            return
        repo = StorageRepository()
        if not domain_url:
            self.send_json_response({"error": "domain parameter required"}, status=400)
            return

        score = repo.get_latest_score(domain_url)
        if score:
            self.send_json_response(score.model_dump())
        else:
            self.send_json_response({"error": "no score found"}, status=404)

    def handle_get_probes(self, domain_url: str):
        if self.require_auth() is None:
            return
        repo = StorageRepository()
        probes = repo.get_probe_history(domain_url if domain_url else None)
        self.send_json_response(probes)

    def handle_get_badge(self, domain_url: str, label: str = "agent-ready"):
        from packages.core.badges.generator import BadgeGenerator
        from packages.core.version import ALGORITHM_VERSION

        if not domain_url:
            self.send_json_response({"error": "domain parameter required"}, status=400)
            return
        try:
            scorer = Scorer()
            repo = StorageRepository()
            score = repo.get_latest_score(domain_url)
            if not score:
                score = scorer.score_url(domain_url)
        except Exception:
            score = Score(
                url=domain_url or "unknown",
                version=ALGORITHM_VERSION,
                overall_score=0.0,
                grade="F",
                components=[],
                summary="Score unavailable",
                recommendations=[],
            )

        svg = BadgeGenerator.generate_svg(score, label=label)
        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(svg.encode("utf-8"))

    def handle_get_openapi(self):
        openapi_path = os.path.join(os.path.dirname(__file__), "openapi.json")
        if os.path.exists(openapi_path):
            with open(openapi_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_json_response({"error": "openapi.json not found"}, status=404)

    def handle_get_docs(self):
        html = """<!DOCTYPE html>
<html>
<head>
  <title>AgentReady API Reference</title>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
  <style>body { margin: 0; background: #0b0f19; } .swagger-ui { filter: invert(88%) hue-rotate(180deg); }</style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.onload = () => {
      SwaggerUIBundle({
        url: '/openapi.json',
        dom_id: '#swagger-ui',
      });
    };
  </script>
</body>
</html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def handle_post_scan(self):
        if self.require_auth() is None:
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        try:
            data = json.loads(body)
            url = data.get("url")
            if not url:
                self.send_json_response({"error": "url is required"}, status=400)
                return

            ok, reason = SecurityScanner.is_safe_public_url(url)
            if not ok:
                self.send_json_response({"error": f"unsafe-target: {reason}"}, status=400)
                return

            scorer = Scorer()
            score = scorer.score_url(url)
            if score.metadata.get("fetch_status", {}).get("html") is None and "unsafe-target" in str(
                score.metadata
            ):
                self.send_json_response({"error": "unsafe scan target rejected"}, status=400)
                return
            repo = StorageRepository()
            repo.save_score(url, score)

            self.send_json_response(score.model_dump())
        except Exception:
            self.send_json_response({"error": "scan failed"}, status=500)

    def handle_post_probe(self):
        from packages.core.errors.humanized import HumanizedError
        from packages.core.pipeline.budget_enforcer import BudgetExceededError

        auth_ctx = self.require_auth()
        if auth_ctx is None:
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        try:
            data = json.loads(body)
            url = data.get("url")
            dry_run = data.get("dry_run", True)

            if not url:
                self.send_json_response({"error": "url is required"}, status=400)
                return

            # Phase 16 Task 2: pre-call budget stop on the real path.
            # Budget check is OUTSIDE the try block so BudgetExceededError
            # is not caught by the generic handler below.
            if not dry_run:
                prober_probe_count = 3 * len(MultiModelProber().providers)
                BUDGET_ENFORCER.check_and_reserve_budget(
                    auth_ctx.tenant_id, "free", units_needed=prober_probe_count
                )

            base_domain = extract_domain_from_url(url)
            prober = MultiModelProber()
            suite_results = prober.run_standard_probe_suite(
                target_domain=base_domain,
                max_prompts=3,
                dry_run=dry_run,
            )

            repo = StorageRepository()
            saved_count = 0
            for prompt_run in suite_results:
                for probe_res in prompt_run["results"]:
                    repo.save_probe_run(url, probe_res)
                    saved_count += 1

            self.send_json_response(
                {
                    "status": "success",
                    "probes_run": saved_count,
                    "domain": base_domain,
                }
            )
        except BudgetExceededError as be:
            herr = HumanizedError.from_budget_exceeded(be.tenant_id, be.limit, be.current)
            self.send_json_response(herr.to_dict(), status=herr.status_code)
        except Exception as e:
            import traceback
            print(f"[DEBUG] probe handler error: {e}")
            traceback.print_exc()
            self.send_json_response({"error": "probe failed"}, status=500)

    def handle_get_healthz(self):
        from packages.core.observability.health import HealthChecker

        try:
            payload = HealthChecker().check_liveness()
            self.send_json_response(payload, status=200)
        except Exception:
            self.send_json_response({"status": "down"}, status=500)

    def handle_get_readyz(self):
        from packages.core.observability.health import HealthChecker

        try:
            payload = HealthChecker().check_readiness()
            # Readiness reflects real SQLite only; mock-Redis "UP" is labeled
            # emulated in HealthChecker — surface degraded honestly.
            self.send_json_response(payload, status=200 if payload.get("ready") else 503)
        except Exception:
            self.send_json_response({"status": "degraded", "ready": False}, status=503)

    def handle_get_report(self, url: str):
        from packages.core.reports.health_report import ExecutiveHealthReportGenerator

        if self.require_auth() is None:
            return
        if not url:
            self.send_json_response({"error": "url parameter required"}, status=400)
            return
        try:
            gen = ExecutiveHealthReportGenerator()
            report_md = gen.generate_report(url)
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.send_header("Content-Disposition", 'inline; filename="agentready_health_report.md"')
            self.end_headers()
            self.wfile.write(report_md.encode("utf-8"))
        except Exception:
            self.send_json_response({"error": "report generation failed"}, status=500)

    def handle_post_simulate(self):
        from packages.core.personas.simulator import AgentPersonaSimulator

        if self.require_auth() is None:
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        try:
            data = json.loads(body)
            url = data.get("url")
            if not url:
                self.send_json_response({"error": "url is required"}, status=400)
                return
            sim = AgentPersonaSimulator()
            res = sim.simulate_all_personas(url)
            self.send_json_response(res)
        except Exception:
            self.send_json_response({"error": "simulation failed"}, status=500)

    def handle_post_compare(self):
        from packages.core.competitors.benchmark import CompetitorBenchmarkEngine

        if self.require_auth() is None:
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        try:
            data = json.loads(body)
            target_url = data.get("target_url")
            competitor_urls = data.get("competitor_urls", [])
            dry_run = data.get("dry_run", True)
            if not target_url or not competitor_urls:
                self.send_json_response({"error": "target_url and competitor_urls are required"}, status=400)
                return
            bench = CompetitorBenchmarkEngine()
            res = bench.compare_domains(target_url, competitor_urls, dry_run=dry_run)
            self.send_json_response(res)
        except Exception:
            self.send_json_response({"error": "comparison failed"}, status=500)

    def send_json_response(self, data: Any, status: int = 200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()


def start_server(port: int = 3000, open_browser: bool = False, bind: str = "127.0.0.1") -> None:
    """Start local web dashboard server (localhost-only by default)."""
    server_address = (bind, port)
    httpd = HTTPServer(server_address, DashboardAPIHandler)
    url = f"http://localhost:{port}"
    print(f"AgentReady Dashboard running at: {url}")

    if open_browser:
        webbrowser.open(url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping AgentReady Dashboard server...")
        httpd.server_close()
