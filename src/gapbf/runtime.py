"""Shared runtime helpers for GAPBF CLI and web execution."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable, TypedDict

from .Config import Config
from .Database import ResumeInfo, RunDatabase, detect_device_id, stale_run_timeout_seconds
from .Output import Output
from .PathFinder import PathFinder
from .PathHandler import ADBHandler, PathHandler, PrintHandler, TestHandler


class UserRequestedStop(Exception):
    """Raised when the operator asks a run to stop gracefully."""


@dataclass(frozen=True, slots=True)
class ResumeContext:
    device_id: str
    resume_info: ResumeInfo


@dataclass(slots=True)
class RunSession:
    config: Config
    mode: str
    path_finder: PathFinder
    output: Output
    database: RunDatabase | None = None
    run_id: str | None = None
    device_id: str | None = None
    resume_info: ResumeInfo | None = None

    def attach_state(self, state: "RunState") -> None:
        state.attach_device_id(self.device_id)
        state.attach_resume_info(self.resume_info)
        if self.resume_info is not None:
            state.paths_tested = self.resume_info.attempted_count

    def finish(self, status: str, successful_attempt: str | list[str] | None = None) -> None:
        if self.database is None or self.run_id is None:
            return
        resolved_attempt = (
            "".join(successful_attempt)
            if isinstance(successful_attempt, list)
            else successful_attempt
        )
        self.database.finish_run(self.run_id, status, resolved_attempt)

    def close(self) -> None:
        if self.database is None:
            return
        self.database.close()
        self.database = None


def create_path_finder(config: Config) -> PathFinder:
    return PathFinder(
        config.grid_size,
        config.path_min_length,
        config.path_max_length,
        config.path_max_node_distance,
        config.path_prefix,
        config.path_suffix,
        config.excluded_nodes,
    )


def _prepare_persistent_context(
    config: Config,
    mode: str,
    *,
    create_run: bool,
) -> tuple[RunDatabase, str, ResumeInfo, str | None]:
    database = RunDatabase(config.db_path)
    try:
        device_id = detect_device_id(config.adb_timeout)
        database.reconcile_stale_runs(
            device_id,
            config.grid_size,
            stale_after_seconds=stale_run_timeout_seconds(config),
        )
        resume_info = database.get_resume_info(config, device_id)
        run_id = None
        if create_run:
            run_id = database.create_run(config, device_id, mode).run_id
        return database, device_id, resume_info, run_id
    except Exception:
        database.close()
        raise


def load_resume_context(config: Config) -> ResumeContext:
    database, device_id, resume_info, _run_id = _prepare_persistent_context(
        config,
        "a",
        create_run=False,
    )
    try:
        return ResumeContext(device_id=device_id, resume_info=resume_info)
    finally:
        database.close()


def open_run_session(config: Config, mode: str, output: Output) -> RunSession:
    path_finder = create_path_finder(config)
    database: RunDatabase | None = None
    run_id: str | None = None
    device_id: str | None = None
    resume_info: ResumeInfo | None = None

    try:
        if "a" in mode:
            database, device_id, resume_info, run_id = _prepare_persistent_context(
                config,
                mode,
                create_run=True,
            )

        add_handlers(
            path_finder,
            config,
            mode,
            database=database,
            run_id=run_id,
            device_id=device_id,
            output=output,
        )
    except Exception:
        if database is not None:
            database.close()
        raise

    return RunSession(
        config=config,
        mode=mode,
        path_finder=path_finder,
        output=output,
        database=database,
        run_id=run_id,
        device_id=device_id,
        resume_info=resume_info,
    )


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
    """Thread-safe run state used by CLI and shared runtime helpers."""

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
    """Own the shared CLI run-state callbacks for execute_path_search."""

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
        return execute_path_search(
            path_finder,
            should_stop=self.should_stop,
            is_paused=self.is_paused,
            total_paths_provider=self.total_paths_provider,
            on_path_selected=self.on_path_selected,
            on_attempt_completed=self.on_attempt_completed,
        )


def add_handlers(
    path_finder: PathFinder,
    config: Config,
    mode: str,
    *,
    database: RunDatabase | None,
    run_id: str | None,
    device_id: str | None,
    output: Output,
) -> list[PathHandler]:
    """Create and attach handlers for the requested mode string."""
    handlers: list[PathHandler] = []
    for mode_key in mode:
        handler: PathHandler
        if mode_key == "p":
            handler = PrintHandler(config, path_finder.grid_nodes, output)
        elif mode_key == "t":
            handler = TestHandler(config, output)
        elif mode_key == "a":
            if database is None or run_id is None or device_id is None:
                raise RuntimeError("ADB mode requires an initialized run database and device id")
            handler = ADBHandler(
                config,
                database=database,
                run_id=run_id,
                device_id=device_id,
                output=output,
            )
        else:
            raise RuntimeError(f"Unsupported handler mode: {mode_key}")
        path_finder.add_handler(handler)
        handlers.append(handler)
    return handlers


def execute_path_search(
    path_finder: PathFinder,
    *,
    should_stop: Callable[[], bool],
    is_paused: Callable[[], bool],
    total_paths_provider: Callable[[], int | None],
    on_path_selected: Callable[[list[str]], None],
    on_attempt_completed: Callable[[list[str], bool, list[str] | None], None],
    pause_poll_interval: float = 0.05,
) -> tuple[bool, list[str]]:
    """Run the shared path iteration loop for CLI and web modes."""
    for path in path_finder:
        while True:
            if should_stop():
                raise UserRequestedStop()
            if not is_paused():
                break
            time.sleep(pause_poll_interval)

        on_path_selected(path)
        success, result_path = path_finder.process_path(path, total_paths_provider())
        on_attempt_completed(path, success, result_path)

        if success:
            return True, result_path or path

    return False, []