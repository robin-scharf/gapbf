import pytest
import yaml
import tempfile
import os
from unittest.mock import patch, mock_open
from gapbf.Config import Config


class TestConfig:
    """Unit tests for the Config class."""
    
    def test_config_init_with_valid_data(self):
        """Test Config initialization with valid data."""
        config = Config(
            config_file_path='test.yaml',
            grid_size=3,
            path_min_length=4,
            path_max_length=9,
            path_max_node_distance=1,
            path_prefix=['1', '2'],
            path_suffix=['8', '9'],
            excluded_nodes=['5'],
            attempt_delay=10.5,
            test_path=['1', '2', '3'],
            stdout_normal='Failed',
            stdout_success='Success',
            stdout_error='Error',
            paths_log_file_path='./paths.csv',
            process_log_file_path='./process.csv',
            adb_timeout=30,
            total_paths=100
        )
        
        assert config.grid_size == 3
        assert config.path_min_length == 4
        assert config.path_max_length == 9
        assert config.attempt_delay == 10.5
        assert config.total_paths == 100

    def test_config_post_init_type_validation(self):
        """Test that Pydantic validates types correctly."""
        from pydantic import ValidationError
        
        # Test invalid grid_size type
        with pytest.raises(ValidationError, match="grid_size"):
            Config(grid_size="invalid")
        
        # Test invalid path_min_length type
        with pytest.raises(ValidationError, match="path_min_length"):
            Config(path_min_length="invalid")
        
        # Test invalid path_max_length type
        with pytest.raises(ValidationError, match="path_max_length"):
            Config(path_max_length="invalid")
        
        # Test invalid attempt_delay type - Pydantic will auto-convert strings to floats if possible
        # So we need a truly invalid value
        with pytest.raises(ValidationError, match="attempt_delay"):
            Config(attempt_delay="not_a_number")
        
        # Test invalid path_prefix items - Pydantic will auto-convert to strings
        # so this will actually succeed, but test that non-list fails
        with pytest.raises(ValidationError, match="path_prefix"):
            Config(path_prefix="not_a_list")

    def test_load_config_success(self):
        """Test successful config loading from YAML file."""
        yaml_content = """
grid_size: 3
path_min_length: 4
path_max_length: 9
path_max_node_distance: 1
path_prefix: [1, 2]
path_suffix: [8, 9]
excluded_nodes: [5]
attempt_delay: 10.5
test_path: [1, 2, 3]
outputstrings:
  stdout_normal: "Failed to decrypt"
  stdout_success: "Data successfully decrypted"
  stdout_error: "Error occurred"
paths_log_file_path: "./paths.csv"
process_log_file_path: "./process.csv"
adb_timeout: 30
total_paths: 100
"""
        
        with patch('builtins.open', mock_open(read_data=yaml_content)):
            config = Config.load_config('test.yaml')
            
            assert config.grid_size == 3
            assert config.path_min_length == 4
            assert config.path_max_length == 9
            assert config.path_prefix == ['1', '2']  # Nodes stored as strings
            assert config.path_suffix == ['8', '9']  # Nodes stored as strings
            assert config.excluded_nodes == ['5']    # Nodes stored as strings
            assert config.attempt_delay == 10.5
            assert config.stdout_normal == "Failed to decrypt"
            assert config.stdout_success == "Data successfully decrypted"

    def test_load_config_file_not_found(self):
        """Test config loading when file doesn't exist."""
        with pytest.raises(ValueError, match="Configuration file not found"):
            Config.load_config('nonexistent.yaml')

    def test_load_config_invalid_yaml(self):
        """Test config loading with invalid YAML format."""
        invalid_yaml = "invalid: yaml: content: ["
        
        with patch('builtins.open', mock_open(read_data=invalid_yaml)):
            with pytest.raises(ValueError, match="Invalid YAML"):
                Config.load_config('test.yaml')

    def test_load_config_with_defaults(self):
        """Test config loading with missing values uses defaults."""
        minimal_yaml = """
grid_size: 4
"""
        
        with patch('builtins.open', mock_open(read_data=minimal_yaml)):
            config = Config.load_config('test.yaml')
            
            assert config.grid_size == 4
            assert config.path_min_length == 4  # Default value
            assert config.path_max_length == 9  # Default from load_config
            assert config.path_prefix == []     # Default value
            assert config.attempt_delay == 0.0  # Default value

    def test_repr_method(self):
        """Test the __repr__ method returns expected format."""
        config = Config(config_file_path='test.yaml')
        # Note: The __repr__ method in the code is defined outside the class
        # so we'll test if it exists and works correctly
        repr_str = repr(config)
        assert 'Config' in repr_str


class TestConfigIntegration:
    """Integration tests for Config with actual file operations."""
    
    def test_load_config_real_file(self):
        """Test loading config from a real temporary file."""
        yaml_content = {
            'grid_size': 3,
            'path_min_length': 4,
            'path_max_length': 9,
            'attempt_delay': 10.5,
            'outputstrings': {
                'stdout_normal': 'Failed',
                'stdout_success': 'Success',
                'stdout_error': 'Error'
            },
            'total_paths': 100
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(yaml_content, f)
            temp_file = f.name
        
        try:
            config = Config.load_config(temp_file)
            assert config.grid_size == 3
            assert config.path_min_length == 4
            assert config.stdout_normal == 'Failed'
            assert config.total_paths == 100
        finally:
            os.unlink(temp_file)
