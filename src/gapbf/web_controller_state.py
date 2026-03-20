from __future__ import annotations

import queue
from collections import deque
from threading import Lock
from typing import Any

from .Database import RunDatabase
from .web_models import serialize_attempt_row, serialize_run_row


def controller_initial_state(default_config_path: str) -> dict[str, Any]:
    return {
        "default_config_path": default_config_path,
        "active": False,
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
        database = RunDatabase(db_path)
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
        database = RunDatabase(db_path)
        try:
            return [
                serialize_attempt_row(row)
                for row in database.list_attempts(target_run_id, limit=limit, offset=offset)
            ]
        finally:
            database.close()