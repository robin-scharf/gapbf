"""SQLite-backed persistence for GAPBF runs and attempts."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import cast

from .Config import Config


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_db_path(db_path: str) -> Path:
    """Expand the configured database path and ensure its parent exists."""
    resolved = Path(db_path).expanduser()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def detect_device_id(timeout_seconds: int = 30) -> str:
    """Return the connected ADB device serial number.

    Raises RuntimeError when the device serial cannot be determined.
    """
    try:
        result = subprocess.run(
            ["adb", "get-serialno"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=True,
        )
    except FileNotFoundError as error:
        raise RuntimeError(
            "ADB command not found. Please install Android platform-tools"
        ) from error
    except subprocess.CalledProcessError as error:
        stderr = (error.stderr or "").strip()
        raise RuntimeError(f"Failed to determine ADB device id: {stderr or error}") from error
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"Timed out while determining device id after {timeout_seconds}s"
        ) from error

    serial = result.stdout.strip()
    if not serial or serial in {"unknown", "", "<empty>"}:
        raise RuntimeError("ADB did not report a usable device serial number")
    return serial


@dataclass(frozen=True)
class RunInfo:
    """In-memory run metadata returned when a run is created."""

    run_id: str
    config_fingerprint: str
    device_id: str


@dataclass(frozen=True)
class ResumeInfo:
    """Summary of resumable history for a device/config combination."""

    attempted_count: int
    latest_run_id: str | None
    latest_started_at: str | None
    latest_finished_at: str | None
    latest_status: str | None
    latest_successful_attempt: str | None


class RunDatabase:
    """Manage durable run and attempt history in a compact SQLite file."""

    def __init__(self, db_path: str):
        self.path = normalize_db_path(db_path)
        self._lock = Lock()
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        with self._lock:
            self.connection.execute("PRAGMA foreign_keys = ON")
        self._ensure_schema()

    def close(self) -> None:
        """Close the SQLite connection."""
        with self._lock:
            self.connection.close()

    def _ensure_schema(self) -> None:
        with self._lock:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    grid_size INTEGER NOT NULL DEFAULT 3,
                    config_snapshot TEXT NOT NULL,
                    config_fingerprint TEXT NOT NULL,
                    successful_attempt TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_runs_device_fingerprint
                ON runs (device_id, config_fingerprint);

                CREATE INDEX IF NOT EXISTS idx_runs_device_grid_status
                ON runs (device_id, grid_size, status);

                CREATE TABLE IF NOT EXISTS attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    device_id TEXT NOT NULL DEFAULT '',
                    grid_size INTEGER NOT NULL DEFAULT 3,
                    attempt TEXT NOT NULL,
                    response TEXT NOT NULL,
                    stdout TEXT NOT NULL DEFAULT '',
                    stderr TEXT NOT NULL DEFAULT '',
                    result_classification TEXT NOT NULL,
                    returncode INTEGER,
                    duration_ms REAL NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_attempts_run_id ON attempts (run_id);
                CREATE INDEX IF NOT EXISTS idx_attempts_attempt ON attempts (attempt);
                CREATE INDEX IF NOT EXISTS idx_attempts_result ON attempts (result_classification);
                """
            )
            self._ensure_column_exists("runs", "updated_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column_exists("runs", "grid_size", "INTEGER NOT NULL DEFAULT 3")
            self._ensure_column_exists("attempts", "device_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column_exists("attempts", "grid_size", "INTEGER NOT NULL DEFAULT 3")
            self._ensure_column_exists("attempts", "stdout", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column_exists("attempts", "stderr", "TEXT NOT NULL DEFAULT ''")
            self._backfill_runs_metadata()
            self._backfill_attempt_metadata()
            self._deduplicate_attempts()
            self.connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_attempts_device_grid_attempt_unique
                ON attempts (device_id, grid_size, attempt)
                """
            )
            self.connection.commit()

    def _ensure_column_exists(self, table_name: str, column_name: str, definition: str) -> None:
        existing_columns = {
            row["name"]
            for row in self.connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name in existing_columns:
            return
        self.connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    def _backfill_runs_metadata(self) -> None:
        rows = self.connection.execute(
            """
            SELECT run_id, started_at, updated_at, config_snapshot
            FROM runs
            WHERE updated_at = '' OR updated_at IS NULL OR grid_size IS NULL
            """
        ).fetchall()
        for row in rows:
            snapshot = json.loads(row["config_snapshot"])
            grid_size = int(snapshot.get("grid_size", 3))
            updated_at = row["updated_at"] or row["started_at"]
            self.connection.execute(
                """
                UPDATE runs
                SET updated_at = ?, grid_size = ?
                WHERE run_id = ?
                """,
                (updated_at, grid_size, row["run_id"]),
            )

    def _backfill_attempt_metadata(self) -> None:
        rows = self.connection.execute(
            """
            SELECT attempts.id, attempts.run_id, attempts.device_id, attempts.grid_size
            FROM attempts
            WHERE attempts.device_id = ''
               OR attempts.device_id IS NULL
               OR attempts.grid_size IS NULL
            """
        ).fetchall()
        for row in rows:
            run_row = self.connection.execute(
                "SELECT device_id, grid_size FROM runs WHERE run_id = ?",
                (row["run_id"],),
            ).fetchone()
            if run_row is None:
                continue
            self.connection.execute(
                """
                UPDATE attempts
                SET device_id = ?, grid_size = ?
                WHERE id = ?
                """,
                (run_row["device_id"], run_row["grid_size"], row["id"]),
            )

    def _deduplicate_attempts(self) -> None:
        duplicate_rows = self.connection.execute(
            """
            SELECT device_id, grid_size, attempt, MIN(id) AS keep_id
            FROM attempts
            GROUP BY device_id, grid_size, attempt
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        for row in duplicate_rows:
            self.connection.execute(
                """
                DELETE FROM attempts
                WHERE device_id = ? AND grid_size = ? AND attempt = ? AND id <> ?
                """,
                (row["device_id"], row["grid_size"], row["attempt"], row["keep_id"]),
            )

    def _config_snapshot(self, config: Config) -> dict[str, object]:
        snapshot = config.model_dump()
        snapshot.pop("total_paths", None)
        snapshot.pop("config_file_path", None)
        return snapshot

    def config_fingerprint(self, config: Config) -> str:
        payload = json.dumps(self._config_snapshot(config), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def create_run(self, config: Config, device_id: str, mode: str) -> RunInfo:
        run_id = str(uuid.uuid4())
        fingerprint = self.config_fingerprint(config)
        snapshot_json = json.dumps(self._config_snapshot(config), sort_keys=True)
        created_at = utc_now_iso()
        with self._lock:
            self._reconcile_stale_runs_locked(
                device_id,
                config.grid_size,
                stale_after_seconds=stale_run_timeout_seconds(config),
            )
            self.connection.execute(
                """
                INSERT INTO runs (
                    run_id, started_at, updated_at, status, mode, device_id, grid_size,
                    config_snapshot, config_fingerprint
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    created_at,
                    created_at,
                    "running",
                    mode,
                    device_id,
                    config.grid_size,
                    snapshot_json,
                    fingerprint,
                ),
            )
            self.connection.commit()
        return RunInfo(
            run_id=run_id,
            config_fingerprint=fingerprint,
            device_id=device_id,
        )

    def finish_run(
        self,
        run_id: str,
        status: str,
        successful_attempt: str | None = None,
    ) -> None:
        with self._lock:
            self.connection.execute(
                """
                UPDATE runs
                SET finished_at = ?, updated_at = ?, status = ?,
                    successful_attempt = COALESCE(?, successful_attempt)
                WHERE run_id = ?
                """,
                (utc_now_iso(), utc_now_iso(), status, successful_attempt, run_id),
            )
            self.connection.commit()

    def reconcile_stale_runs(
        self,
        device_id: str,
        grid_size: int,
        *,
        stale_after_seconds: int,
    ) -> int:
        with self._lock:
            return self._reconcile_stale_runs_locked(
                device_id,
                grid_size,
                stale_after_seconds=stale_after_seconds,
            )

    def _reconcile_stale_runs_locked(
        self,
        device_id: str,
        grid_size: int,
        *,
        stale_after_seconds: int,
    ) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)
        cutoff_iso = cutoff.isoformat(timespec="seconds")
        reconciled_at = utc_now_iso()
        cursor = self.connection.execute(
            """
            UPDATE runs
            SET status = 'interrupted_or_crashed',
                finished_at = COALESCE(finished_at, updated_at),
                updated_at = ?
            WHERE device_id = ? AND grid_size = ? AND status = 'running' AND updated_at < ?
            """,
            (reconciled_at, device_id, grid_size, cutoff_iso),
        )
        self.connection.commit()
        return int(cursor.rowcount)

    def touch_run(self, run_id: str) -> None:
        with self._lock:
            self.connection.execute(
                "UPDATE runs SET updated_at = ? WHERE run_id = ?",
                (utc_now_iso(), run_id),
            )
            self.connection.commit()

    def get_attempted_paths(self, config: Config, device_id: str) -> set[str]:
        with self._lock:
            rows = self.connection.execute(
                """
                SELECT DISTINCT attempt
                FROM attempts
                WHERE device_id = ? AND grid_size = ?
                """,
                (device_id, config.grid_size),
            ).fetchall()
        return {row[0] for row in rows}

    def get_resume_info(self, config: Config, device_id: str) -> ResumeInfo:
        with self._lock:
            attempted_count_row = self.connection.execute(
                """
                SELECT COUNT(*) AS attempted_count
                FROM attempts
                WHERE device_id = ? AND grid_size = ?
                """,
                (device_id, config.grid_size),
            ).fetchone()

            latest_row = self.connection.execute(
                """
                SELECT run_id, started_at, finished_at, status, successful_attempt
                FROM runs
                WHERE device_id = ? AND grid_size = ?
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (device_id, config.grid_size),
            ).fetchone()

        return ResumeInfo(
            attempted_count=int(attempted_count_row["attempted_count"] or 0),
            latest_run_id=latest_row["run_id"] if latest_row else None,
            latest_started_at=latest_row["started_at"] if latest_row else None,
            latest_finished_at=latest_row["finished_at"] if latest_row else None,
            latest_status=latest_row["status"] if latest_row else None,
            latest_successful_attempt=(
                latest_row["successful_attempt"] if latest_row else None
            ),
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
            self.connection.execute(
                """
                INSERT INTO attempts (
                    run_id, timestamp, device_id, grid_size, attempt, response,
                    stdout, stderr, result_classification, returncode, duration_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    utc_now_iso(),
                    run_row["device_id"],
                    run_row["grid_size"],
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
                "UPDATE runs SET updated_at = ? WHERE run_id = ?",
                (utc_now_iso(), run_id),
            )
            self.connection.commit()

    def list_runs(self, limit: int = 20) -> list[sqlite3.Row]:
        """Return recent runs with attempt counts for CLI display."""
        with self._lock:
            rows = self.connection.execute(
                """
                SELECT
                    runs.run_id,
                    runs.started_at,
                    runs.finished_at,
                    runs.status,
                    runs.mode,
                    runs.device_id,
                    runs.grid_size,
                    runs.successful_attempt,
                    COUNT(attempts.id) AS attempt_count
                FROM runs
                LEFT JOIN attempts ON attempts.run_id = runs.run_id
                GROUP BY runs.run_id
                ORDER BY runs.started_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return list(rows)

    def get_run(self, run_id: str) -> sqlite3.Row | None:
        """Return a single run row with an aggregated attempt count."""
        with self._lock:
            row = self.connection.execute(
                """
                SELECT
                    runs.run_id,
                    runs.started_at,
                    runs.finished_at,
                    runs.status,
                    runs.mode,
                    runs.device_id,
                    runs.grid_size,
                    runs.successful_attempt,
                    runs.config_snapshot,
                    runs.config_fingerprint,
                    COUNT(attempts.id) AS attempt_count
                FROM runs
                LEFT JOIN attempts ON attempts.run_id = runs.run_id
                WHERE runs.run_id = ?
                GROUP BY runs.run_id
                """,
                (run_id,),
            ).fetchone()
        return cast(sqlite3.Row | None, row)

    def list_attempts(self, run_id: str, limit: int = 200, offset: int = 0) -> list[sqlite3.Row]:
        """Return attempts for a run in reverse chronological order."""
        with self._lock:
            rows = self.connection.execute(
                """
                SELECT
                    id,
                    run_id,
                    timestamp,
                    attempt,
                    response,
                    stdout,
                    stderr,
                    result_classification,
                    returncode,
                    duration_ms
                FROM attempts
                WHERE run_id = ?
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (run_id, limit, offset),
            ).fetchall()
        return list(rows)


def stale_run_timeout_seconds(config: Config) -> int:
    minimum_timeout = 300
    attempt_window = int(config.adb_timeout + config.attempt_delay) * 3 + 30
    return max(minimum_timeout, attempt_window)
