# mypy: disable-error-code=attr-defined
from __future__ import annotations

import json


class DatabaseSchemaMixin:
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
        if column_name not in existing_columns:
            self.connection.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
            )

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
            self.connection.execute(
                """
                UPDATE runs SET updated_at = ?, grid_size = ? WHERE run_id = ?
                """,
                (
                    row["updated_at"] or row["started_at"],
                    int(snapshot.get("grid_size", 3)),
                    row["run_id"],
                ),
            )

    def _backfill_attempt_metadata(self) -> None:
        rows = self.connection.execute(
            """
            SELECT attempts.id, attempts.run_id, attempts.device_id, attempts.grid_size
            FROM attempts
            WHERE attempts.device_id = '' OR attempts.device_id IS NULL
                OR attempts.grid_size IS NULL
            """
        ).fetchall()
        for row in rows:
            run_row = self.connection.execute(
                "SELECT device_id, grid_size FROM runs WHERE run_id = ?",
                (row["run_id"],),
            ).fetchone()
            if run_row is not None:
                self.connection.execute(
                    "UPDATE attempts SET device_id = ?, grid_size = ? WHERE id = ?",
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
                (
                    "DELETE FROM attempts WHERE device_id = ? AND grid_size = ? "
                    "AND attempt = ? AND id <> ?"
                ),
                (row["device_id"], row["grid_size"], row["attempt"], row["keep_id"]),
            )
