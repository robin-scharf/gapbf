"""SQLite-backed persistence for GAPBF runs and attempts."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import Lock

from .database_common import (
    TERMINAL_ATTEMPT_CLASSIFICATIONS,
    AttemptHistoryEntry,
    ResumeInfo,
    RunInfo,
    detect_device_id,
    normalize_db_path,
    stale_run_timeout_seconds,
    utc_now_iso,
)
from .database_schema import DatabaseSchemaMixin
from .database_stores import DatabaseStoreMixin


class RunDatabase(DatabaseSchemaMixin, DatabaseStoreMixin):
    _lock: Lock
    connection: sqlite3.Connection

    def __init__(self, db_path: str, *, read_only: bool = False):
        self._lock = Lock()
        if read_only:
            # Never create or migrate. Used for the web dashboard, which opens
            # caller-supplied paths — a read-only URI can't write a SQLite file
            # to an arbitrary location. Raises OperationalError if absent.
            self.path = Path(db_path).expanduser()
            self.connection = sqlite3.connect(
                f"file:{self.path}?mode=ro", uri=True, check_same_thread=False, timeout=30.0
            )
            self.connection.row_factory = sqlite3.Row
            return
        self.path = normalize_db_path(db_path)
        self.connection = sqlite3.connect(self.path, check_same_thread=False, timeout=30.0)
        self.connection.row_factory = sqlite3.Row
        with self._lock:
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.execute("PRAGMA journal_mode = WAL")
            self.connection.execute("PRAGMA busy_timeout = 30000")
        self._ensure_schema()

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    @staticmethod
    def stale_after_seconds(config) -> int:
        return stale_run_timeout_seconds(config)


__all__ = [
    "AttemptHistoryEntry",
    "ResumeInfo",
    "RunDatabase",
    "RunInfo",
    "TERMINAL_ATTEMPT_CLASSIFICATIONS",
    "detect_device_id",
    "normalize_db_path",
    "stale_run_timeout_seconds",
    "utc_now_iso",
]
