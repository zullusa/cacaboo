"""Persistent storage for the phone-operator lookup cache.

A tiny SQLite table keyed by the 10-digit number stores the last known
operator and the timestamp it was checked at. Entries live for a configurable
TTL (default: a week); after that the caller re-checks the operator.
SQLite is built into the stdlib and the database file lives on a bind mount,
so the cache survives container restarts.
"""

import logging
import os
import sqlite3
import threading
import time

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS operator_cache (
    phone_number TEXT PRIMARY KEY,
    operator     TEXT NOT NULL,
    checked_at   REAL NOT NULL
)
"""


class SqliteOperatorStore:
    """Thread-safe operator cache backed by a local SQLite database.

    The connection is created once and shared across worker threads; a lock
    serializes reads/writes (SQLite single-writer anyway). ``check_same_thread
    =False`` is required because lookups run on send-worker threads.
    """

    def __init__(self, db_path: str) -> None:
        db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute(_SCHEMA)
        self._conn.commit()
        logger.info("Operator cache db ready: %s", db_path)

    def get(self, phone_number: str) -> tuple[str, float] | None:
        """Return (operator, checked_at) for the number or None if absent."""
        with self._lock:
            row = self._conn.execute(
                "SELECT operator, checked_at FROM operator_cache "
                "WHERE phone_number = ?",
                (phone_number,),
            ).fetchone()
        if row is None:
            return None
        return str(row["operator"]), float(row["checked_at"])

    def set(self, phone_number: str, operator: str, checked_at: float | None = None) -> None:
        """Store or refresh the operator of a number."""
        timestamp = checked_at if checked_at is not None else time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO operator_cache (phone_number, operator, checked_at) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(phone_number) DO UPDATE SET "
                "operator = excluded.operator, checked_at = excluded.checked_at",
                (phone_number, operator, timestamp),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()