"""Local web UI and API for GAPBF."""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import time
from collections import deque
from pathlib import Path
from threading import Lock, Thread
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from rich.console import Console

from .Config import Config, valid_nodes_for_grid
from .Database import RunDatabase, detect_device_id, utc_now_iso
from .Logging import setup_logging
from .Output import Output
from .PathFinder import PathFinder
from .PathHandler import ADBHandler, PathHandler, PrintHandler, TestHandler

logger = logging.getLogger("gapbf.web")

ALLOWED_MODES = {"a", "p", "t"}
ATTEMPT_EVENTS = {
    "adb_skip",
    "adb_timeout",
    "adb_error",
    "adb_success",
    "adb_failure",
    "adb_unexpected",
    "test_success",
    "test_failure",
    "print_path",
}


class UserRequestedStop(Exception):
    """Raised when the operator requests a graceful stop."""


class LoadConfigRequest(BaseModel):
    path: str = Field(default="config.yaml", min_length=1)


class ValidateConfigRequest(BaseModel):
    config: dict[str, Any]


class StartRunRequest(BaseModel):
    mode: str = Field(default="a", min_length=1)
    config: dict[str, Any]


def _validate_mode(mode: str) -> str:
    if not mode or not set(mode).issubset(ALLOWED_MODES):
        allowed = "".join(sorted(ALLOWED_MODES))
        raise ValueError(f"Invalid mode: {mode}. Allowed values are combinations of {allowed}.")
    return mode


def _serialize_resume_info(resume_info: Any) -> dict[str, Any] | None:
    if resume_info is None:
        return None
    return {
        "attempted_count": resume_info.attempted_count,
        "latest_run_id": resume_info.latest_run_id,
        "latest_started_at": resume_info.latest_started_at,
        "latest_finished_at": resume_info.latest_finished_at,
        "latest_status": resume_info.latest_status,
        "latest_successful_attempt": resume_info.latest_successful_attempt,
    }


def _serialize_attempt_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "timestamp": row["timestamp"],
        "attempt": row["attempt"],
        "response": row["response"],
        "result_classification": row["result_classification"],
        "returncode": row["returncode"],
        "duration_ms": row["duration_ms"],
    }


def _serialize_run_row(row: Any) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "status": row["status"],
        "mode": row["mode"],
        "device_id": row["device_id"],
        "successful_attempt": row["successful_attempt"],
        "attempt_count": row["attempt_count"],
    }


def _config_meta(grid_size: int) -> dict[str, Any]:
    nodes = valid_nodes_for_grid(grid_size)
    return {
        "grid_size": grid_size,
        "nodes": nodes,
        "node_count": len(nodes),
        "min_path_length": 1,
        "default_path_min_length": min(4, len(nodes)),
        "max_path_length": len(nodes),
        "default_path_max_length": len(nodes),
        "default_attempt_delay": 10.1,
        "default_adb_timeout": 30,
        "path_max_node_distance_note": "Stored in config but not enforced by PathFinder yet.",
    }


def _serialize_config(config: Config) -> dict[str, Any]:
    payload = config.model_dump()
    payload["config_file_path"] = config.config_file_path
    return payload


def _config_from_payload(config_data: dict[str, Any]) -> Config:
    normalized = dict(config_data)
    normalized.setdefault("grid_size", 3)
    normalized.setdefault("path_min_length", 4)
    normalized.setdefault("path_max_length", normalized["grid_size"] ** 2)
    normalized.setdefault("path_max_node_distance", 1)
    normalized.setdefault("path_prefix", [])
    normalized.setdefault("path_suffix", [])
    normalized.setdefault("excluded_nodes", [])
    normalized.setdefault("attempt_delay", 0.0)
    normalized.setdefault("test_path", [])
    normalized.setdefault("stdout_normal", "")
    normalized.setdefault("stdout_success", "")
    normalized.setdefault("stdout_error", "")
    normalized.setdefault("db_path", "~/.gapbf/gapbf.db")
    normalized.setdefault("adb_timeout", 30)
    normalized.setdefault("total_paths", 0)
    normalized.setdefault("echo_commands", True)
    normalized.setdefault("config_file_path", normalized.get("config_file_path", "web-ui"))
    return Config(**normalized)


