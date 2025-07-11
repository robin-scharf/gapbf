import pytest
import tempfile
import os
import yaml
from unittest.mock import patch, Mock
from Config import Config
from PathFinder import PathFinder
from PathHandler import ADBHandler, TestHandler, PrintHandler


class TestFullIntegration:
    """Integration tests that test the complete system."""
    
    def test_config_to_pathfinder_integration(self):
        """Test that Config integrates properly with PathFinder."""
        # Create a temporary config file
        config_data = {
            'grid_size': 3,
            'path_min_length': 4,
            'path_max_length': 6,
            'path_max_node_distance': 1,
            'path_prefix': [1, 2],
            'path_suffix': [8, 9],
            'excluded_nodes': [5],
            'attempt_delay': 10.0,
            'test_path': [1, 2, 3, 4],
            'outputstrings': {
                'stdout_normal': 'Failed',
                'stdout_success': 'Success',
                'stdout_error': 'Error'
            },
            'paths_log_file_path': './test_paths.csv',
            'process_log_file_path': './test_process.csv',
            'adb_timeout': 30,
            'total_paths': 0
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            config_file = f.name
        
        try:
            # Load config
            config = Config.load_config(config_file)
            
            # Create PathFinder with config values
            pf = PathFinder(
                grid_size=config.grid_size,
                path_min_len=config.path_min_length,
                path_max_len=config.path_max_length,
                path_max_node_distance=config.path_max_node_distance,
                path_prefix=config.path_prefix,
                path_suffix=config.path_suffix,
                excluded_nodes=config.excluded_nodes
            )
            
            # Verify PathFinder uses config values correctly
            assert pf._grid_size == 3
            assert pf._path_min_len == 4
            assert pf._path_max_len == 6
            assert pf._path_prefix == (1, 2)
            assert pf._path_suffix == (8, 9)
            assert pf._excluded_nodes == {5}
            
        finally:
            os.unlink(config_file)

    def test_pathfinder_with_test_handler_integration(self):
        """Test PathFinder working with TestHandler end-to-end."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            config_data = {
                'grid_size': 3,
                'path_min_length': 4,
                'path_max_length': 5,
                'path_prefix': [1],
                'path_suffix': [5],
                'test_path': [1, 2, 3, 4, 5],
                'excluded_nodes': [],
                'outputstrings': {
                    'stdout_normal': 'Failed',
                    'stdout_success': 'Success',
                    'stdout_error': 'Error'
                },
                'paths_log_file_path': './test_paths.csv',
                'total_paths': 0
            }
            yaml.dump(config_data, f)
            config_file = f.name
        
        try:
            with patch('PathHandler.Config.load_config') as mock_load:
                mock_config = Config.load_config(config_file)
                mock_load.return_value = mock_config
                
                # Create PathFinder
                pf = PathFinder(
                    grid_size=3,
                    path_min_len=4,
                    path_max_len=5,
                    path_prefix=[1],
                    path_suffix=[5],
                    excluded_nodes=[]
                )
                
                # Add TestHandler
                test_handler = TestHandler()
                pf.add_handler(test_handler)
                
                # Run DFS - should find the test path
                success, found_path = pf.dfs()
                
                assert success is True
                assert found_path == [1, 2, 3, 4, 5]
                
        finally:
            os.unlink(config_file)

    @patch('subprocess.run')
    def test_pathfinder_with_adb_handler_integration(self, mock_subprocess):
        """Test PathFinder working with ADBHandler (mocked)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            config_data = {
                'grid_size': 3,
                'path_min_length': 4,
                'path_max_length': 4,
                'path_prefix': [1],
                'path_suffix': [],
                'excluded_nodes': [],
                'attempt_delay': 100,
                'outputstrings': {
                    'stdout_normal': 'Failed to decrypt',
                    'stdout_success': 'Data successfully decrypted',
                    'stdout_error': 'Error'
                },
                'paths_log_file_path': './test_paths.csv',
                'adb_timeout': 30,
                'total_paths': 0
            }
            yaml.dump(config_data, f)
            config_file = f.name
        
        try:
            with patch('PathHandler.Config.load_config') as mock_load:
                mock_config = Config.load_config(config_file)
                mock_load.return_value = mock_config
                
                # Mock successful ADB response for specific path
                def mock_adb_response(command, **kwargs):
                    if 'decrypt' in command and '1234' in command:
                        result = Mock()
                        result.returncode = 0
                        result.stdout = 'Data successfully decrypted'
                        result.stderr = ''
                        return result
                    else:
                        result = Mock()
                        result.returncode = 0
                        result.stdout = 'Failed to decrypt'
                        result.stderr = ''
                        return result
                
                mock_subprocess.side_effect = mock_adb_response
                
                # Create PathFinder
                pf = PathFinder(
                    grid_size=3,
                    path_min_len=4,
                    path_max_len=4,
                    path_prefix=[1],
                    path_suffix=[],
                    excluded_nodes=[]
                )
                
                with patch.object(ADBHandler, 'get_attempted_paths', return_value=[]), \
                     patch('PathHandler.LogHandler'):
                    
                    # Add ADBHandler
                    adb_handler = ADBHandler()
                    pf.add_handler(adb_handler)
                    
                    # Run DFS - should find successful path
                    success, found_path = pf.dfs()
                    
                    # Should succeed when it tries path [1, 2, 3, 4]
                    assert success is True
                    assert found_path == [1, 2, 3, 4]
                
        finally:
            os.unlink(config_file)

    def test_multiple_handlers_priority(self):
        """Test that multiple handlers work and first success is returned."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            config_data = {
                'grid_size': 3,
                'path_min_length': 4,
                'path_max_length': 4,
                'test_path': [1, 2, 3, 4],
                'path_prefix': [],
                'path_suffix': [],
                'excluded_nodes': [],
                'outputstrings': {'stdout_normal': 'Failed', 'stdout_success': 'Success', 'stdout_error': 'Error'},
                'paths_log_file_path': './test_paths.csv',
                'total_paths': 0
            }
            yaml.dump(config_data, f)
            config_file = f.name
        
        try:
            with patch('PathHandler.Config.load_config') as mock_load:
                mock_config = Config.load_config(config_file)
                mock_load.return_value = mock_config
                
                pf = PathFinder(
                    grid_size=3,
                    path_min_len=4,
                    path_max_len=4,
                    path_prefix=[],
                    path_suffix=[],
                    excluded_nodes=[]
                )
                
                # Add handlers in order: Print (always fails), Test (succeeds for correct path)
                print_handler = PrintHandler()
                test_handler = TestHandler()
                
                pf.add_handler(print_handler)
                pf.add_handler(test_handler)
                
                # Run DFS
                success, found_path = pf.dfs()
                
                # Should succeed via TestHandler
                assert success is True
                assert found_path == [1, 2, 3, 4]
                
        finally:
            os.unlink(config_file)

    def test_constraint_validation_end_to_end(self):
        """Test that constraints are properly enforced end-to-end."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            config_data = {
                'grid_size': 3,
                'path_min_length': 5,
                'path_max_length': 5,
                'path_prefix': [1, 2],
                'path_suffix': [9],
                'excluded_nodes': [5],  # Exclude center node
                'test_path': [1, 2, 3, 6, 9],  # Valid path meeting all constraints
                'outputstrings': {'stdout_normal': 'Failed', 'stdout_success': 'Success', 'stdout_error': 'Error'},
                'paths_log_file_path': './test_paths.csv',
                'total_paths': 0
            }
            yaml.dump(config_data, f)
            config_file = f.name
        
        try:
            with patch('PathHandler.Config.load_config') as mock_load:
                mock_config = Config.load_config(config_file)
                mock_load.return_value = mock_config
                
                pf = PathFinder(
                    grid_size=3,
                    path_min_len=5,
                    path_max_len=5,
                    path_prefix=[1, 2],
                    path_suffix=[9],
                    excluded_nodes=[5]
                )
                
                # Track all attempted paths
                attempted_paths = []
                
                class TrackingHandler(TestHandler):
                    def handle_path(self, path, total_paths=None):
                        attempted_paths.append(path.copy())
                        return super().handle_path(path, total_paths)
                
                tracking_handler = TrackingHandler()
                pf.add_handler(tracking_handler)
                
                success, found_path = pf.dfs()
                
                # Should succeed
                assert success is True
                assert found_path == [1, 2, 3, 6, 9]
                
                # Verify all attempted paths meet constraints
                for path in attempted_paths:
                    assert len(path) == 5  # Exact length
                    assert path[0] == 1 and path[1] == 2  # Prefix
                    assert path[-1] == 9  # Suffix
                    assert 5 not in path  # Excluded node
                
        finally:
            os.unlink(config_file)


