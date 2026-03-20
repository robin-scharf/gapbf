from fastapi.testclient import TestClient

from gapbf.Config import Config
from gapbf.Database import RunDatabase
from gapbf.web import create_app


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