import logging
import os
import select
import sys
import termios
import time
import tty
from concurrent.futures import Future
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from itertools import islice
from threading import Lock, Thread
from typing import Any, Callable, TypedDict, TypeVar

import typer
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .Config import Config
from .Database import ResumeInfo, RunDatabase, detect_device_id
from .Logging import setup_logging
from .Output import Output
from .PathFinder import PathFinder
from .PathHandler import ADBHandler, PathHandler, PrintHandler, TestHandler

ResultT = TypeVar("ResultT")


class HandlerSpec(TypedDict):
    class_: type[PathHandler]
    help: str


class LiveRunSnapshot(TypedDict):
    config: Config
    mode: str
    total_paths: int | None
    total_paths_state: str
    paths_tested: int
    current_path: str
    last_feedback: str
    search_status: str
    device_id: str | None
    resume_info: ResumeInfo | None
    started_at: float
    successful_path: str | None
    error_message: str | None
    paused: bool
    show_help: bool
    quit_requested: bool
    key_input_enabled: bool


app = typer.Typer(
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=True,
)
console = Console()
output = Output(console)


handler_classes: dict[str, HandlerSpec] = {
    "a": {"class_": ADBHandler, "help": "Attempt decryption via ADB shell on Android device"},
    "p": {"class_": PrintHandler, "help": "Print attempted paths to the console"},
    "t": {"class_": TestHandler, "help": "Run mock brute force against test_path in config"},
}

SPINNER_FRAMES = "|/-\\"


class UserRequestedStop(Exception):
    """Raised when the operator asks the live run to stop."""


class TerminalKeyReader(AbstractContextManager["TerminalKeyReader"]):
    """Best-effort single-key reader for TTY-backed Linux terminals."""

    def __init__(self) -> None:
        self._stream = sys.stdin
        self._fd: int | None = None
        self._old_settings: list | None = None
        self.enabled = False

    def __enter__(self) -> "TerminalKeyReader":
        if not self._stream.isatty():
            return self

        try:
            self._fd = self._stream.fileno()
            self._old_settings = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
            self.enabled = True
        except Exception:
            self.enabled = False
            self._fd = None
            self._old_settings = None
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> None:
        if self.enabled and self._fd is not None and self._old_settings is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_settings)
        self.enabled = False
        self._fd = None
        self._old_settings = None

    def read_key(self) -> str | None:
        if not self.enabled or self._fd is None:
            return None
        readable, _, _ = select.select([self._stream], [], [], 0)
        if not readable:
            return None
        try:
            return os.read(self._fd, 1).decode("utf-8", errors="ignore") or None
        except Exception:
            return None


@dataclass(slots=True)
class LiveRunState:
    config: Config
    mode: str
    total_paths: int | None = None
    total_paths_state: str = "unknown"
    paths_tested: int = 0
    current_path: str = "-"
    last_feedback: str = "Waiting to start"
    search_status: str = "Preparing"
    device_id: str | None = None
    resume_info: ResumeInfo | None = None
    started_at: float = field(default_factory=time.monotonic)
    successful_path: str | None = None
    error_message: str | None = None
    paused: bool = False
    show_help: bool = False
    quit_requested: bool = False
    key_input_enabled: bool = False
    _lock: Lock = field(default_factory=Lock, repr=False)

    def snapshot(self) -> LiveRunSnapshot:
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

    def attach_resume_info(self, resume_info: ResumeInfo | None) -> None:
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


def _run_in_background(
    callback: Callable[..., ResultT], *args: Any, **kwargs: Any
) -> Future[ResultT]:
    future: Future[ResultT] = Future()

    def runner() -> None:
        if not future.set_running_or_notify_cancel():
            return
        try:
            future.set_result(callback(*args, **kwargs))
        except BaseException as error:
            future.set_exception(error)

    Thread(target=runner, daemon=True).start()
    return future


def _mode_label(mode: str) -> str:
    return ", ".join([handler_classes[item]["class_"].__name__ for item in mode])


def _format_path_constraints(values: list[str]) -> str:
    return "".join(values) if values else "None"


def _format_progress(paths_tested: int, total_paths: int | None) -> str:
    if total_paths is None:
        return f"{paths_tested:,} / Unknown"
    if total_paths == 0:
        return f"{paths_tested:,} / 0"
    percentage = paths_tested / total_paths * 100
    return f"{paths_tested:,} / {total_paths:,} ({percentage:.4f}%)"


