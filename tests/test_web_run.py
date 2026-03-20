import time

from fastapi.testclient import TestClient

from gapbf.web import create_app


def test_start_run_in_test_mode_completes_and_updates_state(tmp_path):
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
                "total_paths": 1,
                "echo_commands": True,
            },
        },
    )

    assert response.status_code == 200

    for _ in range(40):
        snapshot = client.get("/api/state").json()
        if not snapshot["active"]:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("web test-mode run did not complete")

    assert snapshot["status"] == "success"
    assert snapshot["successful_path"] == "1236"
    assert snapshot["paths_tested"] >= 1
    assert any(entry["result_classification"] == "test_success" for entry in snapshot["log_tail"])


def test_successful_run_state_exposes_successful_path_for_notice(tmp_path):
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
                "total_paths": 1,
                "echo_commands": True,
            },
        },
    )

    assert response.status_code == 200

    for _ in range(40):
        snapshot = client.get("/api/state").json()
        if snapshot["status"] == "success":
            break
        time.sleep(0.05)
    else:
        raise AssertionError("web test-mode run did not report success")

    assert snapshot["successful_path"] == "1236"