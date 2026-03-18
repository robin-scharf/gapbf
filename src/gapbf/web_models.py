from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from .Config import Config, valid_nodes_for_grid

ALLOWED_MODES = {"a", "p", "t"}


class LoadConfigRequest(BaseModel):
    path: str = Field(default="config.yaml", min_length=1)


class SaveConfigRequest(BaseModel):
    path: str = Field(min_length=1)
    config: dict[str, Any]


class ValidateConfigRequest(BaseModel):
    config: dict[str, Any]


class StartRunRequest(BaseModel):
    mode: str = Field(default="a", min_length=1)
    config: dict[str, Any]


def validate_mode(mode: str) -> str:
    if not mode or not set(mode).issubset(ALLOWED_MODES):
        allowed = "".join(sorted(ALLOWED_MODES))
        raise ValueError(f"Invalid mode: {mode}. Allowed values are combinations of {allowed}.")
    return mode


def serialize_resume_info(resume_info: Any) -> dict[str, Any] | None:
    if resume_info is None:
        return None
    return {
        "attempted_count": resume_info.attempted_count,
        "latest_run_id": resume_info.latest_run_id,
        "latest_started_at": resume_info.latest_started_at,
        "latest_finished_at": resume_info.latest_finished_at,
        "latest_status": resume_info.latest_status,
        "latest_successful_attempt": resume_info.latest_successful_attempt,
    }


def serialize_attempt_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "timestamp": row["timestamp"],
        "attempt": row["attempt"],
        "response": row["response"],
        "stdout": row["stdout"],
        "stderr": row["stderr"],
        "result_classification": row["result_classification"],
        "returncode": row["returncode"],
        "duration_ms": row["duration_ms"],
    }


def serialize_run_row(row: Any) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "status": row["status"],
        "mode": row["mode"],
        "device_id": row["device_id"],
        "successful_attempt": row["successful_attempt"],
        "attempt_count": row["attempt_count"],
    }


def config_meta(grid_size: int) -> dict[str, Any]:
    nodes = valid_nodes_for_grid(grid_size)
    return {
        "grid_size": grid_size,
        "nodes": nodes,
        "node_count": len(nodes),
        "min_path_length": 4,
        "default_path_min_length": 4,
        "max_path_length": len(nodes),
        "default_path_max_length": len(nodes),
        "default_attempt_delay": 10.1,
        "default_adb_timeout": 30,
    }


def serialize_config(config: Config) -> dict[str, Any]:
    payload = config.model_dump()
    payload["config_file_path"] = config.config_file_path
    return payload


def config_from_payload(config_data: dict[str, Any]) -> Config:
    normalized = dict(config_data)
    normalized.setdefault("grid_size", 3)
    normalized.setdefault("path_min_length", 4)
    normalized.setdefault("path_max_length", normalized["grid_size"] ** 2)
    normalized.setdefault("path_max_node_distance", 1)
    normalized.setdefault("path_prefix", [])
    normalized.setdefault("path_suffix", [])
    normalized.setdefault("excluded_nodes", [])
    normalized.setdefault("attempt_delay", 0.0)
    normalized.setdefault("test_path", [])
    normalized.setdefault("stdout_normal", "")
    normalized.setdefault("stdout_success", "")
    normalized.setdefault("stdout_error", "")
    normalized.setdefault("db_path", "~/.gapbf/gapbf.db")
    normalized.setdefault("adb_timeout", 30)
    normalized.setdefault("total_paths", 0)
    normalized.setdefault("echo_commands", True)
    normalized.setdefault("config_file_path", normalized.get("config_file_path", "web-ui"))
    return Config(**normalized)


def save_config_to_path(path: str, config_data: dict[str, Any]) -> dict[str, Any]:
    config = config_from_payload({**config_data, "config_file_path": path})
    config_path = Path(path).expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as file_obj:
        yaml.safe_dump(config.model_dump(exclude={"config_file_path"}), file_obj, sort_keys=False)
    return {
        "saved_path": str(config_path),
        "config": serialize_config(config),
        "meta": config_meta(config.grid_size),
    }
