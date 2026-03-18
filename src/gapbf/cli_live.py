import os
import select
import sys
import termios
import time
import tty
from concurrent.futures import Future
from contextlib import AbstractContextManager
from threading import Thread
from typing import Any, Callable, TypedDict, TypeVar

from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .cli_definitions import console, handler_classes
from .Config import Config
from .Database import ResumeInfo
from .runtime import RunState

ResultT = TypeVar("ResultT")
SPINNER_FRAMES = "|/-\\"
LiveRunState = RunState
LiveRunSnapshot = TypedDict(
    "LiveRunSnapshot",
    {
        "config": Config,
        "mode": str,
        "total_paths": int | None,
        "total_paths_state": str,
        "paths_tested": int,
        "current_path": str,
        "last_feedback": str,
        "search_status": str,
        "device_id": str | None,
        "resume_info": ResumeInfo | None,
        "started_at": float,
        "successful_path": str | None,
        "error_message": str | None,
        "paused": bool,
        "show_help": bool,
        "quit_requested": bool,
        "key_input_enabled": bool,
    },
)


class TerminalKeyReader(AbstractContextManager["TerminalKeyReader"]):
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


def run_in_background(
    callback: Callable[..., ResultT], *args: Any, **kwargs: Any
) -> Future[ResultT]:
    future: Future[ResultT] = Future()

    def runner() -> None:
        if future.set_running_or_notify_cancel():
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


def format_elapsed(elapsed_seconds: float) -> str:
    hours, remainder = divmod(int(elapsed_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _format_progress(paths_tested: int, total_paths: int | None) -> str:
    if total_paths is None:
        return f"{paths_tested:,} / Unknown"
    if total_paths == 0:
        return f"{paths_tested:,} / 0"
    return f"{paths_tested:,} / {total_paths:,} ({paths_tested / total_paths * 100:.4f}%)"


def _format_total_paths_state(total_paths: int | None, total_paths_state: str) -> str:
    if total_paths is not None:
        return f"{total_paths:,}"
    if total_paths_state == "counting":
        frame = SPINNER_FRAMES[int(time.monotonic() * 8) % len(SPINNER_FRAMES)]
        return f"{frame} Counting exact total in background"
    return "Unavailable" if total_paths_state == "error" else "Unknown"


def _control_hint(allow_pause: bool, key_input_enabled: bool) -> str:
    if not key_input_enabled:
        return "Interactive controls unavailable in this terminal. Ctrl+C still stops the run."
    return (
        "Keys: p pause/resume, q quit after current attempt, h help, Ctrl+C hard stop"
        if allow_pause
        else "Keys: q close view, h help"
    )


def _control_help(allow_pause: bool) -> list[str]:
    return (
        [
            "p: pause or resume between attempts",
            "q: stop the run after the current in-flight attempt",
            "h: toggle this help",
            "Ctrl+C: interrupt immediately",
        ]
        if allow_pause
        else ["q: close the status view", "h: toggle this help"]
    )


def handle_live_keypress(state: LiveRunState, key: str, *, allow_pause: bool) -> bool:
    normalized = key.lower()
    if normalized in {"h", "?"}:
        help_visible = state.toggle_help()
        state.set_feedback("Controls help shown" if help_visible else "Controls help hidden")
        return False
    if normalized == "q":
        state.request_quit()
        state.set_feedback(
            "Stop requested. Waiting for the current attempt to finish"
            if allow_pause
            else "Status view closed by user"
        )
        return not allow_pause
    if allow_pause and normalized == "p":
        paused = state.toggle_pause()
        state.set_feedback("Run paused" if paused else "Run resumed")
    return False


def render_live_dashboard(state: LiveRunState, title: str, *, allow_pause: bool) -> Panel:
    snapshot = state.snapshot()
    config = snapshot["config"]
    resume_info = snapshot["resume_info"]
    table = Table(title=title, show_header=False)
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("Search", str(snapshot["search_status"]))
    table.add_row("Progress", _format_progress(snapshot["paths_tested"], snapshot["total_paths"]))
    table.add_row(
        "Total paths",
        _format_total_paths_state(snapshot["total_paths"], snapshot["total_paths_state"]),
    )
    table.add_row("Current path", str(snapshot["current_path"]))
    table.add_row("Last feedback", str(snapshot["last_feedback"]))
    table.add_row("Elapsed", format_elapsed(time.monotonic() - snapshot["started_at"]))
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
    return Panel.fit(
        table,
        subtitle=Text(_control_hint(allow_pause, bool(snapshot["key_input_enabled"])), style="dim"),
    )


def sync_live_total_paths(state: LiveRunState, total_paths_future: Future[int] | None) -> None:
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


def should_auto_count_status_totals() -> bool:
    return sys.stdin.isatty()


def drive_live_dashboard(
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
            render_live_dashboard(state, title, allow_pause=allow_pause),
            console=console,
            refresh_per_second=8,
            transient=True,
        ) as live:
            while not done_callback():
                sync_live_total_paths(state, total_paths_future)
                key = key_reader.read_key()
                if key is not None and handle_live_keypress(state, key, allow_pause=allow_pause):
                    live.update(render_live_dashboard(state, title, allow_pause=allow_pause))
                    return True
                live.update(render_live_dashboard(state, title, allow_pause=allow_pause))
                time.sleep(0.1)
            sync_live_total_paths(state, total_paths_future)
            live.update(render_live_dashboard(state, title, allow_pause=allow_pause))
    return False
