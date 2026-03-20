import subprocess

from gapbf.Config import Config
from gapbf.Database import AttemptHistoryEntry
from gapbf.PathHandler import ADBHandler


class TestADBHandler:
    def test_adbhandler_init_starts_server_and_loads_attempts(self, mocker):
        config = Config(
            grid_size=3,
            path_min_length=4,
            path_max_length=9,
            stdout_normal="Failed",
            stdout_success="Success",
            stdout_error="Error",
            adb_timeout=30,
        )
        database = mocker.Mock()
        database.get_terminal_attempt_history.return_value = {
            "known-hash": AttemptHistoryEntry("1234", "known-hash", "normal_failure")
        }
        run_result = mocker.Mock(returncode=0, stdout="", stderr="")
        subprocess_run = mocker.patch("gapbf.PathHandler.subprocess.run", return_value=run_result)
        reporter = mocker.Mock()

        handler = ADBHandler(
            config, database=database, run_id="run-1", device_id="SERIAL123", output=reporter
        )

        assert handler.current_path_number == 1
        database.get_terminal_attempt_history.assert_called_once_with(config, "SERIAL123")
        subprocess_run.assert_called_once_with(
            ["adb", "start-server"], check=True, capture_output=True
        )

    def test_handle_path_skips_attempted_path(self, mocker):
        config = Config(
            grid_size=3,
            path_min_length=4,
            path_max_length=9,
            stdout_normal="Failed",
            stdout_success="Success",
            stdout_error="Error",
            adb_timeout=30,
        )
        database = mocker.Mock()
        known_hash = "known-hash"
        database.get_terminal_attempt_history.return_value = {
            known_hash: AttemptHistoryEntry("123", known_hash, "normal_failure")
        }
        database.attempt_hash_for.return_value = known_hash
        run_result = mocker.Mock(returncode=0, stdout="", stderr="")
        subprocess_run = mocker.patch("gapbf.PathHandler.subprocess.run", return_value=run_result)
        reporter = mocker.Mock()

        handler = ADBHandler(
            config, database=database, run_id="run-1", device_id="SERIAL123", output=reporter
        )
        success, path = handler.handle_path(["1", "2", "3"], total_paths=100)

        assert success is False
        assert path is None
        database.log_attempt.assert_not_called()
        assert subprocess_run.call_count == 1
        reporter.show_adb_skip.assert_called_once()

    def test_handle_path_returns_cached_success(self, mocker):
        config = Config(
            grid_size=3,
            path_min_length=4,
            path_max_length=9,
            stdout_normal="Failed",
            stdout_success="Success",
            stdout_error="Error",
            adb_timeout=30,
        )
        database = mocker.Mock()
        known_hash = "known-hash"
        database.get_terminal_attempt_history.return_value = {
            known_hash: AttemptHistoryEntry("123", known_hash, "success")
        }
        database.attempt_hash_for.return_value = known_hash
        run_result = mocker.Mock(returncode=0, stdout="", stderr="")
        subprocess_run = mocker.patch("gapbf.PathHandler.subprocess.run", return_value=run_result)
        reporter = mocker.Mock()

        handler = ADBHandler(
            config, database=database, run_id="run-1", device_id="SERIAL123", output=reporter
        )
        success, path = handler.handle_path(["1", "2", "3"], total_paths=100)

        assert success is True
        assert path == ["1", "2", "3"]
        database.log_attempt.assert_not_called()
        assert subprocess_run.call_count == 1
        reporter.show_adb_success.assert_called_once_with(["1", "2", "3"])

    def test_handle_path_success(self, mocker):
        config = Config(
            grid_size=3,
            path_min_length=4,
            path_max_length=9,
            stdout_normal="Failed",
            stdout_success="Data successfully decrypted",
            stdout_error="Error",
            adb_timeout=30,
            echo_commands=False,
        )
        database = mocker.Mock()
        database.get_terminal_attempt_history.return_value = {}
        database.attempt_hash_for.return_value = "new-hash"
        database.get_terminal_attempt_entry.return_value = AttemptHistoryEntry(
            "123", "new-hash", "success"
        )
        start_result = mocker.Mock(returncode=0, stdout="", stderr="")
        decrypt_result = mocker.Mock(returncode=0, stdout="Data successfully decrypted", stderr="")
        subprocess_run = mocker.patch(
            "gapbf.PathHandler.subprocess.run", side_effect=[start_result, decrypt_result]
        )
        reporter = mocker.Mock()

        handler = ADBHandler(
            config, database=database, run_id="run-1", device_id="SERIAL123", output=reporter
        )
        success, path = handler.handle_path(["1", "2", "3"], total_paths=100)

        assert success is True
        assert path == ["1", "2", "3"]
        subprocess_run.assert_any_call(
            ["adb", "shell", "twrp", "decrypt", "123"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        database.log_attempt.assert_called_once()
        reporter.show_adb_success.assert_called_once_with(["1", "2", "3"])

    def test_handle_path_timeout(self, mocker):
        config = Config(
            grid_size=3,
            path_min_length=4,
            path_max_length=9,
            stdout_normal="Failed",
            stdout_success="Success",
            stdout_error="Error",
            adb_timeout=30,
        )
        database = mocker.Mock()
        database.get_terminal_attempt_history.return_value = {}
        database.attempt_hash_for.return_value = "new-hash"
        start_result = mocker.Mock(returncode=0, stdout="", stderr="")
        mocker.patch(
            "gapbf.PathHandler.subprocess.run",
            side_effect=[start_result, subprocess.TimeoutExpired(cmd="adb", timeout=30)],
        )
        reporter = mocker.Mock()

        handler = ADBHandler(
            config, database=database, run_id="run-1", device_id="SERIAL123", output=reporter
        )
        success, path = handler.handle_path(["1", "2", "3"], total_paths=100)

        assert success is False
        assert path is None
        database.log_attempt.assert_called_once()
        reporter.show_adb_timeout.assert_called_once()

    def test_handle_path_uses_configured_error_marker(self, mocker):
        config = Config(
            grid_size=3,
            path_min_length=4,
            path_max_length=9,
            stdout_normal="Failed",
            stdout_success="Success",
            stdout_error="Error occurred",
            adb_timeout=30,
            echo_commands=False,
        )
        database = mocker.Mock()
        database.get_terminal_attempt_history.return_value = {}
        database.attempt_hash_for.return_value = "new-hash"
        database.get_terminal_attempt_entry.return_value = AttemptHistoryEntry(
            "123", "new-hash", "normal_failure"
        )
        start_result = mocker.Mock(returncode=0, stdout="", stderr="")
        decrypt_result = mocker.Mock(returncode=0, stdout="Error occurred", stderr="")
        mocker.patch("gapbf.PathHandler.subprocess.run", side_effect=[start_result, decrypt_result])
        reporter = mocker.Mock()

        handler = ADBHandler(
            config, database=database, run_id="run-1", device_id="SERIAL123", output=reporter
        )
        success, path = handler.handle_path(["1", "2", "3"], total_paths=100)

        assert success is False
        assert path is None
        database.log_attempt.assert_called_once()
        assert database.log_attempt.call_args.args[3] == "configured_error"
        reporter.show_adb_error.assert_called_once()