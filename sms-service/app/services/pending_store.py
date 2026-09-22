"""Persistent storage for SMS queued by a gateway until its working hours.

When sms.ru accepts a message outside its working hours (10:00-20:00 by
default) it does not send it: the message stays in sms.ru's own queue with
status_code 100 and a returned sms_id, and is only dispatched once working
hours begin. The delivery status therefore cannot become terminal before
that, so the service remembers those sms_id values here and re-checks them
later when the working hours have started.

The database file lives on a bind mount, so the pending messages survive
container restarts (a reminder queued at 22:00 is still tracked at 10:00).
"""

import logging
import os
import sqlite3
import threading
import time

from app.domain.models import SmsMessage
from app.interfaces.protocols import QueuedSmsStore

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pending_queued_sms (
    sms_id          TEXT PRIMARY KEY,
    message_json    TEXT NOT NULL,
    queued_at       REAL NOT NULL,
    last_checked_at REAL,
    attempts        INTEGER NOT NULL DEFAULT 0
)
"""


class SqlitePendingQueuedStore(QueuedSmsStore):
    """Thread-safe store of gateway-queued SMS backed by a local SQLite DB.

    The connection is created once and shared across worker threads; a lock
    serializes reads/writes (SQLite is single-writer anyway) and
    ``check_same_thread=False`` is required because queries run on the send
    and the queued-delivery worker threads.
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
        logger.info("Pending queued SMS store ready: %s", db_path)

    def add(self, sms_id: str, message: SmsMessage) -> None:
        """Remember a gateway-queued SMS (idempotent, keeps the first queued_at)."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO pending_queued_sms (sms_id, message_json, queued_at) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(sms_id) DO UPDATE SET message_json = excluded.message_json",
                (sms_id, message.to_json(), time.time()),
            )
            self._conn.commit()

    def list(self) -> list[tuple[str, SmsMessage, int]]:
        """Return (sms_id, message, attempts) for every pending SMS."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT sms_id, message_json, attempts FROM pending_queued_sms "
                "ORDER BY queued_at"
            ).fetchall()
        items: list[tuple[str, SmsMessage, int]] = []
        for row in rows:
            try:
                message = SmsMessage.from_json(row["message_json"])
            except Exception:
                logger.exception(
                    "Dropping unparseable pending queued SMS %s", row["sms_id"]
                )
                self.remove(row["sms_id"])
                continue
            items.append((str(row["sms_id"]), message, int(row["attempts"])))
        return items

    def touch(self, sms_id: str) -> int:
        """Record one more status re-check and return the new attempt count."""
        with self._lock:
            self._conn.execute(
                "UPDATE pending_queued_sms SET attempts = attempts + 1, "
                "last_checked_at = ? WHERE sms_id = ?",
                (time.time(), sms_id),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT attempts FROM pending_queued_sms WHERE sms_id = ?",
                (sms_id,),
            ).fetchone()
        return int(row["attempts"]) if row is not None else 0

    def remove(self, sms_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM pending_queued_sms WHERE sms_id = ?", (sms_id,)
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()