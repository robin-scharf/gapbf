import pytest
from typer.testing import CliRunner

from gapbf.Config import Config
from gapbf.Database import ResumeInfo, RunDatabase
from gapbf.main import LiveRunState, _handle_live_keypress, app, handler_classes, validate_mode

runner = CliRunner()


def test_validate_mode_accepts_supported_combinations():
    assert validate_mode("a") == "a"
    assert validate_mode("p") == "p"
    assert validate_mode("t") == "t"
    assert validate_mode("ap") == "ap"
    assert validate_mode("apt") == "apt"


def test_validate_mode_rejects_invalid_modes():
    with pytest.raises(Exception, match="Invalid mode"):
        validate_mode("x")

    with pytest.raises(Exception, match="Invalid mode"):
        validate_mode("az")


def test_handler_classes_define_expected_handlers():
    assert set(handler_classes) == {"a", "p", "t"}
    assert handler_classes["a"]["class_"].__name__ == "ADBHandler"
    assert handler_classes["p"]["class_"].__name__ == "PrintHandler"
    assert handler_classes["t"]["class_"].__name__ == "TestHandler"


def test_run_command_dry_run_uses_command_surface(mocker):
    config = Config(grid_size=3, path_min_length=4, path_max_length=5)
    mocker.patch("gapbf.main.Config.load_config", return_value=config)
    path_finder = mocker.Mock()
    path_finder.total_paths = 42
    path_finder.calculate_total_paths_async.return_value = mocker.Mock(
        done=lambda: True, result=lambda: 42
    )
    mocker.patch("gapbf.main.PathFinder", return_value=path_finder)
    mocker.patch("gapbf.main._generate_sample_paths", return_value=iter([["1", "2", "3", "4"]]))

    result = runner.invoke(app, ["run", "--mode", "p", "--dry-run"])

    assert result.exit_code == 0
    assert "Dry Run" in result.stdout
    assert "1234" in result.stdout


def test_legacy_root_options_still_run_dry_run(mocker):
    config = Config(grid_size=3, path_min_length=4, path_max_length=5)
    mocker.patch("gapbf.main.Config.load_config", return_value=config)
    path_finder = mocker.Mock()
    path_finder.total_paths = 7
    path_finder.calculate_total_paths_async.return_value = mocker.Mock(
        done=lambda: True, result=lambda: 7
    )
    mocker.patch("gapbf.main.PathFinder", return_value=path_finder)
    mocker.patch("gapbf.main._generate_sample_paths", return_value=iter([]))

    result = runner.invoke(app, ["--mode", "p", "--dry-run"])

    assert result.exit_code == 0
    assert "Dry Run" in result.stdout


