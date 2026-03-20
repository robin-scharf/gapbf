import time
from concurrent.futures import Future

from fastapi.testclient import TestClient

from gapbf.web import create_app


def test_total_path_count_timeout_falls_back_to_unknown_total(tmp_path, monkeypatch):
    from gapbf import web_controller_runtime
    from gapbf.PathFinder import PathFinder

    monkeypatch.setattr(web_controller_runtime, "TOTAL_PATHS_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(web_controller_runtime, "TOTAL_PATHS_PROGRESS_INTERVAL_SECONDS", 0.01)

    def hanging_total_future(self):
        return Future()

    monkeypatch.setattr(PathFinder, "calculate_total_paths_async", hanging_total_future)

    config_path = tmp_path / "config.yaml"
    client = TestClient(create_app(str(config_path)))

    response = client.post(
        "/api/run/start",
        json={
            "mode": "t",
            "config": {
                "grid_size": 3,
                "path_min_length": 4,
                "path_max_length": 4,
                "path_prefix": ["1", "2", "3", "6"],
                "path_suffix": ["1", "2", "3", "6"],
                "excluded_nodes": [],
                "attempt_delay": 0,
                "test_path": ["1", "2", "3", "6"],
                "stdout_normal": "Failed to decrypt",
                "stdout_success": "Data successfully decrypted",
                "stdout_error": "",
                "db_path": str(tmp_path / "gapbf.db"),
                "adb_timeout": 30,
                "total_paths": 0,
                "echo_commands": True,
            },
        },
    )

    assert response.status_code == 200

    for _ in range(80):
        snapshot = client.get("/api/state").json()
        if snapshot["total_paths_state"] == "timeout":
            break
        time.sleep(0.02)
    else:
        raise AssertionError("web total-path count did not time out")

    assert snapshot["total_paths"] is None
    assert snapshot["total_paths_elapsed_seconds"] >= 0
    assert snapshot["total_paths_timeout_seconds"] == 30
    assert "unknown total" in snapshot["last_feedback"].lower()