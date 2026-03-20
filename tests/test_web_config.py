import time

from fastapi.testclient import TestClient

from gapbf.web import create_app


def test_load_config_endpoint_returns_config_and_meta(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "grid_size: 4",
                "path_min_length: 4",
                "path_max_length: 8",
                "no_diagonal_crossings: true",
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
    assert payload["config"]["no_diagonal_crossings"] is True
    assert payload["config"]["path_prefix"] == ["1", "2"]
    assert payload["meta"]["min_path_length"] == 4
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


def test_save_config_endpoint_persists_yaml(tmp_path):
    config_path = tmp_path / "saved-config.yaml"
    client = TestClient(create_app(str(tmp_path / "config.yaml")))
    response = client.post(
        "/api/config/save",
        json={
            "path": str(config_path),
            "config": {
                "grid_size": 4,
                "path_min_length": 4,
                "path_max_length": 8,
                "no_diagonal_crossings": True,
                "no_perpendicular_crossings": True,
                "path_prefix": ["1", "2"],
                "path_suffix": ["7", "8"],
                "excluded_nodes": ["5"],
                "attempt_delay": 0,
                "test_path": [],
                "stdout_normal": "Failed to decrypt",
                "stdout_success": "Data successfully decrypted",
                "stdout_error": "",
                "db_path": "~/.gapbf/gapbf.db",
                "adb_timeout": 30,
                "total_paths": 0,
                "echo_commands": True,
            },
        },
    )

    assert response.status_code == 200
    assert config_path.exists()
    saved_text = config_path.read_text(encoding="utf-8")
    assert "grid_size: 4" in saved_text
    assert "no_diagonal_crossings: true" in saved_text
    assert "no_perpendicular_crossings: true" in saved_text
    assert "path_prefix:" in saved_text
    assert "- '1'" in saved_text or '- "1"' in saved_text or "- '2'" in saved_text


def test_calculate_total_paths_endpoint_updates_snapshot(tmp_path):
    client = TestClient(create_app(str(tmp_path / "config.yaml")))

    response = client.post(
        "/api/config/calculate-total-paths",
        json={
            "config": {
                "grid_size": 3,
                "path_min_length": 4,
                "path_max_length": 4,
                "path_prefix": ["1", "2", "3", "6"],
                "path_suffix": ["1", "2", "3", "6"],
                "excluded_nodes": [],
                "attempt_delay": 0,
                "test_path": [],
                "stdout_normal": "Failed to decrypt",
                "stdout_success": "Data successfully decrypted",
                "stdout_error": "",
                "db_path": str(tmp_path / "gapbf.db"),
                "adb_timeout": 30,
                "total_paths": 0,
                "echo_commands": True,
            }
        },
    )

    assert response.status_code == 200

    for _ in range(40):
        snapshot = client.get("/api/state").json()
        if snapshot["total_paths_state"] == "ready":
            break
        time.sleep(0.05)
    else:
        raise AssertionError("total path calculation did not complete")

    assert snapshot["total_paths"] == 1
    assert snapshot["total_paths_state"] == "ready"