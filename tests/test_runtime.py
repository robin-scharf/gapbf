import pytest
from rich.console import Console

from gapbf.Config import Config
from gapbf.Database import ResumeInfo
from gapbf.Output import Output
from gapbf.PathFinder import PathFinder
from gapbf.runtime import (
    RunController,
    RunState,
    UserRequestedStop,
    add_handlers,
    execute_path_search,
    load_resume_context,
    open_run_session,
)


def test_execute_path_search_returns_success_for_matching_test_handler():
    config = Config(
        grid_size=3,
        path_min_length=4,
        path_max_length=4,
        path_prefix=["1", "2", "3", "6"],
        path_suffix=["1", "2", "3", "6"],
        test_path=["1", "2", "3", "6"],
    )
    path_finder = PathFinder(
        config.grid_size,
        config.path_min_length,
        config.path_max_length,
        config.path_max_node_distance,
        config.path_prefix,
        config.path_suffix,
        config.excluded_nodes,
    )
    add_handlers(
        path_finder,
        config,
        "t",
        database=None,
        run_id=None,
        device_id=None,
        output=Output(console=Console(), silent=True),
    )

    selected_paths: list[list[str]] = []
    completed_paths: list[list[str]] = []

    success, result_path = execute_path_search(
        path_finder,
        should_stop=lambda: False,
        is_paused=lambda: False,
        total_paths_provider=lambda: 1,
        on_path_selected=lambda path: selected_paths.append(path.copy()),
        on_attempt_completed=lambda path, _success, _result: completed_paths.append(path.copy()),
    )

    assert success is True
    assert result_path == ["1", "2", "3", "6"]
    assert selected_paths == [["1", "2", "3", "6"]]
    assert completed_paths == [["1", "2", "3", "6"]]


def test_execute_path_search_honors_stop_requests():
    config = Config(grid_size=3, path_min_length=4, path_max_length=4, path_prefix=["1", "2"])
    path_finder = PathFinder(
        config.grid_size,
        config.path_min_length,
        config.path_max_length,
        config.path_max_node_distance,
        config.path_prefix,
        config.path_suffix,
        config.excluded_nodes,
    )

    with pytest.raises(UserRequestedStop):
        execute_path_search(
            path_finder,
            should_stop=lambda: True,
            is_paused=lambda: False,
            total_paths_provider=lambda: None,
            on_path_selected=lambda _path: None,
            on_attempt_completed=lambda _path, _success, _result: None,
        )


def test_run_controller_updates_state_on_success():
    config = Config(
        grid_size=3,
        path_min_length=4,
        path_max_length=4,
        path_prefix=["1", "2", "3", "6"],
        path_suffix=["1", "2", "3", "6"],
        test_path=["1", "2", "3", "6"],
    )
    path_finder = PathFinder(
        config.grid_size,
        config.path_min_length,
        config.path_max_length,
        config.path_max_node_distance,
        config.path_prefix,
        config.path_suffix,
        config.excluded_nodes,
    )
    add_handlers(
        path_finder,
        config,
        "t",
        database=None,
        run_id=None,
        device_id=None,
        output=Output(console=Console(), silent=True),
    )
    state = RunState(config=config, mode="t", total_paths=1)
    controller = RunController(state)

    success, result_path = controller.execute_search(path_finder)
    snapshot = state.snapshot()

    assert success is True
    assert result_path == ["1", "2", "3", "6"]
    assert snapshot["paths_tested"] == 1
    assert snapshot["successful_path"] == "1236"
    assert snapshot["last_feedback"] == "Pattern found: 1236"


def test_load_resume_context_uses_shared_persistent_lookup(mocker):
    config = Config(grid_size=3, path_min_length=4, path_max_length=5, db_path="test.db")
    database = mocker.Mock()
    database.get_resume_info.return_value = ResumeInfo(
        attempted_count=3,
        latest_run_id="run-1",
        latest_started_at="2026-03-18T10:00:00+00:00",
        latest_finished_at=None,
        latest_status="running",
        latest_successful_attempt=None,
    )
    mocker.patch("gapbf.runtime.RunDatabase", return_value=database)
    mocker.patch("gapbf.runtime.detect_device_id", return_value="SERIAL123")

    context = load_resume_context(config)

    assert context.device_id == "SERIAL123"
    assert context.resume_info.attempted_count == 3
    database.reconcile_stale_runs.assert_called_once()
    database.close.assert_called_once()


def test_open_run_session_creates_persistent_run_and_attaches_handlers(mocker):
    config = Config(grid_size=3, path_min_length=4, path_max_length=5, db_path="test.db")
    output = Output(console=Console(), silent=True)
    path_finder = mocker.Mock()
    database = mocker.Mock()
    database.get_resume_info.return_value = ResumeInfo(
        attempted_count=2,
        latest_run_id="run-0",
        latest_started_at="2026-03-18T09:00:00+00:00",
        latest_finished_at=None,
        latest_status="interrupted",
        latest_successful_attempt="1236",
    )
    database.create_run.return_value = mocker.Mock(run_id="run-1")
    mocker.patch("gapbf.runtime.create_path_finder", return_value=path_finder)
    mocker.patch("gapbf.runtime.RunDatabase", return_value=database)
    mocker.patch("gapbf.runtime.detect_device_id", return_value="SERIAL123")
    add_handlers_mock = mocker.patch("gapbf.runtime.add_handlers")

    session = open_run_session(config, "a", output)

    assert session.path_finder is path_finder
    assert session.database is database
    assert session.run_id == "run-1"
    assert session.device_id == "SERIAL123"
    assert session.resume_info is database.get_resume_info.return_value
    assert session.known_successful_attempt == "1236"
    add_handlers_mock.assert_called_once()
    session.close()
    database.close.assert_called_once()
