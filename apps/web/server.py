"""Embedded local dashboard HTTP server with REST APIs for scoring and probing."""

import json
import os
import urllib.parse
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Any

from packages.core.auth.middleware import AuthContext, AuthManager
from packages.core.pipeline.budget_enforcer import BudgetEnforcer as _BudgetEnforcer
from packages.core.probes.extractor import extract_domain_from_url
from packages.core.probes.redis_cache import DistributedProbeCache
from packages.core.probes.redis_connection import connect_real as connect_real_redis
from packages.core.probes.runner import MultiModelProber
from packages.core.schemas import Score
from packages.core.scorer import Scorer
from packages.core.storage.repository import StorageRepository

WEB_DIR = os.path.dirname(os.path.abspath(__file__))


# Phase 16 Task 1 (+ follow-up): AuthManager backing the live request path.
# AGENTREADY_STORAGE=postgres -> persistent hashed keys in Postgres
# (survive restarts, revocation/expiry enforced). Default -> in-process
# AuthManager (keys lost on restart; explicit dev limitation, not a mock).
def _build_auth_manager():
    if os.environ.get("AGENTREADY_STORAGE", "sqlite").lower() == "postgres":
        try:
            from packages.core.auth.pg_keys import PgAuthManager
            from packages.core.storage.pg_connection import connect_real

            mgr = PgAuthManager(connect_real())
            print("[auth] persistent Postgres-backed API keys enabled")
            return mgr
        except Exception as e:
            print(
                f"[auth] WARNING: AGENTREADY_STORAGE=postgres but PG unreachable ({e}); "
                "falling back to in-process keys"
            )
    return AuthManager()