class TestErrorHandling:
    """Test error handling across the system."""
    
    def test_invalid_config_file_handling(self):
        """Test system handles invalid config files gracefully."""
        with pytest.raises(ValueError, match="Configuration file not found"):
            Config.load_config('nonexistent_file.yaml')

    def test_unsupported_grid_size_handling(self):
        """Test system handles unsupported grid sizes gracefully."""
        with pytest.raises(ValueError, match="Unsupported grid size"):
            PathFinder(grid_size=10, path_min_len=4, path_max_len=9)

    def test_impossible_constraints_handling(self):
        """Test system handles impossible constraints gracefully."""
        pf = PathFinder(
            grid_size=3,
            path_min_len=20,  # Impossible for 3x3 grid
            path_max_len=25,
            path_prefix=[],
            path_suffix=[],
            excluded_nodes=[]
        )
        
        with pytest.raises(ValueError, match="No paths found with the given configuration"):
            pf._calculate_total_paths()

    @patch('subprocess.run')
    def test_adb_subprocess_error_handling(self, mock_subprocess):
        """Test ADB handler handles subprocess errors gracefully."""
        mock_subprocess.side_effect = Exception("ADB not found")
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            config_data = {
                'grid_size': 3,
                'outputstrings': {'stdout_normal': 'Failed', 'stdout_success': 'Success', 'stdout_error': 'Error'},
                'paths_log_file_path': './test_paths.csv',
                'adb_timeout': 30,
                'attempt_delay': 100,
                'total_paths': 100
            }
            yaml.dump(config_data, f)
            config_file = f.name
        
        try:
            with patch('PathHandler.Config.load_config') as mock_load:
                mock_config = Config.load_config(config_file)
                mock_load.return_value = mock_config
                
                with patch.object(ADBHandler, 'get_attempted_paths', return_value=[]), \
                     patch('sys.exit') as mock_exit:
                    
                    handler = ADBHandler()
                    handler.handle_path([1, 2, 3])
                    
                    # Should exit on subprocess error
                    mock_exit.assert_called_once_with(1)
                    
        finally:
            os.unlink(config_file)