def _format_elapsed(elapsed_seconds: float) -> str:
    hours, remainder = divmod(int(elapsed_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _format_total_paths_state(total_paths: int | None, total_paths_state: str) -> str:
    if total_paths is not None:
        return f"{total_paths:,}"
    if total_paths_state == "counting":
        frame = SPINNER_FRAMES[int(time.monotonic() * 8) % len(SPINNER_FRAMES)]
        return f"{frame} Counting exact total in background"
    if total_paths_state == "error":
        return "Unavailable"
    return "Unknown"


def _control_hint(allow_pause: bool, key_input_enabled: bool) -> str:
    if not key_input_enabled:
        return "Interactive controls unavailable in this terminal. Ctrl+C still stops the run."
    if allow_pause:
        return "Keys: p pause/resume, q quit after current attempt, h help, Ctrl+C hard stop"
    return "Keys: q close view, h help"


def _control_help(allow_pause: bool) -> list[str]:
    if allow_pause:
        return [
            "p: pause or resume between attempts",
            "q: stop the run after the current in-flight attempt",
            "h: toggle this help",
            "Ctrl+C: interrupt immediately",
        ]
    return [
        "q: close the status view",
        "h: toggle this help",
    ]


def _handle_live_keypress(state: LiveRunState, key: str, *, allow_pause: bool) -> bool:
    normalized = key.lower()
    if normalized in {"h", "?"}:
        help_visible = state.toggle_help()
        state.set_feedback("Controls help shown" if help_visible else "Controls help hidden")
        return False

    if normalized == "q":
        state.request_quit()
        if allow_pause:
            state.set_feedback("Stop requested. Waiting for the current attempt to finish")
            return False
        state.set_feedback("Status view closed by user")
        return True

    if allow_pause and normalized == "p":
        paused = state.toggle_pause()
        state.set_feedback("Run paused" if paused else "Run resumed")
        return False

    return False


def _render_live_dashboard(state: LiveRunState, title: str, *, allow_pause: bool) -> Panel:
    snapshot = state.snapshot()
    config = snapshot["config"]
    resume_info = snapshot["resume_info"]

    table = Table(title=title, show_header=False)
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("Search", str(snapshot["search_status"]))
    table.add_row(
        "Progress",
        _format_progress(snapshot["paths_tested"], snapshot["total_paths"]),
    )
    table.add_row(
        "Total paths",
        _format_total_paths_state(snapshot["total_paths"], snapshot["total_paths_state"]),
    )
    table.add_row("Current path", str(snapshot["current_path"]))
    table.add_row("Last feedback", str(snapshot["last_feedback"]))
    table.add_row("Elapsed", _format_elapsed(time.monotonic() - snapshot["started_at"]))
    table.add_row("Grid", f"{config.grid_size}x{config.grid_size}")
    table.add_row("Path length", f"{config.path_min_length} to {config.path_max_length}")
    table.add_row("Prefix", _format_path_constraints(config.path_prefix))
    table.add_row("Suffix", _format_path_constraints(config.path_suffix))
    table.add_row("Excluded", _format_path_constraints(config.excluded_nodes))
    table.add_row("Handlers", _mode_label(str(snapshot["mode"])))
    table.add_row("Device", str(snapshot["device_id"] or "None"))
    if resume_info is not None:
        table.add_row("Resumable attempts", f"{resume_info.attempted_count:,}")
        table.add_row("Latest run status", str(resume_info.latest_status or "None"))
        table.add_row("Latest success", str(resume_info.latest_successful_attempt or "None"))
    if snapshot["successful_path"]:
        table.add_row("Successful path", str(snapshot["successful_path"]))
    if snapshot["error_message"]:
        table.add_row("Error", str(snapshot["error_message"]))
    if snapshot["show_help"]:
        table.add_row("Controls", "\n".join(_control_help(allow_pause)))

    footer = Text(
        _control_hint(allow_pause, bool(snapshot["key_input_enabled"])),
        style="dim",
    )
    return Panel.fit(table, subtitle=footer)


def _sync_live_total_paths(state: LiveRunState, total_paths_future: Future[int] | None) -> None:
    if total_paths_future is None or not total_paths_future.done():
        return
    snapshot = state.snapshot()
    if snapshot["total_paths"] is not None or snapshot["total_paths_state"] == "error":
        return
    try:
        state.set_total_paths(total_paths_future.result())
        state.set_feedback("Exact total path count is ready")
    except Exception as error:
        state.mark_total_paths_unavailable(f"Total-path calculation failed: {error}")


def _should_auto_count_status_totals() -> bool:
    return sys.stdin.isatty()


def _drive_live_dashboard(
    state: LiveRunState,
    title: str,
    total_paths_future: Future[int] | None,
    *,
    allow_pause: bool,
    done_callback: Callable[[], bool],
) -> bool:
    with TerminalKeyReader() as key_reader:
        state.set_key_input_enabled(key_reader.enabled)
        with Live(
            _render_live_dashboard(state, title, allow_pause=allow_pause),
            console=console,
            refresh_per_second=8,
            transient=True,
        ) as live:
            while not done_callback():
                _sync_live_total_paths(state, total_paths_future)
                key = key_reader.read_key()
                if key is not None and _handle_live_keypress(state, key, allow_pause=allow_pause):
                    live.update(_render_live_dashboard(state, title, allow_pause=allow_pause))
                    return True
                live.update(_render_live_dashboard(state, title, allow_pause=allow_pause))
                time.sleep(0.1)
            _sync_live_total_paths(state, total_paths_future)
            live.update(_render_live_dashboard(state, title, allow_pause=allow_pause))
    return False


def validate_mode(value):
    valid_modes = "".join(handler_classes.keys())
    if not set(value).issubset(set(valid_modes)):
        available_options = ", ".join(valid_modes)
        raise typer.BadParameter(
            f"Invalid mode: {value}. Allowed values are combinations of {available_options}."
        )
    return value


def _generate_sample_paths(path_finder, limit=10):
    """Generate a limited number of sample paths for dry-run mode.

    Args:
        path_finder: PathFinder instance
        limit: Maximum number of paths to generate

    Yields:
        Path lists
    """
    yield from islice(path_finder, limit)


def _load_config(config_path: str, logger: logging.Logger) -> Config:
    try:
        config = Config.load_config(config_path)
        logger.info(f"Loaded configuration from {config_path}")
        return config
    except Exception as error:
        logger.error(f"Failed to load configuration: {error}")
        raise typer.Exit(code=1) from error


def _build_path_finder(config: Config, logger: logging.Logger) -> PathFinder:
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
        logger.info("Initialized PathFinder")
        return path_finder
    except Exception as error:
        logger.error(f"Failed to initialize PathFinder: {error}")
        raise typer.Exit(code=1) from error


def _resolve_total_paths(
    config: Config,
    path_finder: PathFinder,
    logger: logging.Logger,
    *,
    calculate: bool,
) -> int | None:
    if config.total_paths > 0 and not calculate:
        logger.info(f"Using configured total_paths={config.total_paths}")
        return config.total_paths

    if not calculate:
        logger.info("Skipping expensive total_paths calculation")
        return None

    total_paths = path_finder.total_paths
    logger.info(f"Calculated total_paths={total_paths}")
    return total_paths


def _format_total_paths(total_paths: int | None) -> str:
    return f"{total_paths:,}" if total_paths is not None else "Unknown"


def _print_dry_run_summary(
    config: Config, total_paths: int | None, path_finder: PathFinder
) -> None:
    summary = Table(title="Dry Run", show_header=False)
    summary.add_column("Field", style="cyan")
    summary.add_column("Value")
    summary.add_row("Total paths", _format_total_paths(total_paths))
    summary.add_row("Grid", f"{config.grid_size}x{config.grid_size}")
    summary.add_row("Length", f"{config.path_min_length} to {config.path_max_length}")
    summary.add_row("Prefix", str(config.path_prefix or "None"))
    summary.add_row("Suffix", str(config.path_suffix or "None"))
    summary.add_row(
        "Excluded", str(list(config.excluded_nodes) if config.excluded_nodes else "None")
    )
    console.print(summary)

    sample_table = Table(title="First Paths")
    sample_table.add_column("#", justify="right")
    sample_table.add_column("Path")
    for count, path in enumerate(_generate_sample_paths(path_finder, 10), start=1):
        sample_table.add_row(str(count), "".join(path))
    console.print(sample_table)


def _print_resume_summary(resume_info: ResumeInfo) -> None:
    output.show_resume(
        resume_info.attempted_count,
        status=resume_info.latest_status,
        started_at=resume_info.latest_started_at,
    )


def _add_handlers(
    path_finder: PathFinder,
    config: Config,
    mode: str,
    logger: logging.Logger,
    database: RunDatabase | None,
    run_id: str | None,
    device_id: str | None,
    output_adapter: Output,
) -> None:
    for mode_key in mode:
        handler_class = handler_classes[mode_key]["class_"]
        handler: PathHandler
        try:
            if handler_class is PrintHandler:
                handler = PrintHandler(config, path_finder.grid_nodes, output_adapter)
            elif handler_class is ADBHandler:
                if database is None or run_id is None or device_id is None:
                    raise RuntimeError(
                        "ADB mode requires an initialized run database and device id"
                    )
                handler = ADBHandler(
                    config,
                    database=database,
                    run_id=run_id,
                    device_id=device_id,
                    output=output_adapter,
                )
            elif handler_class is TestHandler:
                handler = TestHandler(config, output_adapter)
            else:
                raise RuntimeError(f"Unsupported handler class: {handler_class.__name__}")
            path_finder.add_handler(handler)
            logger.info(f"Added handler: {handler_class.__name__}")
        except Exception as error:
            logger.error(f"Failed to initialize {handler_class.__name__}: {error}")
            raise typer.Exit(code=1) from error


def _print_run_summary(
    config: Config,
    mode: str,
    total_paths: int | None,
    resume_info: ResumeInfo | None = None,
    device_id: str | None = None,
) -> None:
    handler_names = _mode_label(mode)
    summary = Table(title="GAPBF Run Summary", show_header=False)
    summary.add_column("Field", style="cyan")
    summary.add_column("Value")
    summary.add_row("Grid", f"{config.grid_size}x{config.grid_size}")
    summary.add_row("Path length", f"{config.path_min_length} to {config.path_max_length}")
    summary.add_row("Prefix", str(config.path_prefix or "None"))
    summary.add_row("Suffix", str(config.path_suffix or "None"))
    summary.add_row("Excluded", str(config.excluded_nodes or "None"))
    summary.add_row("Total paths", _format_total_paths(total_paths))
    summary.add_row("Handlers", handler_names)
    if device_id is not None:
        summary.add_row("Device", device_id)
    if resume_info is not None:
        summary.add_row("Resumable attempts", f"{resume_info.attempted_count:,}")
        summary.add_row("Latest run status", str(resume_info.latest_status or "None"))
        summary.add_row("Latest success", str(resume_info.latest_successful_attempt or "None"))
    console.print(summary)


def _execute_search(
    path_finder: PathFinder,
    logger: logging.Logger,
    database: RunDatabase | None,
    run_id: str | None,
    db_path: str,
    state: LiveRunState,
    total_paths_future: Future[int] | None,
) -> None:
    logger.info("Starting brute force search")
    state.set_search_status("Running")

    def search_worker() -> tuple[bool, list[str]]:
        for path in path_finder:
            while True:
                snapshot = state.snapshot()
                if snapshot["quit_requested"]:
                    raise UserRequestedStop()
                if not snapshot["paused"]:
                    break
                time.sleep(0.05)

            state.set_current_path(path)
            result_success, result_path = path_finder.process_path(
                path, state.snapshot()["total_paths"]
            )
            state.record_attempt(path)
            if result_success:
                resolved_path = result_path or path
                state.mark_success(resolved_path)
                state.set_feedback(f"Pattern found: {''.join(resolved_path)}")
                return True, resolved_path

        return False, []

    search_future = _run_in_background(search_worker)
    start_time = time.monotonic()

    try:
        _drive_live_dashboard(
            state,
            "GAPBF Live Run",
            total_paths_future,
            allow_pause=True,
            done_callback=search_future.done,
        )

        success, successful_path = search_future.result()
        elapsed_time = time.monotonic() - start_time

        if success:
            if database is not None and run_id is not None and successful_path is not None:
                database.finish_run(run_id, "success", "".join(successful_path))
            console.print(_render_live_dashboard(state, "GAPBF Live Run", allow_pause=True))
            console.print(f"Success: pattern found {successful_path}")
            console.print(f"Elapsed: {_format_elapsed(elapsed_time)}")
            logger.info(f"Successfully found pattern: {successful_path} in {elapsed_time:.2f}s")
            return

        state.mark_completed()
        if database is not None and run_id is not None:
            database.finish_run(run_id, "completed")
        console.print(_render_live_dashboard(state, "GAPBF Live Run", allow_pause=True))
        console.print("Search completed without finding a successful pattern")
        console.print(f"Elapsed: {_format_elapsed(elapsed_time)}")
        if database is not None:
            console.print(f"History: {db_path}")
        logger.info(
            f"Search completed without finding successful pattern after {elapsed_time:.2f}s"
        )
    except UserRequestedStop:
        state.mark_interrupted()
        if database is not None and run_id is not None:
            database.finish_run(run_id, "interrupted")
        elapsed_time = time.monotonic() - start_time
        console.print(_render_live_dashboard(state, "GAPBF Live Run", allow_pause=True))
        console.print("Search stopped by operator request")
        console.print(f"Elapsed: {_format_elapsed(elapsed_time)}")
        logger.info("Search stopped by operator request")
        raise typer.Exit(code=0)
    except KeyboardInterrupt:
        state.mark_interrupted()
        if database is not None and run_id is not None:
            database.finish_run(run_id, "interrupted")
        elapsed_time = time.monotonic() - start_time
        console.print(_render_live_dashboard(state, "GAPBF Live Run", allow_pause=True))
        console.print("Search interrupted by user")
        console.print(f"Elapsed: {_format_elapsed(elapsed_time)}")
        logger.info("Search interrupted by user")
        raise typer.Exit(code=0)
    except typer.Exit:
        raise
    except Exception as error:
        state.mark_error(str(error))
        if database is not None and run_id is not None:
            database.finish_run(run_id, "error")
        logger.error(f"Error during search: {error}", exc_info=True)
        raise typer.Exit(code=1) from error


def _show_status_dashboard(
    config: Config,
    mode: str,
    device_id: str | None,
    resume_info: ResumeInfo | None,
    total_paths: int | None,
    total_paths_future: Future[int] | None,
) -> None:
    state = LiveRunState(
        config=config,
        mode=mode,
        total_paths=total_paths,
        total_paths_state="ready" if total_paths is not None else "unknown",
        paths_tested=resume_info.attempted_count if resume_info is not None else 0,
    )
    state.attach_device_id(device_id)
    state.attach_resume_info(resume_info)
    state.set_search_status("Status")
    state.set_feedback(
        "Waiting for exact total path count"
        if total_paths_future is not None
        else "Status is ready"
    )

    if total_paths_future is not None:
        state.mark_total_paths_counting()
        closed_early = _drive_live_dashboard(
            state,
            "GAPBF Live Status",
            total_paths_future,
            allow_pause=False,
            done_callback=total_paths_future.done,
        )
        if closed_early:
            state.set_search_status("Closed")
            state.set_feedback("Status view closed by user")

    console.print(_render_live_dashboard(state, "GAPBF Live Status", allow_pause=False))


def _run_command(
    mode: str, config_path: str, log_level: str, log_file: str | None, dry_run: bool
) -> None:
    setup_logging(log_level, log_file)
    logger = logging.getLogger("gapbf")
    config = _load_config(config_path, logger)
    path_finder = _build_path_finder(config, logger)
    total_paths = _resolve_total_paths(config, path_finder, logger, calculate=False)
    state = LiveRunState(config=config, mode=mode, total_paths=total_paths, paths_tested=0)
    if total_paths is not None:
        state.total_paths_state = "ready"

    database = None
    run_info = None
    resume_info = None
    if "a" in mode and not dry_run:
        try:
            database = RunDatabase(config.db_path)
            device_id = detect_device_id(config.adb_timeout)
            resume_info = database.get_resume_info(config, device_id)
            run_info = database.create_run(config, device_id, mode)
            state.attach_device_id(device_id)
            state.attach_resume_info(resume_info)
            state.paths_tested = resume_info.attempted_count
            logger.info(f"Created run {run_info.run_id} for device {run_info.device_id}")
        except Exception as error:
            logger.error(f"Failed to initialize SQLite run logging: {error}")
            raise typer.Exit(code=1) from error

    if dry_run:
        _print_dry_run_summary(config, total_paths, path_finder)
        return

    _add_handlers(
        path_finder,
        config,
        mode,
        logger,
        database,
        run_info.run_id if run_info else None,
        run_info.device_id if run_info else None,
        Output(
            console,
            silent=True,
            event_sink=lambda _event, payload: state.set_feedback(
                str(payload.get("message", _event))
            ),
        ),
    )
    if resume_info is not None and resume_info.attempted_count > 0:
        _print_resume_summary(resume_info)
    _print_run_summary(
        config, mode, total_paths, resume_info, run_info.device_id if run_info else None
    )

    total_paths_future = None
    if total_paths is None:
        state.mark_total_paths_counting()
        total_paths_future = path_finder.calculate_total_paths_async()

    try:
        _execute_search(
            path_finder,
            logger,
            database,
            run_info.run_id if run_info else None,
            config.db_path,
            state,
            total_paths_future,
        )
    finally:
        if database is not None:
            database.close()


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    mode: str | None = typer.Option(
        None,
        "--mode",
        "-m",
        callback=lambda value: validate_mode(value) if value is not None else None,
    ),
    config: str = typer.Option("config.yaml", "--config", "-c"),
    log_level: str = typer.Option("error", "--logging", "-l"),
    log_file: str | None = typer.Option(None, "--log-file"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    if mode is None:
        console.print(ctx.get_help())
        raise typer.Exit(code=0)
    _run_command(mode, config, log_level, log_file, dry_run)


@app.command("run")
def run_command(
    mode: str = typer.Option(..., "--mode", "-m", callback=validate_mode),
    config: str = typer.Option("config.yaml", "--config", "-c"),
    log_level: str = typer.Option("error", "--logging", "-l"),
    log_file: str | None = typer.Option(None, "--log-file"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Run the brute-force search."""
    _run_command(mode, config, log_level, log_file, dry_run)


@app.command("history")
def history_command(
    config: str = typer.Option("config.yaml", "--config", "-c"),
    limit: int = typer.Option(20, min=1, max=200),
) -> None:
    """Show recent run history from the SQLite store."""
    logger = logging.getLogger("gapbf")
    run_config = _load_config(config, logger)
    database = RunDatabase(run_config.db_path)
    try:
        rows = database.list_runs(limit)
    finally:
        database.close()

    if not rows:
        console.print("No recorded runs found")
        return

    table = Table(title="Recent Runs")
    table.add_column("Run")
    table.add_column("Started")
    table.add_column("Status")
    table.add_column("Mode")
    table.add_column("Device")
    table.add_column("Attempts", justify="right")
    table.add_column("Success")
    for row in rows:
        table.add_row(
            row["run_id"][:8],
            row["started_at"],
            row["status"],
            row["mode"],
            row["device_id"],
            str(row["attempt_count"]),
            row["successful_attempt"] or "-",
        )
    console.print(table)


@app.command("check-device")
def check_device_command(
    config: str = typer.Option("config.yaml", "--config", "-c"),
) -> None:
    """Verify ADB connectivity and show the active device serial."""
    logger = logging.getLogger("gapbf")
    run_config = _load_config(config, logger)
    try:
        device_id = detect_device_id(run_config.adb_timeout)
    except RuntimeError as error:
        console.print(f"Device check failed: {error}")
        raise typer.Exit(code=1) from error

    table = Table(title="ADB Device")
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("Device", device_id)
    table.add_row("ADB timeout", f"{run_config.adb_timeout}s")
    console.print(table)


@app.command("status")
def status_command(
    config: str = typer.Option("config.yaml", "--config", "-c"),
    mode: str = typer.Option("a", "--mode", "-m", callback=validate_mode),
    calculate_total_paths: bool = typer.Option(
        False,
        "--calculate-total-paths",
        help="Compute an exact total path count. This can be slow for large configs.",
    ),
) -> None:
    """Show current config, device connectivity, and resume state."""
    logger = logging.getLogger("gapbf")
    run_config = _load_config(config, logger)
    path_finder = _build_path_finder(run_config, logger)
    total_paths = _resolve_total_paths(run_config, path_finder, logger, calculate=False)
    total_paths_future = None
    if total_paths is None and (calculate_total_paths or _should_auto_count_status_totals()):
        total_paths_future = path_finder.calculate_total_paths_async()

    device_id = None
    resume_info = None
    if "a" in mode:
        try:
            device_id = detect_device_id(run_config.adb_timeout)
        except RuntimeError as error:
            console.print(f"Device check failed: {error}")
            raise typer.Exit(code=1) from error

        database = RunDatabase(run_config.db_path)
        try:
            resume_info = database.get_resume_info(run_config, device_id)
        finally:
            database.close()

    _show_status_dashboard(
        run_config, mode, device_id, resume_info, total_paths, total_paths_future
    )


@app.command("web")
def web_command(
    config: str = typer.Option("config.yaml", "--config", "-c"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port", min=1, max=65535),
    log_level: str = typer.Option("error", "--logging", "-l"),
    log_file: str | None = typer.Option(None, "--log-file"),
) -> None:
    """Serve the local web UI for controlling and monitoring GAPBF."""
    from .web import serve_web_ui

    serve_web_ui(host=host, port=port, config_path=config, log_level=log_level, log_file=log_file)


def main() -> None:
    try:
        app()
    except typer.Exit as error:
        raise SystemExit(error.exit_code) from error


if __name__ == "__main__":
    main()
