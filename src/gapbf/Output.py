"""Shared CLI output helpers for GAPBF.

This keeps command and handler presentation in one place so the runtime does
not mix Rich-driven CLI output with ad hoc print calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from rich.console import Console

OutputEventSink = Callable[[str, dict[str, Any]], None]


@dataclass(slots=True)
class Output:
    """Console-backed output adapter used by commands and handlers."""

    console: Console
    silent: bool = False
    event_sink: OutputEventSink | None = None

    def _emit(self, event_type: str, **payload: Any) -> None:
        if self.event_sink is not None:
            self.event_sink(event_type, payload)

    def _print(self, message: str) -> None:
        if not self.silent:
            self.console.print(message)

    def show_resume(
        self, attempted_count: int, status: str | None = None, started_at: str | None = None
    ) -> None:
        if attempted_count <= 0:
            return
        message = f"Resuming with {attempted_count:,} previously attempted paths"
        if status:
            message += f" from the latest matching run ({status})"
        if started_at:
            message += f" started at {started_at}"
        self._emit(
            "resume",
            attempted_count=attempted_count,
            status=status,
            started_at=started_at,
            message=message,
        )
        self._print(message)

    def show_adb_skip(
        self, current: int, total: int | None, percentage: float, path: list[str]
    ) -> None:
        message = (
            f"Path {current}/{total} ({percentage:.1f}%): {path} - SKIPPED (already attempted)"
        )
        self._emit(
            "adb_skip",
            current=current,
            total=total,
            percentage=percentage,
            path=path,
            message=message,
        )
        self._print(message)

    def show_adb_timeout(self, current: int, total: int | None) -> None:
        message = f"Path {current}/{total} - TIMEOUT"
        self._emit("adb_timeout", current=current, total=total, message=message)
        self._print(message)

    def show_adb_error(self, current: int, total: int | None, error: str) -> None:
        message = f"Path {current}/{total} - ERROR: {error}"
        self._emit("adb_error", current=current, total=total, error=error, message=message)
        self._print(message)

    def show_adb_success(self, path: list[str]) -> None:
        message = f"Success: pattern found {path}"
        self._emit("adb_success", path=path, message=message)
        self._print(message)

    def show_adb_failure(
        self,
        current: int,
        total: int | None,
        percentage: float,
        path: list[str],
        delay_seconds: float,
    ) -> None:
        if delay_seconds > 0:
            message = (
                f"Path {current}/{total} ({percentage:.1f}%): {path} - FAILED. "
                f"Waiting {delay_seconds:.1f}s before next attempt"
            )
            self._emit(
                "adb_failure",
                current=current,
                total=total,
                percentage=percentage,
                path=path,
                delay_seconds=delay_seconds,
                message=message,
            )
            self._print(message)
            return
        message = f"Path {current}/{total} ({percentage:.1f}%): {path} - FAILED"
        self._emit(
            "adb_failure",
            current=current,
            total=total,
            percentage=percentage,
            path=path,
            delay_seconds=delay_seconds,
            message=message,
        )
        self._print(message)

    def show_adb_unexpected(self, current: int, total: int | None) -> None:
        message = f"Path {current}/{total} - UNEXPECTED ERROR"
        self._emit("adb_unexpected", current=current, total=total, message=message)
        self._print(message)

    def show_test_configuration(
        self,
        *,
        grid_size: int,
        path_max_node_distance: int,
        path_prefix: list[str],
        path_suffix: list[str],
        excluded_nodes: list[str],
        test_path: list[str],
    ) -> None:
        messages = [
            f"[TEST] Grid size: {grid_size}",
            f"[TEST] Path max node distance: {path_max_node_distance}",
            f"[TEST] Path prefix: {path_prefix}",
            f"[TEST] Path suffix: {path_suffix}",
            f"[TEST] Excluded nodes: {excluded_nodes}",
            f"[TEST] Test path: {test_path} (length: {len(test_path)})",
        ]
        self._emit(
            "test_configuration",
            grid_size=grid_size,
            path_max_node_distance=path_max_node_distance,
            path_prefix=path_prefix,
            path_suffix=path_suffix,
            excluded_nodes=excluded_nodes,
            test_path=test_path,
            messages=messages,
        )
        for message in messages:
            self._print(message)

    def show_test_result(
        self, *, success: bool, current: int, total: int | None, percentage: float, path: list[str]
    ) -> None:
        if success:
            self._emit(
                "test_success",
                success=success,
                current=current,
                total=total,
                percentage=percentage,
                path=path,
            )
            self._print(f"[TEST] SUCCESS! Path {current}/{total} ({percentage:.1f}%)")
            self._print(f"[TEST] Found: {path}")
            return
        message = f"[TEST] Path {current}/{total} ({percentage:.1f}%): {path} - FAILED"
        self._emit(
            "test_failure",
            success=success,
            current=current,
            total=total,
            percentage=percentage,
            path=path,
            message=message,
        )
        self._print(message)

    def show_print_path(self, path: list[str], path_rows: list[str], steps_rows: list[str]) -> None:
        self._emit("print_path", path=path, path_rows=path_rows, steps_rows=steps_rows)
        self._print(f"[PRINT] Path: {path}")
        for path_row, steps_row in zip(path_rows, steps_rows):
            self._print(f"  {path_row}    {steps_row}")
        self._print("")
