"""SQLite storage — schema, migrations, seed data (ADR-0008).

Two databases under data/:
  ops_copilot.db  — domain data (faculty, courses, CRM, LMS, calendar)
  checkpoints.db  — LangGraph workflow state (owned by the checkpointer, ADR-0001)

Connections use WAL + busy_timeout; transactions are explicit (autocommit off
by hand via isolation_level=None) so booking can use BEGIN IMMEDIATE (ADR-0009).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from ops_copilot.config import settings

_SCHEMA_VERSION = 2

# ── Migrations (versioned; applied in order, tracked in schema_migrations) ────

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS faculty (
            id                TEXT PRIMARY KEY,
            name              TEXT NOT NULL,
            expertise         TEXT NOT NULL,
            subjects          TEXT NOT NULL,
            available_days    TEXT NOT NULL,
            time_slot         TEXT NOT NULL,
            current_batches   INTEGER NOT NULL DEFAULT 0,
            max_batches       INTEGER NOT NULL DEFAULT 2,
            rating            REAL    NOT NULL DEFAULT 4.5,
            students_taught   INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS lms_state (
            id                 INTEGER PRIMARY KEY DEFAULT 1,
            total_capacity     INTEGER NOT NULL,
            current_enrollment INTEGER NOT NULL,
            active_batches     INTEGER NOT NULL,
            max_batches        INTEGER NOT NULL,
            setup_time_days    INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS crm_data (
            subject_area             TEXT PRIMARY KEY,
            avg_enrollment           INTEGER NOT NULL,
            min_enrollment           INTEGER NOT NULL,
            max_enrollment           INTEGER NOT NULL,
            current_leads            INTEGER NOT NULL,
            top_channels             TEXT NOT NULL,
            best_launch_months       TEXT NOT NULL,
            avg_revenue_per_student  INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS courses (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            category        TEXT NOT NULL,
            subject_area   TEXT NOT NULL,
            description    TEXT NOT NULL,
            duration_weeks INTEGER NOT NULL DEFAULT 16,
            price          INTEGER NOT NULL DEFAULT 2999
        );
        CREATE TABLE IF NOT EXISTS faculty_calendar (
            faculty_id  TEXT NOT NULL,
            date        TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'blocked',
            notes       TEXT,
            PRIMARY KEY (faculty_id, date)
        );
        """,
    ),
    (
        2,
        """
        ALTER TABLE faculty_calendar ADD COLUMN session_id TEXT;
        ALTER TABLE faculty_calendar ADD COLUMN reserved_at TEXT;
        CREATE INDEX IF NOT EXISTS idx_calendar_session ON faculty_calendar(session_id);
        CREATE INDEX IF NOT EXISTS idx_calendar_status ON faculty_calendar(faculty_id, status, date);
        """,
    ),
]


def get_conn(db_path: Path | None = None) -> sqlite3.Connection:
    """A fresh connection with WAL and busy timeout. Caller closes it."""
    path = db_path or settings.app_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)  # autocommit; explicit BEGIN
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def apply_migrations(conn: sqlite3.Connection) -> int:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version INTEGER PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
    current = row["v"] or 0
    for version, sql in MIGRATIONS:
        if version <= current:
            continue
        # executescript() issues an implicit COMMIT — incompatible with our
        # explicit BEGIN IMMEDIATE, so split and execute statement by statement
        statements = [s.strip() for s in sql.split(";") if s.strip()]
        conn.execute("BEGIN IMMEDIATE")
        try:
            for stmt in statements:
                conn.execute(stmt)
            conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return current
