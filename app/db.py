"""SQLite access: connection factory, per-request sessions, schema bootstrap."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from . import settings

SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"


def connect() -> sqlite3.Connection:
    """Open a connection to the embedded SQLite database.

    WAL keeps concurrent readers from blocking the single writer, and foreign
    keys are enforced per connection (SQLite's default is off).
    """
    path = settings.database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def session() -> Iterator[sqlite3.Connection]:
    """Yield a connection, commit on success, roll back on failure."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create the schema if it is missing. Safe to call on every boot."""
    with session() as conn:
        conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
