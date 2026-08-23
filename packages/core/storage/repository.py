"""Storage repository interface for domain history, scores, and LLM probes."""

import json
from datetime import datetime, timezone
import sqlite3
from typing import Any, Dict, List, Optional

from packages.core.schemas import ComponentStatus, ProbeResult, Score, ScoreComponent
from packages.core.storage.db import get_connection, init_db


class StorageRepository:
    """High-level repository for storing and querying scores and probe history."""

    def __init__(self, conn: Optional[sqlite3.Connection] = None, db_path: Optional[str] = None):
        self.conn = init_db(conn, db_path)

    def get_or_create_domain(self, domain_url: str) -> Dict[str, Any]:
        """Find existing domain or insert a new record."""
        norm_url = domain_url.strip().rstrip("/").lower()
        now = datetime.now(timezone.utc).isoformat()
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM domains WHERE domain_url = ?", (norm_url,))
        row = cursor.fetchone()
        if row:
            return dict(row)

        cursor.execute(
            "INSERT INTO domains (domain_url, created_at, last_scanned_at) VALUES (?, ?, ?)",
            (norm_url, now, None),
        )
        self.conn.commit()
        cursor.execute("SELECT * FROM domains WHERE id = ?", (cursor.lastrowid,))
        return dict(cursor.fetchone())

    def save_score(self, domain_url: str, score: Score) -> int:
        """Persist a score report linked to a domain."""
        domain = self.get_or_create_domain(domain_url)
        now = datetime.now(timezone.utc).isoformat()

        components_data = [c.model_dump() for c in score.components]
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO scores (
                domain_id, url, version, overall_score, grade,
                components_json, summary, recommendations_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                domain["id"],
                score.url,
                score.version,
                score.overall_score,
                score.grade,
                json.dumps(components_data),
                score.summary,
                json.dumps(score.recommendations),
                now,
            ),
        )
        score_id = cursor.lastrowid

        # Update last_scanned_at
        cursor.execute("UPDATE domains SET last_scanned_at = ? WHERE id = ?", (now, domain["id"]))
        self.conn.commit()
        return score_id

    def get_latest_score(self, domain_url: str) -> Optional[Score]:
        """Fetch the most recent score for a domain."""
        domain = self.get_or_create_domain(domain_url)
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM scores WHERE domain_id = ? ORDER BY created_at DESC LIMIT 1",
            (domain["id"],),
        )
        row = cursor.fetchone()
        if not row:
            return None

        components_raw = json.loads(row["components_json"])
        components = [ScoreComponent(**c) for c in components_raw]
        recs = json.loads(row["recommendations_json"])

        return Score(
            url=row["url"],
            version=row["version"],
            timestamp=datetime.fromisoformat(row["created_at"]),
            overall_score=row["overall_score"],
            grade=row["grade"],
            components=components,
            summary=row["summary"],
            recommendations=recs,
        )

    def get_score_history(self, domain_url: str, limit: int = 30) -> List[Dict[str, Any]]:
        """Fetch score time-series for trend graphs."""
        domain = self.get_or_create_domain(domain_url)
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, url, version, overall_score, grade, created_at FROM scores WHERE domain_id = ? ORDER BY created_at ASC LIMIT ?",
            (domain["id"], limit),
        )
        return [dict(r) for r in cursor.fetchall()]

    def save_probe_run(self, domain_url: str, probe_result: ProbeResult) -> int:
        """Record an LLM citation probe result."""
        domain = self.get_or_create_domain(domain_url)
        now = datetime.now(timezone.utc).isoformat()
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO probe_runs (
                domain_id, provider, prompt, raw_response,
                cited_domains_json, extracted_urls_json, latency_ms, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                domain["id"],
                probe_result.provider,
                probe_result.prompt,
                probe_result.raw_response,
                json.dumps(probe_result.cited_domains),
                json.dumps(probe_result.extracted_urls),
                probe_result.latency_ms,
                now,
            ),
        )
        probe_id = cursor.lastrowid
        cursor.execute("UPDATE domains SET last_probed_at = ? WHERE id = ?", (now, domain["id"]))
        self.conn.commit()
        return probe_id

    def list_domains(self) -> List[Dict[str, Any]]:
        """List all tracked domains with their latest score."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT d.*, s.overall_score, s.grade, s.created_at as score_time
            FROM domains d
            LEFT JOIN scores s ON s.id = (
                SELECT s2.id FROM scores s2 WHERE s2.domain_id = d.id ORDER BY s2.created_at DESC LIMIT 1
            )
            ORDER BY d.created_at DESC
        """)
        return [dict(r) for r in cursor.fetchall()]

    def get_probe_history(self, domain_url: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent probe runs."""
        cursor = self.conn.cursor()
        if domain_url:
            domain = self.get_or_create_domain(domain_url)
            cursor.execute(
                "SELECT * FROM probe_runs WHERE domain_id = ? ORDER BY created_at DESC LIMIT ?",
                (domain["id"], limit),
            )
        else:
            cursor.execute("SELECT * FROM probe_runs ORDER BY created_at DESC LIMIT ?", (limit,))

        rows = cursor.fetchall()
        results = []
        for r in rows:
            item = dict(r)
            item["cited_domains"] = json.loads(item["cited_domains_json"])
            item["extracted_urls"] = json.loads(item["extracted_urls_json"])
            results.append(item)
        return results
