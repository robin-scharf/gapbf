from __future__ import annotations

import json
import queue
import sqlite3
from collections import deque
from threading import Lock
from typing import Any

from .Database import RunDatabase
from .web_models import serialize_attempt_row, serialize_run_row


def controller_initial_state(default_config_path: str) -> dict[str, Any]:
    return {
        "default_config_path": default_config_path,
        "active": False,
        "controllable": False,
        "status": "idle",
        "mode": "a",
        "config": None,
        "paths_tested": 0,
        "total_paths": None,
        "total_paths_state": "unknown",
        "total_paths_elapsed_seconds": 0,
        "total_paths_timeout_seconds": 30,
        "current_path": "",
        "last_feedback": "Ready",
        "device_id": None,
        "resume_info": None,
        "started_at": None,
        "finished_at": None,
        "successful_path": None,
        "error_message": None,
        "paused": False,
        "stop_requested": False,
        "run_id": None,
    }


class WebRunControllerStateMixin:
    def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        raise NotImplementedError

    def _initialize_controller_state(self, default_config_path: str) -> None:
        self.default_config_path = default_config_path
        self._lock = Lock()
        self._subscribers: list[queue.Queue[dict[str, Any]]] = []
        self._log_tail: deque[dict[str, Any]] = deque(maxlen=250)
        self._state = controller_initial_state(default_config_path)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {**self._state, "log_tail": list(self._log_tail)}

    def _state_value(self, key: str) -> Any:
        """Locked single-key read; avoids copying the whole state + log_tail."""
        with self._lock:
            return self._state.get(key)

    def _set_state_value(self, key: str, value: Any) -> None:
        with self._lock:
            self._state[key] = value

    def _resolve_monitor_db_path(self, db_path: str | None, snapshot: dict[str, Any]) -> str:
        if db_path:
            return db_path
        config = snapshot.get("config")
        if isinstance(config, dict) and config.get("db_path"):
            return str(config["db_path"])
        return "~/.gapbf/gapbf.db"

    @staticmethod
    def _monitor_feedback(
        status: str,
        latest_attempt: dict[str, Any] | None,
        successful_attempt: str | None,
    ) -> str:
        if status == "success" and successful_attempt:
            return f"Pattern found: {successful_attempt}"
        if latest_attempt and latest_attempt.get("response"):
            return str(latest_attempt["response"])
        if status == "running":
            return "Monitoring external run"
        return f"Latest run status: {status}"

    def monitored_snapshot(self, db_path: str | None = None) -> dict[str, Any]:
        base_snapshot = self.snapshot()
        if base_snapshot.get("active") and base_snapshot.get("controllable"):
            return base_snapshot

        target_db_path = self._resolve_monitor_db_path(db_path, base_snapshot)
        try:
            database = RunDatabase(target_db_path, read_only=True)
        except sqlite3.OperationalError:
            return base_snapshot
        try:
            rows = database.list_runs(limit=1)
            if not rows:
                return base_snapshot

            latest_run = rows[0]
            run_row = database.get_run(latest_run["run_id"])
            attempts = [
                serialize_attempt_row(row)
                for row in database.list_attempts(latest_run["run_id"], limit=100)
            ]
        finally:
            database.close()

        config_snapshot: dict[str, Any] | None = None
        if run_row is not None:
            raw_config_snapshot = run_row["config_snapshot"]
            if raw_config_snapshot:
                config_snapshot = json.loads(str(raw_config_snapshot))

        total_paths = None
        if isinstance(config_snapshot, dict):
            snapshot_total = config_snapshot.get("total_paths")
            if isinstance(snapshot_total, int) and snapshot_total > 0:
                total_paths = snapshot_total

        latest_attempt = attempts[0] if attempts else None
        return {
            **base_snapshot,
            "active": latest_run["status"] == "running",
            "controllable": False,
            "status": latest_run["status"],
            "mode": latest_run["mode"],
            "config": config_snapshot or base_snapshot.get("config"),
            "paths_tested": int(latest_run["attempt_count"] or 0),
            "total_paths": total_paths,
            "total_paths_state": "ready" if total_paths is not None else "unknown",
            "current_path": (
                latest_attempt["attempt"]
                if latest_attempt is not None
                else (latest_run["successful_attempt"] or "")
            ),
            "last_feedback": self._monitor_feedback(
                str(latest_run["status"]),
                latest_attempt,
                latest_run["successful_attempt"],
            ),
            "device_id": latest_run["device_id"],
            "resume_info": base_snapshot.get("resume_info"),
            "started_at": latest_run["started_at"],
            "finished_at": latest_run["finished_at"],
            "successful_path": latest_run["successful_attempt"],
            "error_message": None,
            "paused": False,
            "stop_requested": False,
            "run_id": latest_run["run_id"],
            "log_tail": attempts,
        }

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        subscriber: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=200)
        with self._lock:
            self._subscribers.append(subscriber)
        self._publish("snapshot", self.snapshot())
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)

    def list_recent_runs(self, db_path: str, limit: int = 20) -> list[dict[str, Any]]:
        try:
            database = RunDatabase(db_path, read_only=True)
        except sqlite3.OperationalError:
            return []
        try:
            return [serialize_run_row(row) for row in database.list_runs(limit=limit)]
        finally:
            database.close()

    def list_attempts(
        self, db_path: str, run_id: str | None, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        target_run_id = run_id or self.snapshot().get("run_id")
        if not target_run_id:
            return []
        try:
            database = RunDatabase(db_path, read_only=True)
        except sqlite3.OperationalError:
            return []
        try:
            return [
                serialize_attempt_row(row)
                for row in database.list_attempts(target_run_id, limit=limit, offset=offset)
            ]
        finally:
            database.close()