# mypy: disable-error-code=attr-defined
from __future__ import annotations

import logging
import queue
import time
from typing import Any

from .Database import utc_now_iso
from .runtime import RunSession, UserRequestedStop, execute_path_search
from .web_models import serialize_attempt_row

logger = logging.getLogger("gapbf.web")
TOTAL_PATHS_TIMEOUT_SECONDS = 30.0
TOTAL_PATHS_PROGRESS_INTERVAL_SECONDS = 0.5
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


class WebRunControllerRuntimeMixin:
    _lock: Any
    _log_tail: Any
    _session: RunSession | None
    _state: dict[str, Any]
    _subscribers: list[queue.Queue[dict[str, Any]]]

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
        started_at = time.monotonic()
        last_published_elapsed = -1

        while not total_future.done():
            elapsed_seconds = int(time.monotonic() - started_at)
            if elapsed_seconds != last_published_elapsed:
                with self._lock:
                    self._state["total_paths_elapsed_seconds"] = elapsed_seconds
                    if self._state["total_paths_state"] == "counting":
                        self._state["last_feedback"] = (
                            "Counting exact total paths "
                            f"({elapsed_seconds}s / {int(TOTAL_PATHS_TIMEOUT_SECONDS)}s budget)"
                        )
                self._publish("snapshot", self.snapshot())
                last_published_elapsed = elapsed_seconds

            if time.monotonic() - started_at >= TOTAL_PATHS_TIMEOUT_SECONDS:
                with self._lock:
                    self._state["total_paths"] = None
                    self._state["total_paths_state"] = "timeout"
                    self._state["total_paths_elapsed_seconds"] = int(
                        TOTAL_PATHS_TIMEOUT_SECONDS
                    )
                    self._state["last_feedback"] = (
                        "Exact total path count timed out. Falling back to unknown total."
                    )
                self._publish("snapshot", self.snapshot())
                return

            time.sleep(TOTAL_PATHS_PROGRESS_INTERVAL_SECONDS)

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
            self._state["total_paths_elapsed_seconds"] = int(time.monotonic() - started_at)
            if self._state["last_feedback"] == "Preparing run" or self._state[
                "last_feedback"
            ].startswith("Counting exact total paths"):
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
                return serialize_attempt_row(rows[0])
        path = payload.get("path")
        attempt = "".join(str(item) for item in path) if isinstance(path, list) else ""
        response = "Printed path" if event_type == "print_path" else str(payload.get("message", ""))
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
        with self._lock:
            self._state["status"] = "running"
            self._state["last_feedback"] = "Running"
        self._publish("snapshot", self.snapshot())
        try:
            success, _resolved_path = execute_path_search(
                session.path_finder,
                should_stop=lambda: bool(self.snapshot()["stop_requested"]),
                is_paused=lambda: bool(self.snapshot()["paused"]),
                total_paths_provider=lambda: (
                    self.snapshot()["total_paths"]
                    if isinstance(self.snapshot()["total_paths"], int)
                    or self.snapshot()["total_paths"] is None
                    else None
                ),
                on_path_selected=lambda path: self._state.__setitem__(
                    "current_path", "".join(path)
                ),
                on_attempt_completed=lambda path, result_success, result_path: (
                    self._on_attempt_completed(session, path, result_success, result_path)
                ),
            )
            if success:
                return
            session.finish("completed")
            with self._lock:
                self._state.update(
                    {
                        "active": False,
                        "status": "completed",
                        "finished_at": utc_now_iso(),
                        "last_feedback": "Search completed without finding a successful pattern",
                    }
                )
            self._publish("snapshot", self.snapshot())
        except UserRequestedStop:
            session.finish("interrupted")
            with self._lock:
                self._state.update(
                    {
                        "active": False,
                        "status": "interrupted",
                        "finished_at": utc_now_iso(),
                        "last_feedback": "Search stopped by operator request",
                    }
                )
            self._publish("snapshot", self.snapshot())
        except Exception as error:
            logger.exception("Web run failed")
            session.finish("error")
            with self._lock:
                self._state.update(
                    {
                        "active": False,
                        "status": "error",
                        "finished_at": utc_now_iso(),
                        "error_message": str(error),
                        "last_feedback": str(error),
                    }
                )
            self._publish("snapshot", self.snapshot())
        finally:
            session.close()
            with self._lock:
                self._session = None

    def _on_attempt_completed(
        self,
        session: RunSession,
        path: list[str],
        result_success: bool,
        result_path: list[str] | None,
    ) -> None:
        with self._lock:
            self._state["paths_tested"] += 1
            self._state["current_path"] = "".join(path)
        self._publish("snapshot", self.snapshot())
        if result_success:
            resolved_path = "".join(result_path or path)
            session.finish("success", resolved_path)
            with self._lock:
                self._state.update(
                    {
                        "active": False,
                        "status": "success",
                        "finished_at": utc_now_iso(),
                        "successful_path": resolved_path,
                        "last_feedback": f"Pattern found: {resolved_path}",
                    }
                )
            self._publish("snapshot", self.snapshot())
