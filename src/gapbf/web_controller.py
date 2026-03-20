from __future__ import annotations

from threading import Thread
from typing import Any

from rich.console import Console

from .Database import utc_now_iso
from .Output import Output
from .runtime import RunSession, open_run_session
from .web_controller_config import WebRunControllerConfigMixin
from .web_controller_runtime import WebRunControllerRuntimeMixin
from .web_controller_state import WebRunControllerStateMixin
from .web_models import (
    config_from_payload,
    serialize_config,
    serialize_resume_info,
    validate_mode,
)


class WebRunController(
    WebRunControllerRuntimeMixin,
    WebRunControllerStateMixin,
    WebRunControllerConfigMixin,
):
    def __init__(self, default_config_path: str):
        self._session: RunSession | None = None
        self._thread: Thread | None = None
        self._initialize_controller_state(default_config_path)

    def calculate_total_paths(self, config_data: dict[str, Any]) -> dict[str, Any]:
        config = config_from_payload(config_data)
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise ValueError("Cannot calculate total paths while a run is active")

            self._state.update(
                {
                    "config": serialize_config(config),
                    "total_paths": None,
                    "total_paths_state": "counting",
                    "total_paths_elapsed_seconds": 0,
                    "total_paths_timeout_seconds": 30,
                    "last_feedback": "Counting exact total paths",
                    "error_message": None,
                }
            )
        self._publish("snapshot", self.snapshot())

        from time import monotonic

        from .runtime import create_path_finder

        started_at = monotonic()
        try:
            total_paths = create_path_finder(config).total_paths
        except Exception as error:
            with self._lock:
                self._state.update(
                    {
                        "total_paths": None,
                        "total_paths_state": "error",
                        "total_paths_elapsed_seconds": int(monotonic() - started_at),
                        "error_message": str(error),
                        "last_feedback": f"Total-path calculation failed: {error}",
                    }
                )
            self._publish("snapshot", self.snapshot())
            raise

        with self._lock:
            self._state.update(
                {
                    "config": serialize_config(
                        config.model_copy(update={"total_paths": total_paths})
                    ),
                    "total_paths": total_paths,
                    "total_paths_state": "ready",
                    "total_paths_elapsed_seconds": int(monotonic() - started_at),
                    "error_message": None,
                    "last_feedback": "Exact total path count is ready",
                }
            )
        self._publish("snapshot", self.snapshot())
        return self.snapshot()

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
                    "total_paths_elapsed_seconds": 0,
                    "total_paths_timeout_seconds": 30,
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

            if "a" in validated_mode and session.known_successful_attempt is not None:
                session.finish("success", session.known_successful_attempt)
                with self._lock:
                    self._state.update(
                        {
                            "active": False,
                            "status": "success",
                            "finished_at": utc_now_iso(),
                            "successful_path": session.known_successful_attempt,
                            "last_feedback": "Pattern already known from prior device history",
                        }
                    )
                self._publish("snapshot", self.snapshot())
                return self.snapshot()

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
