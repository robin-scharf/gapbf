from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, TypedDict

from .PathFinder import PathFinder


class RunStateSnapshot(TypedDict):
    config: Any
    mode: str
    total_paths: int | None
    total_paths_state: str
    paths_tested: int
    current_path: str
    last_feedback: str
    search_status: str
    device_id: str | None
    resume_info: Any
    started_at: float
    successful_path: str | None
    error_message: str | None
    paused: bool
    show_help: bool
    quit_requested: bool
    key_input_enabled: bool


@dataclass(slots=True)
class RunState:
    config: Any
    mode: str
    total_paths: int | None = None
    total_paths_state: str = "unknown"
    paths_tested: int = 0
    current_path: str = "-"
    last_feedback: str = "Waiting to start"
    search_status: str = "Preparing"
    device_id: str | None = None
    resume_info: Any = None
    started_at: float = field(default_factory=time.monotonic)
    successful_path: str | None = None
    error_message: str | None = None
    paused: bool = False
    show_help: bool = False
    quit_requested: bool = False
    key_input_enabled: bool = False
    _lock: Lock = field(default_factory=Lock, repr=False)

    def snapshot(self) -> RunStateSnapshot:
        with self._lock:
            return {
                "config": self.config,
                "mode": self.mode,
                "total_paths": self.total_paths,
                "total_paths_state": self.total_paths_state,
                "paths_tested": self.paths_tested,
                "current_path": self.current_path,
                "last_feedback": self.last_feedback,
                "search_status": self.search_status,
                "device_id": self.device_id,
                "resume_info": self.resume_info,
                "started_at": self.started_at,
                "successful_path": self.successful_path,
                "error_message": self.error_message,
                "paused": self.paused,
                "show_help": self.show_help,
                "quit_requested": self.quit_requested,
                "key_input_enabled": self.key_input_enabled,
            }

    def set_total_paths(self, total_paths: int) -> None:
        with self._lock:
            self.total_paths = total_paths
            self.total_paths_state = "ready"

    def mark_total_paths_counting(self) -> None:
        with self._lock:
            if self.total_paths is None:
                self.total_paths_state = "counting"

    def mark_total_paths_unavailable(self, message: str) -> None:
        with self._lock:
            self.total_paths = None
            self.total_paths_state = "error"
            self.last_feedback = message

    def set_search_status(self, status: str) -> None:
        with self._lock:
            self.search_status = status

    def set_current_path(self, path: list[str] | str) -> None:
        with self._lock:
            self.current_path = "".join(path) if isinstance(path, list) else path

    def record_attempt(self, path: list[str]) -> None:
        with self._lock:
            self.paths_tested += 1
            self.current_path = "".join(path)

    def set_feedback(self, message: str) -> None:
        with self._lock:
            self.last_feedback = message

    def attach_resume_info(self, resume_info: Any) -> None:
        with self._lock:
            self.resume_info = resume_info

    def attach_device_id(self, device_id: str | None) -> None:
        with self._lock:
            self.device_id = device_id

    def mark_success(self, path: list[str] | None) -> None:
        with self._lock:
            self.search_status = "Pattern found"
            self.successful_path = "".join(path) if path else None

    def mark_completed(self) -> None:
        with self._lock:
            if self.search_status != "Pattern found":
                self.search_status = "Completed"

    def mark_interrupted(self) -> None:
        with self._lock:
            self.search_status = "Interrupted"

    def mark_error(self, message: str) -> None:
        with self._lock:
            self.search_status = "Error"
            self.error_message = message
            self.last_feedback = message

    def set_key_input_enabled(self, enabled: bool) -> None:
        with self._lock:
            self.key_input_enabled = enabled

    def toggle_help(self) -> bool:
        with self._lock:
            self.show_help = not self.show_help
            return self.show_help

    def toggle_pause(self) -> bool:
        with self._lock:
            self.paused = not self.paused
            self.search_status = "Paused" if self.paused else "Running"
            return self.paused

    def request_quit(self) -> None:
        with self._lock:
            self.quit_requested = True
            self.search_status = "Stopping"


class RunController:
    def __init__(self, state: RunState):
        self.state = state

    def should_stop(self) -> bool:
        return bool(self.state.snapshot()["quit_requested"])

    def is_paused(self) -> bool:
        return bool(self.state.snapshot()["paused"])

    def total_paths_provider(self) -> int | None:
        return self.state.snapshot()["total_paths"]

    def on_path_selected(self, path: list[str]) -> None:
        self.state.set_current_path(path)

    def on_attempt_completed(
        self, path: list[str], result_success: bool, result_path: list[str] | None
    ) -> None:
        self.state.record_attempt(path)
        if result_success:
            resolved_path = result_path or path
            self.state.mark_success(resolved_path)
            self.state.set_feedback(f"Pattern found: {''.join(resolved_path)}")

    def execute_search(self, path_finder: PathFinder) -> tuple[bool, list[str]]:
        from .runtime_session import execute_path_search

        return execute_path_search(
            path_finder,
            should_stop=self.should_stop,
            is_paused=self.is_paused,
            total_paths_provider=self.total_paths_provider,
            on_path_selected=self.on_path_selected,
            on_attempt_completed=self.on_attempt_completed,
        )
