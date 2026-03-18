from threading import Thread

from gapbf.Config import Config
from gapbf.Database import RunDatabase


class TestRunDatabase:
    def test_create_run_and_finish(self, tmp_path):
        db_path = tmp_path / "gapbf.db"
        config = Config(db_path=str(db_path), grid_size=3, path_min_length=4, path_max_length=9)

        database = RunDatabase(str(db_path))
        run = database.create_run(config, "SERIAL123", "a")
        database.finish_run(run.run_id, "success", "1478")

        row = database.connection.execute(
            "select status, successful_attempt from runs where run_id = ?",
            (run.run_id,),
        ).fetchone()
        database.close()

        assert row["status"] == "success"
        assert row["successful_attempt"] == "1478"

    def test_attempts_are_available_for_resume(self, tmp_path):
        db_path = tmp_path / "gapbf.db"
        config = Config(db_path=str(db_path), grid_size=3, path_min_length=4, path_max_length=9)

        database = RunDatabase(str(db_path))
        run = database.create_run(config, "SERIAL123", "a")
        database.log_attempt(run.run_id, "1234", "Failed to decrypt", "normal_failure", 0, 15.0)
        database.log_attempt(run.run_id, "1478", "Data successfully decrypted", "success", 0, 14.0)

        attempted = database.get_attempted_paths(config, "SERIAL123")
        database.close()

        assert attempted == {"1234", "1478"}

    def test_log_attempt_is_safe_from_worker_thread(self, tmp_path):
        db_path = tmp_path / "gapbf.db"
        config = Config(db_path=str(db_path), grid_size=3, path_min_length=4, path_max_length=9)

        database = RunDatabase(str(db_path))
        run = database.create_run(config, "SERIAL123", "a")

        worker = Thread(
            target=database.log_attempt,
            args=(run.run_id, "1234", "Failed to decrypt", "normal_failure", 0, 15.0),
        )
        worker.start()
        worker.join()

        attempted = database.get_attempted_paths(config, "SERIAL123")
        database.close()

        assert attempted == {"1234"}
