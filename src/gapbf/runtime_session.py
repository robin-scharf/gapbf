from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Protocol

from .Config import Config
from .Database import ResumeInfo, RunDatabase, stale_run_timeout_seconds
from .Output import Output
from .PathFinder import PathFinder
from .PathHandler import ADBHandler, PathHandler, PrintHandler, TestHandler


class UserRequestedStop(Exception):
    """Raised when the operator asks a run to stop gracefully."""


@dataclass(frozen=True, slots=True)
class ResumeContext:
    device_id: str
    resume_info: ResumeInfo


class RunStateLike(Protocol):
    paths_tested: int

    def attach_device_id(self, device_id: str | None) -> None: ...
    def attach_resume_info(self, resume_info: ResumeInfo | None) -> None: ...


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

    def attach_state(self, state: RunStateLike) -> None:
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
    from . import runtime as runtime_module

    database = runtime_module.RunDatabase(config.db_path)
    try:
        device_id = runtime_module.detect_device_id(config.adb_timeout)
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
    from . import runtime as runtime_module

    path_finder = runtime_module.create_path_finder(config)
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

        runtime_module.add_handlers(
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
