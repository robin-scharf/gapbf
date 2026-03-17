"""Shared CLI output helpers for GAPBF.

This keeps command and handler presentation in one place so the runtime does
not mix Rich-driven CLI output with ad hoc print calls.
"""

from __future__ import annotations

from dataclasses import dataclass
import time

from rich.console import Console


@dataclass(slots=True)
class Output:
    """Console-backed output adapter used by commands and handlers."""

    console: Console

    def show_resume(self, attempted_count: int, status: str | None = None, started_at: str | None = None) -> None:
        if attempted_count <= 0:
            return
        message = f"Resuming with {attempted_count:,} previously attempted paths"
        if status:
            message += f" from the latest matching run ({status})"
        if started_at:
            message += f" started at {started_at}"
        self.console.print(message)

    def show_adb_skip(self, current: int, total: int | None, percentage: float, path: list[str]) -> None:
        self.console.print(
            f"Path {current}/{total} ({percentage:.1f}%): {path} - SKIPPED (already attempted)"
        )

    def show_adb_timeout(self, current: int, total: int | None) -> None:
        self.console.print(f"Path {current}/{total} - TIMEOUT")

    def show_adb_error(self, current: int, total: int | None, error: str) -> None:
        self.console.print(f"Path {current}/{total} - ERROR: {error}")

    def show_adb_success(self, path: list[str]) -> None:
        self.console.print(f"Success: pattern found {path}")

    def show_adb_failure(self, current: int, total: int | None, percentage: float, path: list[str], delay_seconds: float) -> None:
        if delay_seconds > 0:
            self.console.print(
                f"Path {current}/{total} ({percentage:.1f}%): {path} - FAILED. Waiting {delay_seconds:.1f}s before next attempt"
            )
            time.sleep(delay_seconds)
            return
        self.console.print(f"Path {current}/{total} ({percentage:.1f}%): {path} - FAILED")

    def show_adb_unexpected(self, current: int, total: int | None) -> None:
        self.console.print(f"Path {current}/{total} - UNEXPECTED ERROR")

    def show_test_configuration(self, *, grid_size: int, path_max_node_distance: int, path_prefix: list[str], path_suffix: list[str], excluded_nodes: list[str], test_path: list[str]) -> None:
        self.console.print(f"[TEST] Grid size: {grid_size}")
        self.console.print(f"[TEST] Path max node distance: {path_max_node_distance}")
        self.console.print(f"[TEST] Path prefix: {path_prefix}")
        self.console.print(f"[TEST] Path suffix: {path_suffix}")
        self.console.print(f"[TEST] Excluded nodes: {excluded_nodes}")
        self.console.print(f"[TEST] Test path: {test_path} (length: {len(test_path)})")

    def show_test_result(self, *, success: bool, current: int, total: int | None, percentage: float, path: list[str]) -> None:
        if success:
            self.console.print(f"[TEST] SUCCESS! Path {current}/{total} ({percentage:.1f}%)")
            self.console.print(f"[TEST] Found: {path}")
            return
        self.console.print(f"[TEST] Path {current}/{total} ({percentage:.1f}%): {path} - FAILED")

    def show_print_path(self, path: list[str], path_rows: list[str], steps_rows: list[str]) -> None:
        self.console.print(f"[PRINT] Path: {path}")
        for path_row, steps_row in zip(path_rows, steps_rows):
            self.console.print(f"  {path_row}    {steps_row}")
        self.console.print()