class WebRunController:
    """Manage one live run for the local web UI."""

    def __init__(self, default_config_path: str):
        self.default_config_path = default_config_path
        self._lock = Lock()
        self._subscribers: list[queue.Queue[dict[str, Any]]] = []
        self._log_tail: deque[dict[str, Any]] = deque(maxlen=250)
        self._database: RunDatabase | None = None
        self._thread: Thread | None = None
        self._run_id: str | None = None
        self._state: dict[str, Any] = {
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
            return {
                **self._state,
                "log_tail": list(self._log_tail),
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

    def load_config(self, path: str) -> dict[str, Any]:
        config = Config.load_config(path)
        return {
            "config": _serialize_config(config),
            "meta": _config_meta(config.grid_size),
        }

    def validate_config(self, config_data: dict[str, Any]) -> dict[str, Any]:
        try:
            config = _config_from_payload(config_data)
        except Exception as error:
            return {"valid": False, "errors": [str(error)]}
        return {
            "valid": True,
            "errors": [],
            "config": _serialize_config(config),
            "meta": _config_meta(config.grid_size),
        }

    def list_recent_runs(self, db_path: str, limit: int = 20) -> list[dict[str, Any]]:
        database = RunDatabase(db_path)
        try:
            return [_serialize_run_row(row) for row in database.list_runs(limit=limit)]
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
                _serialize_attempt_row(row)
                for row in database.list_attempts(target_run_id, limit=limit, offset=offset)
            ]
        finally:
            database.close()

    def start(self, config_data: dict[str, Any], mode: str) -> dict[str, Any]:
        validated_mode = _validate_mode(mode)
        config = _config_from_payload(config_data)
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise ValueError("A run is already active")
            self._log_tail.clear()
            self._state.update(
                {
                    "active": True,
                    "status": "preparing",
                    "mode": validated_mode,
                    "config": _serialize_config(config),
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
            path_finder = PathFinder(
                config.grid_size,
                config.path_min_length,
                config.path_max_length,
                config.path_max_node_distance,
                config.path_prefix,
                config.path_suffix,
                config.excluded_nodes,
            )

            run_id: str | None = None
            device_id: str | None = None
            if "a" in validated_mode:
                self._database = RunDatabase(config.db_path)
                device_id = detect_device_id(config.adb_timeout)
                resume_info = self._database.get_resume_info(config, device_id)
                run_info = self._database.create_run(config, device_id, validated_mode)
                run_id = run_info.run_id
                with self._lock:
                    self._state["device_id"] = device_id
                    self._state["resume_info"] = _serialize_resume_info(resume_info)
                    self._state["paths_tested"] = resume_info.attempted_count
                    self._state["run_id"] = run_id
                    self._run_id = run_id
            else:
                with self._lock:
                    self._run_id = None

            output = Output(console=Console(), silent=True, event_sink=self._handle_output_event)
            for handler in self._build_handlers(path_finder, config, validated_mode, output):
                path_finder.add_handler(handler)

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
                target=self._run_search,
                args=(path_finder, config, validated_mode, run_id),
                name="gapbf-web-run",
                daemon=True,
            )
            self._thread.start()
            return self.snapshot()
        except Exception as error:
            if self._database is not None:
                self._database.close()
                self._database = None
            with self._lock:
                self._run_id = None
                self._state["active"] = False
                self._state["status"] = "error"
                self._state["finished_at"] = utc_now_iso()
                self._state["error_message"] = str(error)
                self._state["last_feedback"] = str(error)
            self._publish("snapshot", self.snapshot())
            raise

    def pause(self) -> dict[str, Any]:
        with self._lock:
            if not self._state["active"]:
                raise ValueError("No active run to pause")
            self._state["paused"] = True
            self._state["status"] = "paused"
            self._state["last_feedback"] = "Run paused"
        self._publish("snapshot", self.snapshot())
        return self.snapshot()

    def resume(self) -> dict[str, Any]:
        with self._lock:
            if not self._state["active"]:
                raise ValueError("No active run to resume")
            self._state["paused"] = False
            self._state["status"] = "running"
            self._state["last_feedback"] = "Run resumed"
        self._publish("snapshot", self.snapshot())
        return self.snapshot()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if not self._state["active"]:
                raise ValueError("No active run to stop")
            self._state["stop_requested"] = True
            self._state["status"] = "stopping"
            self._state["last_feedback"] = "Stop requested. Waiting for the current attempt"
        self._publish("snapshot", self.snapshot())
        return self.snapshot()

    def _publish(self, event: str, payload: dict[str, Any]) -> None:
        stale: list[queue.Queue[dict[str, Any]]] = []
        message = {"event": event, "data": payload}
        with self._lock:
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(message)
            except queue.Full:
                stale.append(subscriber)
        if stale:
            with self._lock:
                self._subscribers = [item for item in self._subscribers if item not in stale]

    def _watch_total_paths(self, total_future: Any) -> None:
        try:
            total_paths = total_future.result()
        except Exception as error:
            with self._lock:
                self._state["total_paths_state"] = "error"
                self._state["last_feedback"] = f"Total-path calculation failed: {error}"
            self._publish("snapshot", self.snapshot())
            return
        with self._lock:
            self._state["total_paths"] = total_paths
            self._state["total_paths_state"] = "ready"
            if self._state["last_feedback"] == "Preparing run":
                self._state["last_feedback"] = "Exact total path count is ready"
        self._publish("snapshot", self.snapshot())

    def _build_handlers(
        self, path_finder: PathFinder, config: Config, mode: str, output: Output
    ) -> list[PathHandler]:
        handlers: list[PathHandler] = []
        for mode_key in mode:
            if mode_key == "p":
                handlers.append(PrintHandler(config, path_finder.grid_nodes, output))
            elif mode_key == "t":
                handlers.append(TestHandler(config, output))
            elif mode_key == "a":
                device_id = self.snapshot()["device_id"]
                if self._database is None or self._run_id is None or device_id is None:
                    raise ValueError("ADB mode requires an initialized device and database")
                handlers.append(
                    ADBHandler(
                        config,
                        database=self._database,
                        run_id=self._run_id,
                        device_id=str(device_id),
                        output=output,
                    )
                )
        return handlers

    def _handle_output_event(self, event_type: str, payload: dict[str, Any]) -> None:
        snapshot_required = False
        with self._lock:
            message = payload.get("message")
            if isinstance(message, str) and message:
                self._state["last_feedback"] = message
                snapshot_required = True
            path = payload.get("path")
            if isinstance(path, list):
                self._state["current_path"] = "".join(str(item) for item in path)
                snapshot_required = True

        if event_type in ATTEMPT_EVENTS:
            log_entry = self._build_log_entry(event_type, payload)
            with self._lock:
                self._log_tail.appendleft(log_entry)
            self._publish("attempt", log_entry)
            snapshot_required = True

        if snapshot_required:
            self._publish("snapshot", self.snapshot())

    def _build_log_entry(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        if (
            event_type.startswith("adb_")
            and self._database is not None
            and self._run_id is not None
        ):
            rows = self._database.list_attempts(self._run_id, limit=1, offset=0)
            if rows:
                return _serialize_attempt_row(rows[0])
        path = payload.get("path")
        attempt = "".join(str(item) for item in path) if isinstance(path, list) else ""
        response = str(payload.get("message", ""))
        if event_type == "print_path":
            response = "Printed path"
        return {
            "id": None,
            "run_id": self._run_id,
            "timestamp": utc_now_iso(),
            "attempt": attempt,
            "response": response,
            "result_classification": event_type,
            "returncode": None,
            "duration_ms": 0.0,
        }

    def _run_search(
        self, path_finder: PathFinder, config: Config, mode: str, run_id: str | None
    ) -> None:
        with self._lock:
            self._state["status"] = "running"
            self._state["last_feedback"] = "Running"
        self._publish("snapshot", self.snapshot())

        try:
            for path in path_finder:
                while True:
                    with self._lock:
                        stop_requested = bool(self._state["stop_requested"])
                        paused = bool(self._state["paused"])
                    if stop_requested:
                        raise UserRequestedStop()
                    if not paused:
                        break
                    time.sleep(0.05)

                with self._lock:
                    self._state["current_path"] = "".join(path)
                total_paths = self.snapshot()["total_paths"]
                success, result_path = path_finder.process_path(path, total_paths)
                with self._lock:
                    self._state["paths_tested"] += 1
                    self._state["current_path"] = "".join(path)
                self._publish("snapshot", self.snapshot())

                if success:
                    resolved_path = "".join(result_path or path)
                    if self._database is not None and run_id is not None:
                        self._database.finish_run(run_id, "success", resolved_path)
                    with self._lock:
                        self._state["active"] = False
                        self._state["status"] = "success"
                        self._state["finished_at"] = utc_now_iso()
                        self._state["successful_path"] = resolved_path
                        self._state["last_feedback"] = f"Pattern found: {resolved_path}"
                    self._publish("snapshot", self.snapshot())
                    return

            if self._database is not None and run_id is not None:
                self._database.finish_run(run_id, "completed")
            with self._lock:
                self._state["active"] = False
                self._state["status"] = "completed"
                self._state["finished_at"] = utc_now_iso()
                self._state["last_feedback"] = (
                    "Search completed without finding a successful pattern"
                )
            self._publish("snapshot", self.snapshot())
        except UserRequestedStop:
            if self._database is not None and run_id is not None:
                self._database.finish_run(run_id, "interrupted")
            with self._lock:
                self._state["active"] = False
                self._state["status"] = "interrupted"
                self._state["finished_at"] = utc_now_iso()
                self._state["last_feedback"] = "Search stopped by operator request"
            self._publish("snapshot", self.snapshot())
        except Exception as error:
            logger.exception("Web run failed")
            if self._database is not None and run_id is not None:
                self._database.finish_run(run_id, "error")
            with self._lock:
                self._state["active"] = False
                self._state["status"] = "error"
                self._state["finished_at"] = utc_now_iso()
                self._state["error_message"] = str(error)
                self._state["last_feedback"] = str(error)
            self._publish("snapshot", self.snapshot())
        finally:
            if self._database is not None:
                self._database.close()
                self._database = None


def create_app(default_config_path: str = "config.yaml") -> FastAPI:
    app = FastAPI(title="GAPBF Web UI")
    controller = WebRunController(default_config_path)
    static_dir = Path(__file__).with_name("web_static")

    app.state.controller = controller
    app.mount("/assets", StaticFiles(directory=static_dir), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        snapshot = controller.snapshot()
        return {
            "ok": True,
            "active": snapshot["active"],
            "status": snapshot["status"],
            "default_config_path": snapshot["default_config_path"],
        }

    @app.get("/api/state")
    def state() -> dict[str, Any]:
        return controller.snapshot()

    @app.get("/api/config/meta")
    def config_meta(grid_size: int = Query(3, ge=3, le=6)) -> dict[str, Any]:
        return _config_meta(grid_size)

    @app.post("/api/config/load")
    def load_config(request: LoadConfigRequest) -> dict[str, Any]:
        try:
            return controller.load_config(request.path)
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/config/validate")
    def validate_config(request: ValidateConfigRequest) -> dict[str, Any]:
        result = controller.validate_config(request.config)
        if result["valid"]:
            return result
        raise HTTPException(status_code=400, detail=result["errors"])

    @app.get("/api/runs")
    def recent_runs(
        db_path: str = Query("~/.gapbf/gapbf.db"),
        limit: int = Query(20, ge=1, le=200),
    ) -> dict[str, Any]:
        try:
            runs = controller.list_recent_runs(db_path, limit=limit)
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"runs": runs}

    @app.get("/api/attempts")
    def attempts(
        db_path: str = Query("~/.gapbf/gapbf.db"),
        run_id: str | None = Query(None),
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        try:
            rows = controller.list_attempts(db_path, run_id, limit=limit, offset=offset)
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"attempts": rows}

    @app.post("/api/run/start")
    def start_run(request: StartRunRequest) -> dict[str, Any]:
        try:
            return controller.start(request.config, request.mode)
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/run/pause")
    def pause_run() -> dict[str, Any]:
        try:
            return controller.pause()
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/run/resume")
    def resume_run() -> dict[str, Any]:
        try:
            return controller.resume()
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/run/stop")
    def stop_run() -> dict[str, Any]:
        try:
            return controller.stop()
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/events")
    async def events() -> StreamingResponse:
        subscriber = controller.subscribe()

        async def stream() -> Any:
            try:
                while True:
                    try:
                        message = await asyncio.to_thread(subscriber.get, True, 1.0)
                    except queue.Empty:
                        yield ": keep-alive\n\n"
                        continue
                    yield (
                        f"event: {message['event']}\n"
                        f"data: {json.dumps(message['data'])}\n\n"
                    )
            finally:
                controller.unsubscribe(subscriber)

        return StreamingResponse(stream(), media_type="text/event-stream")

    return app


def serve_web_ui(
    host: str = "127.0.0.1",
    port: int = 8000,
    config_path: str = "config.yaml",
    log_level: str = "error",
    log_file: str | None = None,
) -> None:
    setup_logging(log_level, log_file)
    uvicorn.run(create_app(config_path), host=host, port=port, log_level="warning")