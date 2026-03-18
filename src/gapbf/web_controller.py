from __future__ import annotations

import queue
from collections import deque
from threading import Lock, Thread
from typing import Any

from rich.console import Console

from .Config import Config
from .Database import RunDatabase, utc_now_iso
from .Output import Output
from .runtime import RunSession, open_run_session
from .web_controller_runtime import WebRunControllerRuntimeMixin
from .web_models import (
    config_from_payload,
    config_meta,
    save_config_to_path,
    serialize_attempt_row,
    serialize_config,
    serialize_resume_info,
    serialize_run_row,
    validate_mode,
)


class WebRunController(WebRunControllerRuntimeMixin):
    def __init__(self, default_config_path: str):
        self.default_config_path = default_config_path
        self._lock = Lock()
        self._subscribers: list[queue.Queue[dict[str, Any]]] = []
        self._log_tail: deque[dict[str, Any]] = deque(maxlen=250)
        self._session: RunSession | None = None
        self._thread: Thread | None = None
        self._state = {
            "default_config_path": default_config_path,
            "active": False,
            "status": "idle",
            "mode": "a",
            "config": None,
            "paths_tested": 0,
            "total_paths": None,
            "total_paths_state": "unknown",
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

    def load_config(self, path: str) -> dict[str, Any]:
        config = Config.load_config(path)
        return {"config": serialize_config(config), "meta": config_meta(config.grid_size)}

    def validate_config(self, config_data: dict[str, Any]) -> dict[str, Any]:
        try:
            config = config_from_payload(config_data)
        except Exception as error:
            return {"valid": False, "errors": [str(error)]}
        return {
            "valid": True,
            "errors": [],
            "config": serialize_config(config),
            "meta": config_meta(config.grid_size),
        }

    def save_config(self, path: str, config_data: dict[str, Any]) -> dict[str, Any]:
        return save_config_to_path(path, config_data)

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

    def start(self, config_data: dict[str, Any], mode: str) -> dict[str, Any]:
        validated_mode = validate_mode(mode)
        config = config_from_payload(config_data)
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise ValueError("A run is already active")
            self._log_tail.clear()
            self._state.update(
                {
                    "active": True,
                    "status": "preparing",
                    "mode": validated_mode,
                    "config": serialize_config(config),
                    "paths_tested": 0,
                    "total_paths": config.total_paths if config.total_paths > 0 else None,
                    "total_paths_state": "ready" if config.total_paths > 0 else "counting",
                    "current_path": "",
                    "last_feedback": "Preparing run",
                    "device_id": None,
                    "resume_info": None,
                    "started_at": utc_now_iso(),
                    "finished_at": None,
                    "successful_path": None,
                    "error_message": None,
                    "paused": False,
                    "stop_requested": False,
                    "run_id": None,
                }
            )

        try:
            output = Output(console=Console(), silent=True, event_sink=self._handle_output_event)
            session = open_run_session(config, validated_mode, output)
            path_finder = session.path_finder
            with self._lock:
                self._session = session
                self._state["device_id"] = session.device_id
                self._state["resume_info"] = serialize_resume_info(session.resume_info)
                self._state["paths_tested"] = (
                    session.resume_info.attempted_count if session.resume_info is not None else 0
                )
                self._state["run_id"] = session.run_id

            if config.total_paths <= 0:
                total_future = path_finder.calculate_total_paths_async()
                Thread(
                    target=self._watch_total_paths,
                    args=(total_future,),
                    name="gapbf-web-total-paths",
                    daemon=True,
                ).start()

            self._publish("snapshot", self.snapshot())
            self._thread = Thread(
                target=self._run_search, args=(session,), name="gapbf-web-run", daemon=True
            )
            self._thread.start()
            return self.snapshot()
        except Exception as error:
            if self._session is not None:
                self._session.close()
                self._session = None
            with self._lock:
                self._state.update(
                    {
                        "active": False,
                        "status": "error",
                        "finished_at": utc_now_iso(),
                        "error_message": str(error),
                        "last_feedback": str(error),
                        "run_id": None,
                    }
                )
            self._publish("snapshot", self.snapshot())
            raise

    def pause(self) -> dict[str, Any]:
        with self._lock:
            if not self._state["active"]:
                raise ValueError("No active run to pause")
            self._state.update({"paused": True, "status": "paused", "last_feedback": "Run paused"})
        self._publish("snapshot", self.snapshot())
        return self.snapshot()

    def resume(self) -> dict[str, Any]:
        with self._lock:
            if not self._state["active"]:
                raise ValueError("No active run to resume")
            self._state.update(
                {"paused": False, "status": "running", "last_feedback": "Run resumed"}
            )
        self._publish("snapshot", self.snapshot())
        return self.snapshot()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if not self._state["active"]:
                raise ValueError("No active run to stop")
            self._state.update(
                {
                    "stop_requested": True,
                    "status": "stopping",
                    "last_feedback": "Stop requested. Waiting for the current attempt",
                }
            )
        self._publish("snapshot", self.snapshot())
        return self.snapshot()
