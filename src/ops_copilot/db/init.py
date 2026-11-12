"""Database initialization entrypoint."""
from __future__ import annotations

from pathlib import Path

from ops_copilot.db import seed
from ops_copilot.db.database import apply_migrations, get_conn


def init_db(db_path: Path | None = None) -> None:
    """Apply migrations and seed. Idempotent; safe to call on every startup."""
    conn = get_conn(db_path)
    try:
        apply_migrations(conn)
        conn.execute("BEGIN IMMEDIATE")
        try:
            seed.seed(conn)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()


def init_fresh(db_path: Path) -> None:
    """Delete and recreate the DB — used by tests."""
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            p.unlink()
    init_db(db_path)
