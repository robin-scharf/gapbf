"""Local web UI and API for GAPBF."""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import time
import urllib.error
import urllib.request
import webbrowser
from collections import deque
from pathlib import Path
from threading import Lock, Thread
from typing import Any

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from rich.console import Console

from .Config import Config, valid_nodes_for_grid
from .Database import RunDatabase, utc_now_iso
from .Logging import setup_logging
from .Output import Output
from .runtime import RunSession, UserRequestedStop, execute_path_search, open_run_session

logger = logging.getLogger("gapbf.web")
_WEB_SERVER_LOCK = Lock()
_WEB_SERVER_THREADS: dict[tuple[str, int], Thread] = {}

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


class LoadConfigRequest(BaseModel):
    path: str = Field(default="config.yaml", min_length=1)


class SaveConfigRequest(BaseModel):
    path: str = Field(min_length=1)
    config: dict[str, Any]


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
        "stdout": row["stdout"],
        "stderr": row["stderr"],
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
        "min_path_length": 4,
        "default_path_min_length": 4,
        "max_path_length": len(nodes),
        "default_path_max_length": len(nodes),
        "default_attempt_delay": 10.1,
        "default_adb_timeout": 30,
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
        self._session: RunSession | None = None
        self._thread: Thread | None = None
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

    def save_config(self, path: str, config_data: dict[str, Any]) -> dict[str, Any]:
        config = _config_from_payload({**config_data, "config_file_path": path})
        config_path = Path(path).expanduser()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        serializable = config.model_dump(exclude={"config_file_path"})
        with config_path.open("w", encoding="utf-8") as file_obj:
            yaml.safe_dump(serializable, file_obj, sort_keys=False)
        return {
            "saved_path": str(config_path),
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
            output = Output(console=Console(), silent=True, event_sink=self._handle_output_event)
            session = open_run_session(config, validated_mode, output)
            path_finder = session.path_finder
            with self._lock:
                self._session = session
                self._state["device_id"] = session.device_id
                self._state["resume_info"] = _serialize_resume_info(session.resume_info)
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
                target=self._run_search,
                args=(session,),
                name="gapbf-web-run",
                daemon=True,
            )
            self._thread.start()
            return self.snapshot()
        except Exception as error:
            if self._session is not None:
                self._session.close()
                self._session = None
            with self._lock:
                self._state["active"] = False
                self._state["status"] = "error"
                self._state["finished_at"] = utc_now_iso()
                self._state["error_message"] = str(error)
                self._state["last_feedback"] = str(error)
                self._state["run_id"] = None
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
            and self._session is not None
            and self._session.database is not None
            and self._session.run_id is not None
        ):
            rows = self._session.database.list_attempts(self._session.run_id, limit=1, offset=0)
            if rows:
                return _serialize_attempt_row(rows[0])
        path = payload.get("path")
        attempt = "".join(str(item) for item in path) if isinstance(path, list) else ""
        response = str(payload.get("message", ""))
        if event_type == "print_path":
            response = "Printed path"
        return {
            "id": None,
            "run_id": self._state.get("run_id"),
            "timestamp": utc_now_iso(),
            "attempt": attempt,
            "response": response,
            "result_classification": event_type,
            "returncode": None,
            "duration_ms": 0.0,
        }

    def _run_search(self, session: RunSession) -> None:
        path_finder = session.path_finder
        with self._lock:
            self._state["status"] = "running"
            self._state["last_feedback"] = "Running"
        self._publish("snapshot", self.snapshot())

        try:
            def should_stop() -> bool:
                with self._lock:
                    return bool(self._state["stop_requested"])

            def is_paused() -> bool:
                with self._lock:
                    return bool(self._state["paused"])

            def total_paths_provider() -> int | None:
                total_paths = self.snapshot()["total_paths"]
                if isinstance(total_paths, int) or total_paths is None:
                    return total_paths
                return None

            def on_path_selected(path: list[str]) -> None:
                with self._lock:
                    self._state["current_path"] = "".join(path)

            def on_attempt_completed(
                path: list[str], result_success: bool, result_path: list[str] | None
            ) -> None:
                with self._lock:
                    self._state["paths_tested"] += 1
                    self._state["current_path"] = "".join(path)
                self._publish("snapshot", self.snapshot())

                if result_success:
                    resolved_path = "".join(result_path or path)
                    session.finish("success", resolved_path)
                    with self._lock:
                        self._state["active"] = False
                        self._state["status"] = "success"
                        self._state["finished_at"] = utc_now_iso()
                        self._state["successful_path"] = resolved_path
                        self._state["last_feedback"] = f"Pattern found: {resolved_path}"
                    self._publish("snapshot", self.snapshot())

            success, _resolved_path = execute_path_search(
                path_finder,
                should_stop=should_stop,
                is_paused=is_paused,
                total_paths_provider=total_paths_provider,
                on_path_selected=on_path_selected,
                on_attempt_completed=on_attempt_completed,
            )

            if success:
                return

            session.finish("completed")
            with self._lock:
                self._state["active"] = False
                self._state["status"] = "completed"
                self._state["finished_at"] = utc_now_iso()
                self._state["last_feedback"] = (
                    "Search completed without finding a successful pattern"
                )
            self._publish("snapshot", self.snapshot())
        except UserRequestedStop:
            session.finish("interrupted")
            with self._lock:
                self._state["active"] = False
                self._state["status"] = "interrupted"
                self._state["finished_at"] = utc_now_iso()
                self._state["last_feedback"] = "Search stopped by operator request"
            self._publish("snapshot", self.snapshot())
        except Exception as error:
            logger.exception("Web run failed")
            session.finish("error")
            with self._lock:
                self._state["active"] = False
                self._state["status"] = "error"
                self._state["finished_at"] = utc_now_iso()
                self._state["error_message"] = str(error)
                self._state["last_feedback"] = str(error)
            self._publish("snapshot", self.snapshot())
        finally:
            session.close()
            with self._lock:
                self._session = None


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

    @app.post("/api/config/save")
    def save_config(request: SaveConfigRequest) -> dict[str, Any]:
        try:
            return controller.save_config(request.path, request.config)
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


