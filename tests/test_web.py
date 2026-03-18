import time

from fastapi.testclient import TestClient

from gapbf.Config import Config
from gapbf.Database import RunDatabase
from gapbf.web import create_app


def test_load_config_endpoint_returns_config_and_meta(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "grid_size: 4",
                "path_min_length: 4",
                "path_max_length: 8",
                "path_prefix: [1, 2]",
                "path_suffix: [7, 8]",
            ]
        ),
        encoding="utf-8",
    )

    client = TestClient(create_app(str(config_path)))
    response = client.post("/api/config/load", json={"path": str(config_path)})

    assert response.status_code == 200
    payload = response.json()
    assert payload["config"]["grid_size"] == 4
    assert payload["config"]["path_prefix"] == ["1", "2"]
    assert payload["meta"]["max_path_length"] == 16


def test_validate_config_endpoint_rejects_invalid_overlap(tmp_path):
    client = TestClient(create_app(str(tmp_path / "config.yaml")))
    response = client.post(
        "/api/config/validate",
        json={
            "config": {
                "grid_size": 3,
                "path_min_length": 4,
                "path_max_length": 9,
                "path_prefix": ["1", "2"],
                "path_suffix": ["7", "8"],
                "excluded_nodes": ["2"],
            }
        },
    )

    assert response.status_code == 400
    assert "path_prefix contains excluded nodes" in str(response.json()["detail"])


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
                "path_prefix": ["1", "2", "3", "4"],
                "path_suffix": ["1", "2", "3", "4"],
                "excluded_nodes": [],
                "attempt_delay": 0,
                "test_path": ["1", "2", "3", "4"],
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
    assert snapshot["successful_path"] == "1234"
    assert snapshot["paths_tested"] >= 1
    assert any(entry["result_classification"] == "test_success" for entry in snapshot["log_tail"])


def test_attempt_endpoints_return_recorded_history(tmp_path):
    db_path = tmp_path / "gapbf.db"
    config = Config(db_path=str(db_path), grid_size=3, path_min_length=4, path_max_length=9)
    database = RunDatabase(str(db_path))
    run = database.create_run(config, "SERIAL123", "a")
    database.log_attempt(run.run_id, "1234", "Failed to decrypt", "normal_failure", 0, 12.5)
    database.finish_run(run.run_id, "completed")
    database.close()

    client = TestClient(create_app(str(tmp_path / "config.yaml")))
    runs_response = client.get("/api/runs", params={"db_path": str(db_path), "limit": 10})
    attempts_response = client.get(
        "/api/attempts",
        params={"db_path": str(db_path), "run_id": run.run_id, "limit": 10},
    )

    assert runs_response.status_code == 200
    assert attempts_response.status_code == 200
    assert runs_response.json()["runs"][0]["run_id"] == run.run_id
    assert attempts_response.json()["attempts"][0]["attempt"] == "1234"