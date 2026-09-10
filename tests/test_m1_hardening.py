"""M1 hardening regression tests: prove P0/P1 fixes through live paths, not mocks."""

import sqlite3

from packages.core.checks.bot_permissions import evaluate_bot_permission, parse_robots_txt
from packages.core.scorer import Scorer
from packages.core.storage.db import init_db
from packages.core.storage.migration import SQLiteToPostgresMigrator
from packages.core.storage.repository import StorageRepository


class TestRobotsGroupSemantics:
    def test_star_after_specific_does_not_bleed(self):
        content = "User-agent: GPTBot\nDisallow:\n\nUser-agent: *\nDisallow: /\n"
        parsed = parse_robots_txt(content)
        assert evaluate_bot_permission("GPTBot", parsed)["status"] == "ALLOWED"
        assert evaluate_bot_permission("ClaudeBot", parsed)["status"] == "BLOCKED"

    def test_specific_after_star(self):
        content = "User-agent: *\nDisallow: /\n\nUser-agent: GPTBot\nDisallow:\n"
        parsed = parse_robots_txt(content)
        assert evaluate_bot_permission("GPTBot", parsed)["status"] == "ALLOWED"
        assert evaluate_bot_permission("ClaudeBot", parsed)["status"] == "BLOCKED"

    def test_multi_ua_group(self):
        content = "User-agent: GPTBot\nUser-agent: ClaudeBot\nDisallow: /private\n"
        parsed = parse_robots_txt(content)
        assert "/private" in parsed["rules"]["gptbot"]["disallows"]
        assert "/private" in parsed["rules"]["claudebot"]["disallows"]

    def test_empty_disallow_unblocks(self):
        content = "User-agent: GPTBot\nDisallow:\n"
        parsed = parse_robots_txt(content)
        assert evaluate_bot_permission("GPTBot", parsed)["status"] == "ALLOWED"


class TestSSRFGuard:
    def test_literal_private_ip_rejected(self):
        s = Scorer()
        res = s.fetch_resource("http://127.0.0.1/robots.txt")
        assert res["success"] is False
        assert "unsafe-target" in res["error"]

    def test_metadata_endpoint_rejected(self):
        s = Scorer()
        res = s.fetch_resource("http://169.254.169.254/latest/meta-data/")
        assert res["success"] is False
        assert "unsafe-target" in res["error"]

    def test_non_http_scheme_rejected(self):
        s = Scorer()
        res = s.fetch_resource("file:///etc/passwd")
        assert res["success"] is False
        assert "unsafe-target" in res["error"]


