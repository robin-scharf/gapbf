from threading import Thread

from gapbf.Config import Config
from gapbf.Database import AttemptHistoryEntry, RunDatabase


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
        updated_config = Config(
            db_path=str(db_path),
            grid_size=3,
            path_min_length=4,
            path_max_length=9,
            attempt_delay=10.1,
            stdout_normal="Different",
        )

        database = RunDatabase(str(db_path))
        run = database.create_run(config, "SERIAL123", "a")
        database.log_attempt(run.run_id, "1234", "Failed to decrypt", "normal_failure", 0, 15.0)
        database.log_attempt(run.run_id, "1478", "Data successfully decrypted", "success", 0, 14.0)

        attempted = database.get_attempted_paths(updated_config, "SERIAL123")
        database.close()

        assert attempted == {"1234", "1478"}

    def test_create_run_reconciles_stale_running_rows(self, tmp_path):
        db_path = tmp_path / "gapbf.db"
        config = Config(db_path=str(db_path), grid_size=3, path_min_length=4, path_max_length=9)

        database = RunDatabase(str(db_path))
        first_run = database.create_run(config, "SERIAL123", "a")
        database.connection.execute(
            "UPDATE runs SET updated_at = '2000-01-01T00:00:00+00:00' WHERE run_id = ?",
            (first_run.run_id,),
        )
        database.connection.commit()

        second_run = database.create_run(config, "SERIAL123", "a")
        rows = database.connection.execute(
            "SELECT run_id, status FROM runs ORDER BY started_at ASC"
        ).fetchall()
        database.close()

        assert rows[0]["run_id"] == first_run.run_id
        assert rows[0]["status"] == "interrupted_or_crashed"
        assert rows[1]["run_id"] == second_run.run_id
        assert rows[1]["status"] == "running"

    def test_log_attempt_preserves_raw_stdout_and_stderr(self, tmp_path):
        db_path = tmp_path / "gapbf.db"
        config = Config(db_path=str(db_path), grid_size=3, path_min_length=4, path_max_length=9)

        database = RunDatabase(str(db_path))
        run = database.create_run(config, "SERIAL123", "a")
        database.log_attempt(
            run.run_id,
            "1234",
            "stdout=Failed; stderr=warning",
            "unknown_response",
            0,
            10.0,
            stdout="Failed",
            stderr="warning",
        )
        row = database.list_attempts(run.run_id, limit=1)[0]
        database.close()

        assert row["stdout"] == "Failed"
        assert row["stderr"] == "warning"

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

    def test_log_attempt_stores_attempt_hash_and_terminal_history(self, tmp_path):
        db_path = tmp_path / "gapbf.db"
        config = Config(db_path=str(db_path), grid_size=3, path_min_length=4, path_max_length=9)

        database = RunDatabase(str(db_path))
        run = database.create_run(config, "SERIAL123", "a")
        database.log_attempt(run.run_id, "1234", "Failed to decrypt", "normal_failure", 0, 15.0)
        database.log_attempt(run.run_id, "5678", "Timeout after 30s", "timeout", -1, 30.0)

        row = database.connection.execute(
            "SELECT attempt_hash FROM attempts WHERE attempt = ?",
            ("1234",),
        ).fetchone()
        history = database.get_terminal_attempt_history(config, "SERIAL123")
        expected_hash = database.attempt_hash_for("SERIAL123", 3, "1234")
        database.close()

        assert row["attempt_hash"] == expected_hash
        assert history == {
            expected_hash: AttemptHistoryEntry(
                attempt="1234",
                attempt_hash=expected_hash,
                result_classification="normal_failure",
            )
        }

    def test_attempt_hash_changes_with_device_and_grid(self, tmp_path):
        database = RunDatabase(str(tmp_path / "gapbf.db"))

        first = database.attempt_hash_for("SERIAL123", 3, "1234")
        second = database.attempt_hash_for("SERIAL999", 3, "1234")
        third = database.attempt_hash_for("SERIAL123", 4, "1234")
        database.close()

        assert first != second
        assert first != third
