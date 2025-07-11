import pytest
import tempfile
import os
import yaml
from unittest.mock import Mock, patch


@pytest.fixture
def sample_config_data():
    """Fixture providing sample configuration data."""
    return {
        'grid_size': 3,
        'path_min_length': 4,
        'path_max_length': 9,
        'path_max_node_distance': 1,
        'path_prefix': [],
        'path_suffix': [],
        'excluded_nodes': [],
        'attempt_delay': 10.0,
        'test_path': [1, 2, 3, 4, 5],
        'outputstrings': {
            'stdout_normal': 'Failed to decrypt',
            'stdout_success': 'Data successfully decrypted',
            'stdout_error': 'Error occurred'
        },
        'paths_log_file_path': './test_paths.csv',
        'process_log_file_path': './test_process.csv',
        'adb_timeout': 30,
        'total_paths': 100
    }


@pytest.fixture
def temp_config_file(sample_config_data):
    """Fixture that creates a temporary config file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(sample_config_data, f)
        temp_file = f.name
    
    yield temp_file
    
    # Cleanup
    try:
        os.unlink(temp_file)
    except FileNotFoundError:
        pass


@pytest.fixture
def mock_config():
    """Fixture providing a mock config object."""
    config = Mock()
    config.grid_size = 3
    config.path_min_length = 4
    config.path_max_length = 9
    config.path_max_node_distance = 1
    config.path_prefix = []
    config.path_suffix = []
    config.excluded_nodes = []
    config.attempt_delay = 10.0
    config.test_path = [1, 2, 3, 4, 5]
    config.stdout_normal = 'Failed to decrypt'
    config.stdout_success = 'Data successfully decrypted'
    config.stdout_error = 'Error occurred'
    config.paths_log_file_path = './test_paths.csv'
    config.process_log_file_path = './test_process.csv'
    config.adb_timeout = 30
    config.total_paths = 100
    return config


@pytest.fixture
def mock_successful_subprocess_result():
    """Fixture providing a mock successful subprocess result."""
    result = Mock()
    result.returncode = 0
    result.stdout = 'Data successfully decrypted'
    result.stderr = ''
    return result


@pytest.fixture
def mock_failed_subprocess_result():
    """Fixture providing a mock failed subprocess result."""
    result = Mock()
    result.returncode = 0
    result.stdout = 'Failed to decrypt'
    result.stderr = ''
    return result


@pytest.fixture(autouse=True)
def clean_singletons():
    """Fixture to clean up singleton instances between tests."""
    # Reset Logger singleton
    from Logging import Logger
    Logger._instance = None
    
    yield
    
    # Clean up after test
    Logger._instance = None


@pytest.fixture
def temp_csv_file():
    """Fixture that creates a temporary CSV file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        temp_file = f.name
    
    yield temp_file
    
    # Cleanup
    try:
        os.unlink(temp_file)
    except FileNotFoundError:
        pass
