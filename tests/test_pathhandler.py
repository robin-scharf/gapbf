import subprocess
import pytest
from unittest.mock import Mock, patch
from rich.console import Console

from gapbf.Config import Config
from gapbf.Output import Output
from gapbf.PathHandler import ADBHandler, PathHandler, PrintHandler, TestHandler as GapbfTestHandler


class TestPathHandlerBase:
    """Tests for the abstract PathHandler base class."""

    def test_pathhandler_init_uses_provided_config(self):
        class ConcreteHandler(PathHandler):
            def handle_path(self, path, total_paths=None):
                return False, None

        config = Config(grid_size=3, path_min_length=4, path_max_length=9)
        handler = ConcreteHandler(config, Output(Console(record=True)))
        assert handler.config == config


class TestADBHandler:
    """Tests for the ADBHandler class."""

    def test_adbhandler_init_starts_server_and_loads_attempts(self, mocker):
        config = Config(
            grid_size=3,
            path_min_length=4,
            path_max_length=9,
            stdout_normal='Failed',
            stdout_success='Success',
            stdout_error='Error',
            adb_timeout=30,
        )
        database = mocker.Mock()
        database.get_attempted_paths.return_value = {'1234'}
        run_result = mocker.Mock(returncode=0, stdout='', stderr='')
        subprocess_run = mocker.patch('gapbf.PathHandler.subprocess.run', return_value=run_result)
        reporter = mocker.Mock()

        handler = ADBHandler(config, database=database, run_id='run-1', device_id='SERIAL123', output=reporter)

        assert handler.current_path_number == 1
        database.get_attempted_paths.assert_called_once_with(config, 'SERIAL123')
        subprocess_run.assert_called_once_with(['adb', 'start-server'], check=True, capture_output=True)

    def test_handle_path_skips_attempted_path(self, mocker):
        config = Config(
            grid_size=3,
            path_min_length=4,
            path_max_length=9,
            stdout_normal='Failed',
            stdout_success='Success',
            stdout_error='Error',
            adb_timeout=30,
        )
        database = mocker.Mock()
        database.get_attempted_paths.return_value = {'123'}
        run_result = mocker.Mock(returncode=0, stdout='', stderr='')
        subprocess_run = mocker.patch('gapbf.PathHandler.subprocess.run', return_value=run_result)
        reporter = mocker.Mock()

        handler = ADBHandler(config, database=database, run_id='run-1', device_id='SERIAL123', output=reporter)
        success, path = handler.handle_path(['1', '2', '3'], total_paths=100)

        assert success is False
        assert path is None
        database.log_attempt.assert_called_once()
        assert subprocess_run.call_count == 1
        reporter.show_adb_skip.assert_called_once()

    def test_handle_path_success(self, mocker):
        config = Config(
            grid_size=3,
            path_min_length=4,
            path_max_length=9,
            stdout_normal='Failed',
            stdout_success='Data successfully decrypted',
            stdout_error='Error',
            adb_timeout=30,
            echo_commands=False,
        )
        database = mocker.Mock()
        database.get_attempted_paths.return_value = set()
        start_result = mocker.Mock(returncode=0, stdout='', stderr='')
        decrypt_result = mocker.Mock(returncode=0, stdout='Data successfully decrypted', stderr='')
        subprocess_run = mocker.patch('gapbf.PathHandler.subprocess.run', side_effect=[start_result, decrypt_result])
        reporter = mocker.Mock()

        handler = ADBHandler(config, database=database, run_id='run-1', device_id='SERIAL123', output=reporter)
        success, path = handler.handle_path(['1', '2', '3'], total_paths=100)

        assert success is True
        assert path == ['1', '2', '3']
        subprocess_run.assert_any_call(
            ['adb', 'shell', 'twrp', 'decrypt', '123'],
            capture_output=True,
            text=True,
            timeout=30,
        )
        database.log_attempt.assert_called_once()
        reporter.show_adb_success.assert_called_once_with(['1', '2', '3'])

    def test_handle_path_timeout(self, mocker):
        config = Config(
            grid_size=3,
            path_min_length=4,
            path_max_length=9,
            stdout_normal='Failed',
            stdout_success='Success',
            stdout_error='Error',
            adb_timeout=30,
        )
        database = mocker.Mock()
        database.get_attempted_paths.return_value = set()
        start_result = mocker.Mock(returncode=0, stdout='', stderr='')
        mocker.patch(
            'gapbf.PathHandler.subprocess.run',
            side_effect=[start_result, subprocess.TimeoutExpired(cmd='adb', timeout=30)],
        )
        reporter = mocker.Mock()

        handler = ADBHandler(config, database=database, run_id='run-1', device_id='SERIAL123', output=reporter)
        success, path = handler.handle_path(['1', '2', '3'], total_paths=100)

        assert success is False
        assert path is None
        database.log_attempt.assert_called_once()
        reporter.show_adb_timeout.assert_called_once()


class TestTestHandler:
    """Tests for the TestHandler class."""

    def test_testhandler_init(self):
        config = Config(
            grid_size=3,
            path_min_length=4,
            path_max_length=9,
            test_path=['1', '2', '3', '4', '5'],
            path_prefix=['1', '2'],
            path_suffix=['4', '5'],
            excluded_nodes=['6', '7'],
        )
        handler = GapbfTestHandler(config, Mock())
        assert handler.test_path == ['1', '2', '3', '4', '5']

    def test_handle_path_success(self):
        config = Config(grid_size=3, path_min_length=4, path_max_length=9, test_path=['1', '2', '3', '4', '5'])
        reporter = Mock()
        handler = GapbfTestHandler(config, reporter)

        success, path = handler.handle_path(['1', '2', '3', '4', '5'])

        assert success is True
        assert path == ['1', '2', '3', '4', '5']
        reporter.show_test_result.assert_called_once()

    def test_handle_path_failure(self):
        config = Config(grid_size=3, path_min_length=4, path_max_length=9, test_path=['1', '2', '3', '4', '5'])
        reporter = Mock()
        handler = GapbfTestHandler(config, reporter)

        success, path = handler.handle_path(['1', '2', '3'])

        assert success is False
        assert path is None
        reporter.show_test_result.assert_called_once()


class TestPrintHandler:
    """Tests for the PrintHandler class."""

    def test_printhandler_init(self):
        config = Config(grid_size=3, path_min_length=4, path_max_length=9)
        grid_nodes = ['1', '2', '3', '4', '5', '6', '7', '8', '9']
        handler = PrintHandler(config, grid_nodes, Mock())
        assert handler.grid_size == 3

    def test_handle_path_prints_grid(self):
        config = Config(grid_size=3, path_min_length=4, path_max_length=9)
        grid_nodes = ['1', '2', '3', '4', '5', '6', '7', '8', '9']
        reporter = Mock()
        handler = PrintHandler(config, grid_nodes, reporter)

        success, path = handler.handle_path(['1', '2', '3'])

        assert success is False
        assert path is None
        reporter.show_print_path.assert_called_once()

    def test_render_path_3x3(self):
        config = Config(grid_size=3, path_min_length=4, path_max_length=9)
        grid_nodes = ['1', '2', '3', '4', '5', '6', '7', '8', '9']
        handler = PrintHandler(config, grid_nodes, Mock())
        grid_rows = handler.render_path(['1', '5', '9'])

        assert len(grid_rows) == 3
        assert '●' in grid_rows[0]
        assert '●' in grid_rows[1]
        assert '●' in grid_rows[2]
