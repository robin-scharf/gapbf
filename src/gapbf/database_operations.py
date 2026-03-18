# mypy: disable-error-code=attr-defined
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import cast

from .Config import Config
from .database_common import ResumeInfo, RunInfo, utc_now_iso


class DatabaseOperationsMixin:
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
        created_at = utc_now_iso()
        with self._lock:
            self._reconcile_stale_runs_locked(
                device_id,
                config.grid_size,
                stale_after_seconds=self.stale_after_seconds(config),
            )
            self.connection.execute(
                """
                INSERT INTO runs (
                    run_id, started_at, updated_at, status, mode,
                    device_id, grid_size, config_snapshot,
                    config_fingerprint
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
                    json.dumps(self._config_snapshot(config), sort_keys=True),
                    fingerprint,
                ),
            )
            self.connection.commit()
        return RunInfo(run_id=run_id, config_fingerprint=fingerprint, device_id=device_id)

    def finish_run(self, run_id: str, status: str, successful_attempt: str | None = None) -> None:
        with self._lock:
            now = utc_now_iso()
            self.connection.execute(
                """
                UPDATE runs
                SET finished_at = ?, updated_at = ?, status = ?,
                    successful_attempt = COALESCE(?, successful_attempt)
                WHERE run_id = ?
                """,
                (now, now, status, successful_attempt, run_id),
            )
            self.connection.commit()

    def reconcile_stale_runs(
        self, device_id: str, grid_size: int, *, stale_after_seconds: int
    ) -> int:
        with self._lock:
            return self._reconcile_stale_runs_locked(
                device_id, grid_size, stale_after_seconds=stale_after_seconds
            )

    def _reconcile_stale_runs_locked(
        self, device_id: str, grid_size: int, *, stale_after_seconds: int
    ) -> int:
        cutoff_iso = (
            datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)
        ).isoformat(timespec="seconds")
        cursor = self.connection.execute(
            """
            UPDATE runs
            SET status = 'interrupted_or_crashed',
                finished_at = COALESCE(finished_at, updated_at), updated_at = ?
            WHERE device_id = ? AND grid_size = ? AND status = 'running' AND updated_at < ?
            """,
            (utc_now_iso(), device_id, grid_size, cutoff_iso),
        )
        self.connection.commit()
        return int(cursor.rowcount)

    def touch_run(self, run_id: str) -> None:
        with self._lock:
            self.connection.execute(
                "UPDATE runs SET updated_at = ? WHERE run_id = ?", (utc_now_iso(), run_id)
            )
            self.connection.commit()

    def get_attempted_paths(self, config: Config, device_id: str) -> set[str]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT DISTINCT attempt FROM attempts WHERE device_id = ? AND grid_size = ?",
                (device_id, config.grid_size),
            ).fetchall()
        return {row[0] for row in rows}

    def get_resume_info(self, config: Config, device_id: str) -> ResumeInfo:
        with self._lock:
            attempted_count_row = self.connection.execute(
                (
                    "SELECT COUNT(*) AS attempted_count FROM attempts "
                    "WHERE device_id = ? AND grid_size = ?"
                ),
                (device_id, config.grid_size),
            ).fetchone()
            latest_row = self.connection.execute(
                """
                SELECT run_id, started_at, finished_at, status, successful_attempt
                FROM runs WHERE device_id = ? AND grid_size = ?
                ORDER BY started_at DESC LIMIT 1
                """,
                (device_id, config.grid_size),
            ).fetchone()
        return ResumeInfo(
            attempted_count=int(attempted_count_row["attempted_count"] or 0),
            latest_run_id=latest_row["run_id"] if latest_row else None,
            latest_started_at=latest_row["started_at"] if latest_row else None,
            latest_finished_at=latest_row["finished_at"] if latest_row else None,
            latest_status=latest_row["status"] if latest_row else None,
            latest_successful_attempt=latest_row["successful_attempt"] if latest_row else None,
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
                    run_id, timestamp, device_id, grid_size, attempt,
                    response, stdout, stderr, result_classification,
                    returncode, duration_ms
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
                "UPDATE runs SET updated_at = ? WHERE run_id = ?", (utc_now_iso(), run_id)
            )
            self.connection.commit()

    def list_runs(self, limit: int = 20) -> list[sqlite3.Row]:
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
                FROM runs LEFT JOIN attempts ON attempts.run_id = runs.run_id
                GROUP BY runs.run_id ORDER BY runs.started_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return list(rows)

    def get_run(self, run_id: str) -> sqlite3.Row | None:
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
                FROM runs LEFT JOIN attempts ON attempts.run_id = runs.run_id
                WHERE runs.run_id = ? GROUP BY runs.run_id
                """,
                (run_id,),
            ).fetchone()
        return cast(sqlite3.Row | None, row)

    def list_attempts(self, run_id: str, limit: int = 200, offset: int = 0) -> list[sqlite3.Row]:
        with self._lock:
            rows = self.connection.execute(
                """
                SELECT
                    id, run_id, timestamp, attempt, response,
                    stdout, stderr, result_classification,
                    returncode, duration_ms
                FROM attempts WHERE run_id = ? ORDER BY id DESC LIMIT ? OFFSET ?
                """,
                (run_id, limit, offset),
            ).fetchall()
        return list(rows)
