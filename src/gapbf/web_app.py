from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from threading import Lock, Thread
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .Logging import setup_logging
from .web_controller import WebRunController
from .web_models import (
    LoadConfigRequest,
    SaveConfigRequest,
    StartRunRequest,
    ValidateConfigRequest,
    config_meta,
)

_WEB_SERVER_LOCK = Lock()
_WEB_SERVER_THREADS: dict[tuple[str, int], Thread] = {}


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
    def config_meta_endpoint(grid_size: int = Query(3, ge=3, le=6)) -> dict[str, Any]:
        return config_meta(grid_size)

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
        db_path: str = Query("~/.gapbf/gapbf.db"), limit: int = Query(20, ge=1, le=200)
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
                    except Exception:
                        yield ": keep-alive\n\n"
                        continue
                    yield f"event: {message['event']}\ndata: {json.dumps(message['data'])}\n\n"
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