AUTH_MANAGER = _build_auth_manager()

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
        elif path == "/api/webhooks/stripe":
            self.handle_post_stripe_webhook()
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
            self.send_json_response({"error": "unauthorized: valid Bearer API key required"}, status=401)
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

    def handle_post_stripe_webhook(self):
        """Phase 16 Task 5 code-side: real Stripe webhook receiver.

        Verifies the Stripe HMAC signature over the RAW body, processes the
        event idempotently through StripeBillingEngine, and persists the
        subscription snapshot to Postgres when AGENTREADY_STORAGE=postgres.
        Live Stripe delivery still requires a test-mode account + CLI;
        this endpoint is the real receiver it will hit (no mocks).
        """
        import logging

        from packages.core.billing.stripe_engine import StripeBillingEngine

        logger = logging.getLogger("agentready.web")
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        signature = self.headers.get("Stripe-Signature", "")

        secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
        if not secret or secret == "whsec_test_secret":
            # Fail fast: never validate traffic against the hardcoded test
            # secret (AR-008). Operators must set STRIPE_WEBHOOK_SECRET.
            self.send_json_response(
                {"error": "webhook not configured", "error_code": "WEBHOOK_UNCONFIGURED"},
                status=503,
            )
            return

        engine = StripeBillingEngine(webhook_secret=secret)
        if not engine.verify_webhook_signature(raw, signature):
            logger.warning("stripe webhook rejected: bad signature")
            self.send_json_response(
                {"error": "invalid signature", "error_code": "WEBHOOK_BAD_SIGNATURE"},
                status=401,
            )
            return

        ok, message = engine.handle_webhook_event(raw, signature)
        if not ok:
            self.send_json_response({"error": "event rejected"}, status=400)
            return

        # Persist subscription snapshot (postgres mode only; SQLite has no
        # subscriptions table by design for local dev).
        try:
            import json as _json

            event = _json.loads(raw)
            data_obj = event.get("data", {}).get("object", {})
            tenant_id = (
                data_obj.get("metadata", {}).get("tenant_id") or data_obj.get("customer") or "org_unknown"
            )
            event_type = event.get("type", "")
            sub = engine.get_subscription(tenant_id) or {}
            from packages.core.storage.tenant_store import get_pg_repo, storage_mode

            if storage_mode() == "postgres":
                pg = get_pg_repo()
                if pg is not None:
                    status = sub.get("status", "active")
                    if event_type == "customer.subscription.deleted":
                        status = "canceled"
                    elif event_type == "invoice.payment_failed":
                        status = "past_due"
                    pg.upsert_subscription(
                        tenant_id,
                        status=status,
                        tier=sub.get("tier"),
                        stripe_customer_id=data_obj.get("customer"),
                        stripe_subscription_id=data_obj.get("id"),
                    )
            # Log event id/type only — never customer PII or raw payload.
            logger.info(f"stripe webhook {event.get('id')} {event_type} -> {message}")
        except Exception:
            logger.exception("stripe webhook persistence failed")
        self.send_json_response({"received": True, "message": message})

    def handle_get_domains(self):
        auth_ctx = self.require_auth()
        if auth_ctx is None:
            return
        from packages.core.storage.tenant_store import TenantStore

        store = TenantStore(auth_ctx.tenant_id)
        domains = store.list_domains()
        self.send_json_response(domains)

    def handle_get_score(self, domain_url: str):
        auth_ctx = self.require_auth()
        if auth_ctx is None:
            return
        from packages.core.storage.tenant_store import TenantStore

        store = TenantStore(auth_ctx.tenant_id)
        if not domain_url:
            self.send_json_response({"error": "domain parameter required"}, status=400)
            return

        score = store.get_latest_score(domain_url)
        if score:
            self.send_json_response(score.model_dump())
        else:
            self.send_json_response({"error": "no score found"}, status=404)

    def handle_get_probes(self, domain_url: str):
        auth_ctx = self.require_auth()
        if auth_ctx is None:
            return
        from packages.core.storage.tenant_store import TenantStore

        store = TenantStore(auth_ctx.tenant_id)
        probes = store.get_probe_history(domain_url if domain_url else None)
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
        auth_ctx = self.require_auth()
        if auth_ctx is None:
            return
        from packages.core.storage.tenant_store import TenantStore

        store = TenantStore(auth_ctx.tenant_id)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        try:
            data = json.loads(body)
            url = data.get("url")
            if not url:
                self.send_json_response({"error": "url is required"}, status=400)
                return

            scorer = Scorer()
            try:
                # Shared boundary incl. the AGENTREADY_ALLOW_PRIVATE_HOSTS
                # opt-in (local dev / smoke tests); direct
                # is_safe_public_url would bypass that allowlist.
                scorer.resolve_and_validate(url)
            except Exception as e:
                self.send_json_response({"error": f"unsafe-target: {e}"}, status=400)
                return

            score = scorer.score_url(url)
            if score.metadata.get("fetch_status", {}).get("html") is None and "unsafe-target" in str(
                score.metadata
            ):
                self.send_json_response({"error": "unsafe scan target rejected"}, status=400)
                return
            store.save_score(url, score)

            self.send_json_response(score.model_dump())
        except Exception:
            self.send_json_response({"error": "scan failed"}, status=500)

    def handle_post_probe(self):
        from packages.core.errors.humanized import HumanizedError
        from packages.core.pipeline.budget_enforcer import BudgetExceededError
        from packages.core.probes.pipeline import ProbePipeline
        from packages.core.probes.prompts import STANDARD_PROBE_PROMPTS
        from packages.core.storage.tenant_store import TenantStore

        auth_ctx = self.require_auth()
        if auth_ctx is None:
            return
        store = TenantStore(auth_ctx.tenant_id)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        try:
            data = json.loads(body)
            url = data.get("url")
            dry_run = data.get("dry_run", True)

            if not url:
                self.send_json_response({"error": "url is required"}, status=400)
                return

            # Phase 17 1.3: full guarded pipeline (budget -> cache ->
            # breaker -> provider -> DLQ), not a lone budget pre-check.
            # BudgetExceededError aborts before any provider call.
            base_domain = extract_domain_from_url(url)
            prober = MultiModelProber()
            pipeline = ProbePipeline(
                budget=BUDGET_ENFORCER,
                tenant_id=auth_ctx.tenant_id,
                org_id=auth_ctx.org_id,
                target_url=url,
            )
            suite_results = pipeline.run_suite(
                prober,
                STANDARD_PROBE_PROMPTS[:3],
                target_domain=base_domain,
                dry_run=dry_run,
            )

            saved_count = 0
            for prompt_run in suite_results:
                for probe_res in prompt_run["results"]:
                    store.save_probe_run(url, probe_res)
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
        except Exception:
            import logging

            # Structured server-side log only; clients get a generic
            # envelope (no stack traces, paths, or internals leak).
            logging.getLogger("agentready.web").exception(
                "probe handler failed for tenant=%s", auth_ctx.tenant_id
            )
            self.send_json_response({"error": "probe failed", "error_code": "PROBE_FAILED"}, status=500)

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
        self.send_header("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        # HSTS is intentionally omitted: this server is localhost-only HTTP.
        # TLS termination (and HSTS) belongs at the reverse proxy / LB.
        # X-Content-Type-Options / X-Frame-Options / Referrer-Policy are set
        # once in end_headers() for every response (no duplicates).
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
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
