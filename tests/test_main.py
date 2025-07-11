import pytest
import sys
from unittest.mock import patch, Mock, MagicMock
import argparse


class TestMainModule:
    """Tests for the main.py module functionality."""
    
    @patch('main.Config.load_config')
    @patch('main.PathFinder')
    def test_main_imports_and_initialization(self, mock_pathfinder, mock_load_config):
        """Test that main.py imports and initializes components correctly."""
        mock_config = Mock()
        mock_config.grid_size = 3
        mock_config.path_min_length = 4
        mock_config.path_max_length = 9
        mock_config.path_max_node_distance = 1
        mock_config.path_prefix = []
        mock_config.path_suffix = []
        mock_config.excluded_nodes = []
        mock_load_config.return_value = mock_config
        
        # Import main to trigger module-level initialization
        import main
        
        # Verify config was loaded
        mock_load_config.assert_called_once_with('config.yaml')
        
        # Verify PathFinder was initialized with config values
        mock_pathfinder.assert_called_once_with(
            3, 4, 9, 1, [], [], []
        )

    def test_validate_mode_valid_modes(self):
        """Test validate_mode function with valid mode combinations."""
        from main import validate_mode
        
        # Test single valid modes
        assert validate_mode('a') == 'a'
        assert validate_mode('p') == 'p'
        assert validate_mode('t') == 't'
        
        # Test valid combinations
        assert validate_mode('ap') == 'ap'
        assert validate_mode('apt') == 'apt'

    def test_validate_mode_invalid_modes(self):
        """Test validate_mode function with invalid modes."""
        from main import validate_mode
        
        with pytest.raises(argparse.ArgumentTypeError, match="Invalid mode"):
            validate_mode('x')  # Invalid single mode
        
        with pytest.raises(argparse.ArgumentTypeError, match="Invalid mode"):
            validate_mode('az')  # Mix of valid and invalid

    @patch('main.Config.load_config')
    @patch('main.PathFinder')
    @patch('sys.argv', ['main.py', '-m', 'p'])
    def test_argument_parsing_print_mode(self, mock_pathfinder, mock_load_config):
        """Test argument parsing for print mode."""
        mock_config = Mock()
        mock_load_config.return_value = mock_config
        
        mock_pf = Mock()
        mock_pf.total_paths = 100
        mock_pf.dfs.return_value = (True, [1, 2, 3, 4])
        mock_pathfinder.return_value = mock_pf
        
        # Reimport to trigger argument parsing
        import importlib
        if 'main' in sys.modules:
            del sys.modules['main']
        
        with patch('builtins.print'):
            import main
        
        # Verify PrintHandler was added
        mock_pf.add_handler.assert_called_once()
        handler_arg = mock_pf.add_handler.call_args[0][0]
        assert handler_arg.__class__.__name__ == 'PrintHandler'

    @patch('main.Config.load_config')
    @patch('main.PathFinder')
    @patch('sys.argv', ['main.py', '-m', 't'])
    def test_argument_parsing_test_mode(self, mock_pathfinder, mock_load_config):
        """Test argument parsing for test mode."""
        mock_config = Mock()
        mock_load_config.return_value = mock_config
        
        mock_pf = Mock()
        mock_pf.total_paths = 100
        mock_pf.dfs.return_value = (True, [1, 2, 3, 4])
        mock_pathfinder.return_value = mock_pf
        
        # Reimport to trigger argument parsing
        if 'main' in sys.modules:
            del sys.modules['main']
        
        with patch('builtins.print'):
            import main
        
        # Verify TestHandler was added
        mock_pf.add_handler.assert_called_once()
        handler_arg = mock_pf.add_handler.call_args[0][0]
        assert handler_arg.__class__.__name__ == 'TestHandler'

    @patch('main.Config.load_config')
    @patch('main.PathFinder')
    @patch('subprocess.run')  # Mock ADB handler's subprocess calls
    @patch('sys.argv', ['main.py', '-m', 'a'])
    def test_argument_parsing_adb_mode(self, mock_subprocess, mock_pathfinder, mock_load_config):
        """Test argument parsing for ADB mode."""
        mock_config = Mock()
        mock_config.stdout_normal = 'Failed'
        mock_config.stdout_success = 'Success'
        mock_config.stdout_error = 'Error'
        mock_config.attempt_delay = 1000
        mock_config.paths_log_file_path = './test.csv'
        mock_config.adb_timeout = 30
        mock_config.total_paths = 100
        mock_load_config.return_value = mock_config
        
        mock_pf = Mock()
        mock_pf.total_paths = 100
        mock_pf.dfs.return_value = (True, [1, 2, 3, 4])
        mock_pathfinder.return_value = mock_pf
        
        # Reimport to trigger argument parsing
        if 'main' in sys.modules:
            del sys.modules['main']
        
        with patch('builtins.print'), \
             patch('PathHandler.ADBHandler.get_attempted_paths', return_value=[]):
            import main
        
        # Verify ADBHandler was added
        mock_pf.add_handler.assert_called_once()
        handler_arg = mock_pf.add_handler.call_args[0][0]
        assert handler_arg.__class__.__name__ == 'ADBHandler'

    @patch('main.Config.load_config')
    @patch('main.PathFinder')
    @patch('sys.argv', ['main.py', '-m', 'ap'])
    def test_multiple_handlers(self, mock_pathfinder, mock_load_config):
        """Test adding multiple handlers."""
        mock_config = Mock()
        mock_config.stdout_normal = 'Failed'
        mock_config.stdout_success = 'Success'
        mock_config.stdout_error = 'Error'
        mock_config.attempt_delay = 1000
        mock_config.paths_log_file_path = './test.csv'
        mock_config.adb_timeout = 30
        mock_config.total_paths = 100
        mock_load_config.return_value = mock_config
        
        mock_pf = Mock()
        mock_pf.total_paths = 100
        mock_pf.dfs.return_value = (True, [1, 2, 3, 4])
        mock_pathfinder.return_value = mock_pf
        
        # Reimport to trigger argument parsing
        if 'main' in sys.modules:
            del sys.modules['main']
        
        with patch('builtins.print'), \
             patch('PathHandler.ADBHandler.get_attempted_paths', return_value=[]), \
             patch('subprocess.run'):
            import main
        
        # Verify both handlers were added
        assert mock_pf.add_handler.call_count == 2
        
        # Get the handler types
        handler_calls = mock_pf.add_handler.call_args_list
        handler_types = [call[0][0].__class__.__name__ for call in handler_calls]
        
        assert 'ADBHandler' in handler_types
        assert 'PrintHandler' in handler_types

    @patch('main.Config.load_config')
    @patch('main.PathFinder')
    @patch('sys.argv', ['main.py', '-m', 'p'])
    def test_successful_path_found(self, mock_pathfinder, mock_load_config):
        """Test main execution when successful path is found."""
        mock_config = Mock()
        mock_load_config.return_value = mock_config
        
        mock_pf = Mock()
        mock_pf.total_paths = 100
        mock_pf.dfs.return_value = (True, [1, 2, 3, 4, 5])
        mock_pathfinder.return_value = mock_pf
        
        # Reimport to trigger execution
        if 'main' in sys.modules:
            del sys.modules['main']
        
        with patch('builtins.print') as mock_print:
            import main
        
        # Verify success message was printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        success_printed = any('Success! The path is: [1, 2, 3, 4, 5]' in call for call in print_calls)
        assert success_printed

    @patch('main.Config.load_config')
    @patch('main.PathFinder')
    @patch('sys.argv', ['main.py', '-m', 'p'])
    def test_no_successful_path_found(self, mock_pathfinder, mock_load_config):
        """Test main execution when no successful path is found."""
        mock_config = Mock()
        mock_load_config.return_value = mock_config
        
        mock_pf = Mock()
        mock_pf.total_paths = 100
        mock_pf.dfs.return_value = (False, [])
        mock_pathfinder.return_value = mock_pf
        
        # Reimport to trigger execution
        if 'main' in sys.modules:
            del sys.modules['main']
        
        with patch('builtins.print') as mock_print:
            import main
        
        # Verify failure message was printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        failure_printed = any('Reached end of paths to try' in call for call in print_calls)
        assert failure_printed

    @patch('sys.argv', ['main.py', '-m', 'invalid'])
    def test_invalid_mode_argument(self):
        """Test that invalid mode arguments are handled."""
        # Reimport to trigger argument parsing
        if 'main' in sys.modules:
            del sys.modules['main']
        
        with patch('sys.exit') as mock_exit:
            try:
                import main
            except SystemExit:
                pass
        
        # Should exit due to invalid argument
        mock_exit.assert_called_with(1)

    @patch('main.Config.load_config')
    @patch('main.PathFinder')
    @patch('sys.argv', ['main.py', '-m', 'x'])  # Invalid mode
    def test_unrecognized_mode_warning(self, mock_pathfinder, mock_load_config):
        """Test warning for unrecognized mode that passes validation."""
        mock_config = Mock()
        mock_load_config.return_value = mock_config
        
        mock_pf = Mock()
        mock_pf.total_paths = 100
        mock_pf.dfs.return_value = (False, [])
        mock_pathfinder.return_value = mock_pf
        
        # This test would need to bypass the validation - it's more of an edge case
        # The validation should catch invalid modes, but this tests the fallback

    @patch('main.Config.load_config')
    @patch('main.PathFinder')
    @patch('sys.argv', ['main.py', '-m', 'p', '-l', 'debug'])
    def test_logging_level_argument(self, mock_pathfinder, mock_load_config):
        """Test that logging level argument is parsed correctly."""
        mock_config = Mock()
        mock_load_config.return_value = mock_config
        
        mock_pf = Mock()
        mock_pf.total_paths = 100
        mock_pf.dfs.return_value = (False, [])
        mock_pathfinder.return_value = mock_pf
        
        # Reimport to trigger argument parsing
        if 'main' in sys.modules:
            del sys.modules['main']
        
        with patch('builtins.print'):
            import main
        
        # This mainly tests that the argument is accepted without error
        # The actual logging configuration would be tested in the Logging module tests


class TestMainExecution:
    """Tests for main execution flow."""
    
    @patch('main.Config.load_config')
    @patch('main.PathFinder')
    def test_handler_classes_dict(self, mock_pathfinder, mock_load_config):
        """Test that handler_classes dictionary is correctly defined."""
        mock_config = Mock()
        mock_load_config.return_value = mock_config
        
        import main
        
        expected_handlers = ['a', 'p', 't']
        for handler_key in expected_handlers:
            assert handler_key in main.handler_classes
            assert 'class' in main.handler_classes[handler_key]
            assert 'help' in main.handler_classes[handler_key]
        
        # Verify handler classes
        assert main.handler_classes['a']['class'].__name__ == 'ADBHandler'
        assert main.handler_classes['p']['class'].__name__ == 'PrintHandler'
        assert main.handler_classes['t']['class'].__name__ == 'TestHandler'
