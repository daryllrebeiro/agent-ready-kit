"""SQLite Database management for AgentReady storage layer."""

import os
import sqlite3
from typing import Optional

DEFAULT_DB_PATH = os.path.join(os.getcwd(), "agentready.db")


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Create a thread-safe connection to SQLite database."""
    path = db_path or os.environ.get("AGENTREADY_DB_PATH", DEFAULT_DB_PATH)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def init_db(conn: Optional[sqlite3.Connection] = None, db_path: Optional[str] = None) -> sqlite3.Connection:
    """Initialize database tables and indexes."""
    db = conn or get_connection(db_path)
    with db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain_url TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            last_scanned_at TEXT,
            last_probed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            version TEXT NOT NULL,
            overall_score REAL NOT NULL,
            grade TEXT NOT NULL,
            components_json TEXT NOT NULL,
            summary TEXT NOT NULL,
            recommendations_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (domain_id) REFERENCES domains(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS probe_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain_id INTEGER,
            provider TEXT NOT NULL,
            prompt TEXT NOT NULL,
            raw_response TEXT NOT NULL,
            cited_domains_json TEXT NOT NULL,
            extracted_urls_json TEXT NOT NULL,
            latency_ms REAL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (domain_id) REFERENCES domains(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_scores_domain ON scores(domain_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_probes_domain ON probe_runs(domain_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_domains_url ON domains(domain_url);
        """)
    return db