class TestMigrationHonesty:
    def _seed_sqlite(self, path):
        repo = StorageRepository(db_path=path)
        html = "<html><head><title>T</title></head><body><p>hello world</p></body></html>"
        score = Scorer().score_payloads("https://example.com", html_content=html)
        repo.save_score("https://example.com", score)
        repo.conn.commit()
        repo.conn.close()

    def test_migrates_and_reconciles(self, tmp_path):
        from packages.core.storage.postgres_rls import MockPostgresConnection, PostgresRLSRepository

        src = str(tmp_path / "src.db")
        self._seed_sqlite(src)
        target = PostgresRLSRepository(connection=MockPostgresConnection())
        stats, reconciled = SQLiteToPostgresMigrator(src, target).migrate()
        assert reconciled is True
        assert stats["domains_migrated"] == 1
        assert stats["scores_migrated"] == 1

    def test_corrupt_source_fails_loudly(self, tmp_path):
        from packages.core.storage.postgres_rls import MockPostgresConnection, PostgresRLSRepository

        src = str(tmp_path / "bad.db")
        conn = sqlite3.connect(src)
        init_db(conn)
        # Insert a score row with invalid JSON blobs -> must not reconcile.
        conn.execute(
            "INSERT INTO domains (domain_url, created_at) VALUES (?, ?)",
            ("https://example.com", "2026-01-01T00:00:00+00:00"),
        )
        dom_id = conn.execute("SELECT id FROM domains").fetchone()[0]
        conn.execute(
            """INSERT INTO scores (domain_id, url, version, overall_score, grade,
               components_json, summary, recommendations_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                dom_id,
                "https://example.com",
                "score_v0.1",
                10.0,
                "F",
                "not-json",
                "x",
                "[]",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        conn.commit()
        conn.close()
        target = PostgresRLSRepository(connection=MockPostgresConnection())
        _stats, reconciled = SQLiteToPostgresMigrator(src, target).migrate()
        assert reconciled is False


class TestProbePipeline:
    def test_budget_refuses_before_spend(self):
        from packages.core.pipeline.budget_enforcer import BudgetExceededError
        from packages.core.probes.pipeline import ProbePipeline
        from packages.core.probes.providers import OpenAIProbe

        pipe = ProbePipeline(tenant_id="t1", plan_tier="free")
        # Exhaust free-tier budget via the underlying cache counter.
        pipe.cache.increment_tenant_usage("t1", 10000)
        try:
            pipe.run(OpenAIProbe(), "hello", dry_run=False)
            raise AssertionError("should have raised BudgetExceededError")
        except BudgetExceededError:
            pass

    def test_provider_error_trips_breaker_and_dlq(self):
        from packages.core.probes.base import BaseProbe
        from packages.core.probes.pipeline import ProbePipeline
        from packages.core.schemas import ProbeResult

        class Flaky(BaseProbe):
            @property
            def provider_name(self):
                return "flaky-test-provider"

            def probe(self, prompt, dry_run=False):
                return ProbeResult(
                    provider="flaky-test-provider",
                    prompt=prompt,
                    raw_response="[API Error 500]: boom",
                    cited_domains=[],
                    extracted_urls=[],
                )

        pipe = ProbePipeline(tenant_id="t2")
        for _ in range(5):
            try:
                pipe.run(Flaky(), "q", dry_run=False)
            except Exception:
                pass
        assert len(pipe.dlq) >= 1
        assert pipe._breaker_for("flaky-test-provider").can_execute() is False

    def test_cache_dedup_avoids_provider_call(self):
        from packages.core.probes.pipeline import ProbePipeline
        from packages.core.probes.providers import OpenAIProbe

        pipe = ProbePipeline(tenant_id="t3")
        first = pipe.run(OpenAIProbe(), "dedup prompt", dry_run=True)
        # Store into cache manually for non-dry path, then ensure hit.
        pipe.cache.store_cached_probe("t3", "openai", "d prompt", first)
        calls = {"n": 0}

        from packages.core.probes.base import BaseProbe

        class Counting(BaseProbe):
            @property
            def provider_name(self):
                return "openai"

            def probe(self, prompt, dry_run=False):
                calls["n"] += 1
                return first

        got = pipe.run(Counting(), "d prompt", dry_run=False)
        assert got == first
        assert calls["n"] == 0


class TestSingleSourceConstants:
    def test_one_version_one_prefix_one_weights(self):
        from packages.cli.main import CLI_VERSION
        from packages.core import config
        from packages.core.auth.middleware import AuthManager
        from packages.core.version import (
            AGENTREADY_VERSION,
            ALGORITHM_VERSION,
            API_KEY_PREFIX,
            DEFAULT_WEIGHTS,
        )

        assert CLI_VERSION == AGENTREADY_VERSION
        assert config.ALGORITHM_VERSION == ALGORITHM_VERSION == "score_v0.1"
        assert config.DEFAULT_WEIGHTS == DEFAULT_WEIGHTS
        key = AuthManager().generate_api_key("t")
        assert key.startswith(API_KEY_PREFIX)

    def test_save_probe_no_crash(self):
        from packages.core.schemas import ProbeResult
        from packages.core.storage.postgres_rls import MockPostgresConnection, PostgresRLSRepository

        repo = PostgresRLSRepository(connection=MockPostgresConnection())
        pr = ProbeResult(provider="openai", prompt="q", raw_response="r")
        pid = repo.save_probe("t", "https://example.com", pr)
        assert pid.startswith("pr_")

    def test_badge_missing_domain_400(self):

        from apps.web.server import DashboardAPIHandler

        handler = DashboardAPIHandler.__new__(DashboardAPIHandler)
        captured = {}

        def fake_json(data, status=200):
            captured["data"] = data
            captured["status"] = status

        handler.send_json_response = fake_json
        handler.handle_get_badge("", "agent-ready")
        assert captured["status"] == 400