def test_history_command_renders_recent_runs(tmp_path):
    db_path = tmp_path / "gapbf.db"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "grid_size: 3",
                "path_min_length: 4",
                "path_max_length: 9",
                f"db_path: {db_path}",
            ]
        ),
        encoding="utf-8",
    )

    config = Config.load_config(str(config_path))
    database = RunDatabase(str(db_path))
    run = database.create_run(config, "SERIAL123", "a")
    database.log_attempt(run.run_id, "1234", "Failed to decrypt", "normal_failure", 0, 12.0)
    database.finish_run(run.run_id, "completed")
    database.close()

    result = runner.invoke(app, ["history", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "Recent Runs" in result.stdout
    assert "SERIAL123" in result.stdout
    assert "completed" in result.stdout


def test_check_device_command_renders_connected_device(mocker):
    config = Config(grid_size=3, path_min_length=4, path_max_length=9, adb_timeout=30)
    mocker.patch("gapbf.main.Config.load_config", return_value=config)
    mocker.patch("gapbf.main.detect_device_id", return_value="SERIAL123")

    result = runner.invoke(app, ["check-device"])

    assert result.exit_code == 0
    assert "ADB Device" in result.stdout
    assert "SERIAL123" in result.stdout


def test_web_command_prints_serving_url(mocker):
    serve_web_ui = mocker.patch("gapbf.web.serve_web_ui")

    result = runner.invoke(app, ["web", "--host", "127.0.0.1", "--port", "8123"])

    assert result.exit_code == 0
    assert "Serving GAPBF web UI at http://127.0.0.1:8123" in result.stdout
    assert "Press Ctrl+C to stop the server" in result.stdout
    serve_web_ui.assert_called_once_with(
        host="127.0.0.1",
        port=8123,
        config_path="config.yaml",
        log_level="error",
        log_file=None,
    )


def test_status_command_renders_resume_state(mocker):
    config = Config(
        grid_size=3, path_min_length=4, path_max_length=9, db_path="test.db", adb_timeout=30
    )
    mocker.patch("gapbf.main.Config.load_config", return_value=config)
    mocker.patch("gapbf.main._should_auto_count_status_totals", return_value=True)
    path_finder = mocker.Mock()
    future = mocker.Mock()
    future.done.return_value = True
    future.result.return_value = 389112
    path_finder.calculate_total_paths_async.return_value = future
    mocker.patch("gapbf.main.create_path_finder", return_value=path_finder)
    mocker.patch(
        "gapbf.main.load_resume_context",
        return_value=mocker.Mock(
            device_id="SERIAL123",
            resume_info=ResumeInfo(
                attempted_count=25,
                latest_run_id="run-1",
                latest_started_at="2026-03-18T10:00:00+00:00",
                latest_finished_at=None,
                latest_status="running",
                latest_successful_attempt=None,
            ),
        ),
    )

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "GAPBF Live Status" in result.stdout
    assert "SERIAL123" in result.stdout
    assert "running" in result.stdout
    assert "25" in result.stdout
    assert "389,112" in result.stdout


def test_status_command_uses_configured_total_paths_without_calculating(mocker):
    config = Config(
        grid_size=5,
        path_min_length=4,
        path_max_length=20,
        db_path="test.db",
        adb_timeout=30,
        total_paths=123456,
    )
    mocker.patch("gapbf.main.Config.load_config", return_value=config)
    path_finder = mocker.Mock()
    mocker.patch("gapbf.main.create_path_finder", return_value=path_finder)
    mocker.patch(
        "gapbf.main.load_resume_context",
        return_value=mocker.Mock(
            device_id="SERIAL123",
            resume_info=ResumeInfo(
                attempted_count=0,
                latest_run_id=None,
                latest_started_at=None,
                latest_finished_at=None,
                latest_status=None,
                latest_successful_attempt=None,
            ),
        ),
    )

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "123,456" in result.stdout
    path_finder.calculate_total_paths_async.assert_not_called()


def test_status_command_can_force_total_path_calculation(mocker):
    config = Config(
        grid_size=3,
        path_min_length=4,
        path_max_length=9,
        db_path="test.db",
        adb_timeout=30,
        total_paths=0,
    )
    mocker.patch("gapbf.main.Config.load_config", return_value=config)
    path_finder = mocker.Mock()
    future = mocker.Mock()
    future.done.return_value = True
    future.result.return_value = 389112
    path_finder.calculate_total_paths_async.return_value = future
    mocker.patch("gapbf.main.create_path_finder", return_value=path_finder)
    mocker.patch(
        "gapbf.main.load_resume_context",
        return_value=mocker.Mock(
            device_id="SERIAL123",
            resume_info=ResumeInfo(
                attempted_count=0,
                latest_run_id=None,
                latest_started_at=None,
                latest_finished_at=None,
                latest_status=None,
                latest_successful_attempt=None,
            ),
        ),
    )

    result = runner.invoke(app, ["status", "--calculate-total-paths"])

    assert result.exit_code == 0
    assert "389,112" in result.stdout


def test_status_command_skips_background_total_counting_when_non_interactive(mocker):
    config = Config(
        grid_size=3,
        path_min_length=4,
        path_max_length=9,
        db_path="test.db",
        adb_timeout=30,
        total_paths=0,
    )
    mocker.patch("gapbf.main.Config.load_config", return_value=config)
    mocker.patch("gapbf.main._should_auto_count_status_totals", return_value=False)
    path_finder = mocker.Mock()
    mocker.patch("gapbf.main.create_path_finder", return_value=path_finder)
    mocker.patch(
        "gapbf.main.load_resume_context",
        return_value=mocker.Mock(
            device_id="SERIAL123",
            resume_info=ResumeInfo(
                attempted_count=0,
                latest_run_id=None,
                latest_started_at=None,
                latest_finished_at=None,
                latest_status=None,
                latest_successful_attempt=None,
            ),
        ),
    )

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "Unknown" in result.stdout
    path_finder.calculate_total_paths_async.assert_not_called()


def test_run_command_uses_live_total_counting_without_touching_pathfinder_total_paths(mocker):
    config = Config(grid_size=3, path_min_length=4, path_max_length=5, total_paths=0)
    mocker.patch("gapbf.main.Config.load_config", return_value=config)
    path_finder = mocker.MagicMock()
    future = mocker.Mock()
    future.done.return_value = True
    future.result.return_value = 42
    path_finder.calculate_total_paths_async.return_value = future
    path_finder.__iter__.return_value = iter([])
    path_finder.handlers = []
    session = mocker.Mock()
    session.path_finder = path_finder
    session.resume_info = None
    session.device_id = None
    session.run_id = None
    session.database = None
    session.attach_state.side_effect = lambda _state: None
    session.finish.side_effect = lambda *_args, **_kwargs: None
    mocker.patch("gapbf.main.open_run_session", return_value=session)

    result = runner.invoke(app, ["run", "--mode", "p"])

    assert result.exit_code == 0
    assert "GAPBF Live Run" in result.stdout
    path_finder.calculate_total_paths_async.assert_called_once()


def test_handle_live_keypress_toggles_pause_for_run():
    state = LiveRunState(config=Config(grid_size=3, path_min_length=4, path_max_length=5), mode="p")
    state.set_search_status("Running")

    should_close = _handle_live_keypress(state, "p", allow_pause=True)

    snapshot = state.snapshot()
    assert should_close is False
    assert snapshot["paused"] is True
    assert snapshot["search_status"] == "Paused"
    assert snapshot["last_feedback"] == "Run paused"


def test_handle_live_keypress_toggles_help():
    state = LiveRunState(config=Config(grid_size=3, path_min_length=4, path_max_length=5), mode="p")

    should_close = _handle_live_keypress(state, "h", allow_pause=True)

    snapshot = state.snapshot()
    assert should_close is False
    assert snapshot["show_help"] is True
    assert snapshot["last_feedback"] == "Controls help shown"


def test_handle_live_keypress_requests_quit_for_run_without_closing_view():
    state = LiveRunState(config=Config(grid_size=3, path_min_length=4, path_max_length=5), mode="a")

    should_close = _handle_live_keypress(state, "q", allow_pause=True)

    snapshot = state.snapshot()
    assert should_close is False
    assert snapshot["quit_requested"] is True
    assert snapshot["search_status"] == "Stopping"
    assert snapshot["last_feedback"] == "Stop requested. Waiting for the current attempt to finish"


def test_handle_live_keypress_closes_status_view():
    state = LiveRunState(config=Config(grid_size=3, path_min_length=4, path_max_length=5), mode="a")

    should_close = _handle_live_keypress(state, "q", allow_pause=False)

    snapshot = state.snapshot()
    assert should_close is True
    assert snapshot["quit_requested"] is True
    assert snapshot["last_feedback"] == "Status view closed by user"
