"""SQLite-backed persistence for GAPBF runs and attempts."""

from __future__ import annotations

import sqlite3
from threading import Lock

from .database_common import (
    ResumeInfo,
    RunInfo,
    detect_device_id,
    normalize_db_path,
    stale_run_timeout_seconds,
    utc_now_iso,
)
from .database_operations import DatabaseOperationsMixin
from .database_schema import DatabaseSchemaMixin


class RunDatabase(DatabaseSchemaMixin, DatabaseOperationsMixin):
    def __init__(self, db_path: str):
        self.path = normalize_db_path(db_path)
        self._lock = Lock()
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        with self._lock:
            self.connection.execute("PRAGMA foreign_keys = ON")
        self._ensure_schema()

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    @staticmethod
    def stale_after_seconds(config) -> int:
        return stale_run_timeout_seconds(config)


__all__ = [
    "ResumeInfo",
    "RunDatabase",
    "RunInfo",
    "detect_device_id",
    "normalize_db_path",
    "stale_run_timeout_seconds",
    "utc_now_iso",
]