def _web_ui_health_url(host: str, port: int) -> str:
    return f"http://{host}:{port}/api/health"


def _web_ui_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def _is_web_ui_available(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with urllib.request.urlopen(_web_ui_health_url(host, port), timeout=timeout) as response:
            return bool(response.status == 200)
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False


def ensure_local_web_ui(
    host: str = "127.0.0.1",
    port: int = 8000,
    config_path: str = "config.yaml",
    *,
    open_browser: bool = True,
    wait_timeout: float = 5.0,
) -> str:
    """Ensure a local web UI server is running, then optionally open it."""
    if not _is_web_ui_available(host, port):
        with _WEB_SERVER_LOCK:
            thread = _WEB_SERVER_THREADS.get((host, port))
            if thread is None or not thread.is_alive():
                thread = Thread(
                    target=serve_web_ui,
                    kwargs={
                        "host": host,
                        "port": port,
                        "config_path": config_path,
                        "log_level": "error",
                        "log_file": None,
                    },
                    name=f"gapbf-web-ui-{host}:{port}",
                    daemon=True,
                )
                _WEB_SERVER_THREADS[(host, port)] = thread
                thread.start()

        deadline = time.monotonic() + wait_timeout
        while time.monotonic() < deadline:
            if _is_web_ui_available(host, port):
                break
            time.sleep(0.1)
        else:
            raise RuntimeError(
                "Web UI did not become available at "
                f"{_web_ui_url(host, port)} within {wait_timeout:.1f}s"
            )

    url = _web_ui_url(host, port)
    if open_browser:
        webbrowser.open(url)
    return url