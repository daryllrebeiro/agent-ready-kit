"""Embedded local dashboard HTTP server with REST APIs for scoring and probing."""

import json
import os
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Optional
import webbrowser

from packages.core.probes.extractor import extract_domain_from_url
from packages.core.probes.runner import MultiModelProber
from packages.core.scorer import Scorer
from packages.core.storage.repository import StorageRepository

WEB_DIR = os.path.dirname(os.path.abspath(__file__))


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
        elif path == "/openapi.json":
            self.handle_get_openapi()
        elif path == "/docs":
            self.handle_get_docs()
        else:
            # Fallback to static files
            super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/scan":
            self.handle_post_scan()
        elif path == "/api/probe":
            self.handle_post_probe()
        else:
            self.send_error(404, "API endpoint not found")

    def handle_get_domains(self):
        repo = StorageRepository()
        domains = repo.list_domains()
        self.send_json_response(domains)

    def handle_get_score(self, domain_url: str):
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
        repo = StorageRepository()
        probes = repo.get_probe_history(domain_url if domain_url else None)
        self.send_json_response(probes)

    def handle_get_badge(self, domain_url: str, label: str = "agent-ready"):
        from packages.core.badges.generator import BadgeGenerator
        scorer = Scorer()
        repo = StorageRepository()
        score = repo.get_latest_score(domain_url) if domain_url else None
        if not score and domain_url:
            score = scorer.score_url(domain_url)
        if not score:
            score = Score(
                url=domain_url or "unknown",
                version="score_v0.1",
                overall_score=0.0,
                grade="F",
                components=[],
                summary="No score",
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
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        try:
            data = json.loads(body)
            url = data.get("url")
            if not url:
                self.send_json_response({"error": "url is required"}, status=400)
                return

            scorer = Scorer()
            score = scorer.score_url(url)
            repo = StorageRepository()
            repo.save_score(url, score)

            self.send_json_response(score.model_dump())
        except Exception as e:
            self.send_json_response({"error": str(e)}, status=500)

    def handle_post_probe(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        try:
            data = json.loads(body)
            url = data.get("url")
            dry_run = data.get("dry_run", True)

            if not url:
                self.send_json_response({"error": "url is required"}, status=400)
                return

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

            self.send_json_response({
                "status": "success",
                "probes_run": saved_count,
                "domain": base_domain,
            })
        except Exception as e:
            self.send_json_response({"error": str(e)}, status=500)

    def send_json_response(self, data: any, status: int = 200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def start_server(port: int = 3000, open_browser: bool = False) -> None:
    """Start local web dashboard server."""
    server_address = ("", port)
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
