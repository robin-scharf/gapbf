from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .Config import Config


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_db_path(db_path: str) -> Path:
    resolved = Path(db_path).expanduser()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def detect_device_id(timeout_seconds: int = 30) -> str:
    try:
        result = subprocess.run(
            ["adb", "get-serialno"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=True,
        )
    except FileNotFoundError as error:
        raise RuntimeError(
            "ADB command not found. Please install Android platform-tools"
        ) from error
    except subprocess.CalledProcessError as error:
        stderr = (error.stderr or "").strip()
        raise RuntimeError(f"Failed to determine ADB device id: {stderr or error}") from error
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"Timed out while determining device id after {timeout_seconds}s"
        ) from error

    serial = result.stdout.strip()
    if not serial or serial in {"unknown", "", "<empty>"}:
        raise RuntimeError("ADB did not report a usable device serial number")
    return serial


@dataclass(frozen=True)
class RunInfo:
    run_id: str
    config_fingerprint: str
    device_id: str


@dataclass(frozen=True)
class ResumeInfo:
    attempted_count: int
    latest_run_id: str | None
    latest_started_at: str | None
    latest_finished_at: str | None
    latest_status: str | None
    latest_successful_attempt: str | None


def stale_run_timeout_seconds(config: Config) -> int:
    minimum_timeout = 300
    attempt_window = int(config.adb_timeout + config.attempt_delay) * 3 + 30
    return max(minimum_timeout, attempt_window)
