from __future__ import annotations

import sqlite3
from threading import Lock

from .Config import Config
from .database_common import (
    TERMINAL_ATTEMPT_CLASSIFICATIONS,
    AttemptHistoryEntry,
    utc_now_iso,
)


class DatabaseAttemptStoreMixin:
    _lock: Lock
    connection: sqlite3.Connection

    def attempt_hash_for(self, device_id: str, grid_size: int, attempt: str) -> str:
        raise NotImplementedError

    def get_attempted_paths(self, config: Config, device_id: str) -> set[str]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT DISTINCT attempt FROM attempts WHERE device_id = ? AND grid_size = ?",
                (device_id, config.grid_size),
            ).fetchall()
        return {row[0] for row in rows}

    def get_terminal_attempt_history(
        self, config: Config, device_id: str
    ) -> dict[str, AttemptHistoryEntry]:
        with self._lock:
            rows = self.connection.execute(
                """
                SELECT attempt, attempt_hash, result_classification
                FROM attempts
                WHERE device_id = ? AND grid_size = ? AND result_classification IN (?, ?)
                """,
                (device_id, config.grid_size, *sorted(TERMINAL_ATTEMPT_CLASSIFICATIONS)),
            ).fetchall()
        return {
            row["attempt_hash"]: AttemptHistoryEntry(
                attempt=row["attempt"],
                attempt_hash=row["attempt_hash"],
                result_classification=row["result_classification"],
            )
            for row in rows
        }

    def get_terminal_attempt_entry(
        self, config: Config, device_id: str, attempt: str
    ) -> AttemptHistoryEntry | None:
        attempt_hash = self.attempt_hash_for(device_id, config.grid_size, attempt)
        with self._lock:
            row = self.connection.execute(
                """
                SELECT attempt, attempt_hash, result_classification
                FROM attempts
                WHERE attempt_hash = ? AND result_classification IN (?, ?)
                LIMIT 1
                """,
                (attempt_hash, *sorted(TERMINAL_ATTEMPT_CLASSIFICATIONS)),
            ).fetchone()
        if row is None:
            return None
        return AttemptHistoryEntry(
            attempt=row["attempt"],
            attempt_hash=row["attempt_hash"],
            result_classification=row["result_classification"],
        )

    def log_attempt(
        self,
        run_id: str,
        attempt: str,
        response: str,
        result_classification: str,
        returncode: int | None,
        duration_ms: float,
        *,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        with self._lock:
            run_row = self.connection.execute(
                "SELECT device_id, grid_size FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if run_row is None:
                raise ValueError(f"Unknown run_id: {run_id}")
            attempt_hash = self.attempt_hash_for(
                run_row["device_id"],
                int(run_row["grid_size"]),
                attempt,
            )
            self.connection.execute(
                """
                INSERT INTO attempts (
                    run_id, timestamp, device_id, grid_size, attempt_hash, attempt,
                    response, stdout, stderr, result_classification,
                    returncode, duration_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    utc_now_iso(),
                    run_row["device_id"],
                    run_row["grid_size"],
                    attempt_hash,
                    attempt,
                    response,
                    stdout,
                    stderr,
                    result_classification,
                    returncode,
                    duration_ms,
                ),
            )
            self.connection.execute(
                "UPDATE runs SET updated_at = ? WHERE run_id = ?", (utc_now_iso(), run_id)
            )
            self.connection.commit()

    def list_attempts(
        self,
        run_id: str,
        limit: int = 200,
        offset: int = 0,
    ) -> list[sqlite3.Row]:
        with self._lock:
            rows = self.connection.execute(
                """
                SELECT
                    id, run_id, timestamp, attempt_hash, attempt, response,
                    stdout, stderr, result_classification,
                    returncode, duration_ms
                FROM attempts WHERE run_id = ? ORDER BY id DESC LIMIT ? OFFSET ?
                """,
                (run_id, limit, offset),
            ).fetchall()
        return list(rows)