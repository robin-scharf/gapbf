from pathlib import Path

import pytest
from typer.testing import CliRunner

from gapbf.Config import Config
from gapbf.Database import ResumeInfo, RunDatabase
from gapbf.main import app, handler_classes, validate_mode


runner = CliRunner()


def test_validate_mode_accepts_supported_combinations():
    assert validate_mode('a') == 'a'
    assert validate_mode('p') == 'p'
    assert validate_mode('t') == 't'
    assert validate_mode('ap') == 'ap'
    assert validate_mode('apt') == 'apt'


def test_validate_mode_rejects_invalid_modes():
    with pytest.raises(Exception, match='Invalid mode'):
        validate_mode('x')

    with pytest.raises(Exception, match='Invalid mode'):
        validate_mode('az')


def test_handler_classes_define_expected_handlers():
    assert set(handler_classes) == {'a', 'p', 't'}
    assert handler_classes['a']['class'].__name__ == 'ADBHandler'
    assert handler_classes['p']['class'].__name__ == 'PrintHandler'
    assert handler_classes['t']['class'].__name__ == 'TestHandler'


def test_run_command_dry_run_uses_command_surface(mocker):
    config = Config(grid_size=3, path_min_length=4, path_max_length=5)
    mocker.patch('gapbf.main.Config.load_config', return_value=config)
    path_finder = mocker.Mock()
    path_finder.total_paths = 42
    mocker.patch('gapbf.main.PathFinder', return_value=path_finder)
    mocker.patch('gapbf.main._generate_sample_paths', return_value=iter([['1', '2', '3', '4']]))

    result = runner.invoke(app, ['run', '--mode', 'p', '--dry-run'])

    assert result.exit_code == 0
    assert 'Dry Run' in result.stdout
    assert '1234' in result.stdout


def test_legacy_root_options_still_run_dry_run(mocker):
    config = Config(grid_size=3, path_min_length=4, path_max_length=5)
    mocker.patch('gapbf.main.Config.load_config', return_value=config)
    path_finder = mocker.Mock()
    path_finder.total_paths = 7
    mocker.patch('gapbf.main.PathFinder', return_value=path_finder)
    mocker.patch('gapbf.main._generate_sample_paths', return_value=iter([]))

    result = runner.invoke(app, ['--mode', 'p', '--dry-run'])

    assert result.exit_code == 0
    assert 'Dry Run' in result.stdout


def test_history_command_renders_recent_runs(tmp_path):
    db_path = tmp_path / 'gapbf.db'
    config_path = tmp_path / 'config.yaml'
    config_path.write_text(
        '\n'.join([
            'grid_size: 3',
            'path_min_length: 4',
            'path_max_length: 9',
            f'db_path: {db_path}',
        ]),
        encoding='utf-8',
    )

    config = Config.load_config(str(config_path))
    database = RunDatabase(str(db_path))
    run = database.create_run(config, 'SERIAL123', 'a')
    database.log_attempt(run.run_id, '1234', 'Failed to decrypt', 'normal_failure', 0, 12.0)
    database.finish_run(run.run_id, 'completed')
    database.close()

    result = runner.invoke(app, ['history', '--config', str(config_path)])

    assert result.exit_code == 0
    assert 'Recent Runs' in result.stdout
    assert 'SERIAL123' in result.stdout
    assert 'completed' in result.stdout


def test_check_device_command_renders_connected_device(mocker):
    config = Config(grid_size=3, path_min_length=4, path_max_length=9, adb_timeout=30)
    mocker.patch('gapbf.main.Config.load_config', return_value=config)
    mocker.patch('gapbf.main.detect_device_id', return_value='SERIAL123')

    result = runner.invoke(app, ['check-device'])

    assert result.exit_code == 0
    assert 'ADB Device' in result.stdout
    assert 'SERIAL123' in result.stdout


def test_status_command_renders_resume_state(mocker):
    config = Config(grid_size=3, path_min_length=4, path_max_length=9, db_path='test.db', adb_timeout=30)
    mocker.patch('gapbf.main.Config.load_config', return_value=config)
    path_finder = mocker.Mock()
    path_finder.total_paths = 389112
    mocker.patch('gapbf.main.PathFinder', return_value=path_finder)
    mocker.patch('gapbf.main.detect_device_id', return_value='SERIAL123')
    database = mocker.Mock()
    database.get_resume_info.return_value = ResumeInfo(
        attempted_count=25,
        latest_run_id='run-1',
        latest_started_at='2026-03-18T10:00:00+00:00',
        latest_finished_at=None,
        latest_status='running',
        latest_successful_attempt=None,
    )
    mocker.patch('gapbf.main.RunDatabase', return_value=database)

    result = runner.invoke(app, ['status'])

    assert result.exit_code == 0
    assert 'GAPBF Run Summary' in result.stdout
    assert 'SERIAL123' in result.stdout
    assert 'running' in result.stdout
    assert '25' in result.stdout
