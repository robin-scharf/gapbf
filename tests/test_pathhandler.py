import pytest
import csv
import os
import tempfile
import subprocess
from unittest.mock import Mock, patch, mock_open, MagicMock
from datetime import datetime
from gapbf.PathHandler import PathHandler, ADBHandler, TestHandler, PrintHandler, LogHandler


class TestPathHandlerBase:
    """Tests for the abstract PathHandler base class."""
    
    @patch('gapbf.PathHandler.Config.load_config')
    def test_pathhandler_init(self, mock_load_config):
        """Test PathHandler initialization loads config."""
        mock_config = Mock()
        mock_load_config.return_value = mock_config
        
        # Create a concrete implementation for testing
        class ConcreteHandler(PathHandler):
            def handle_path(self, path, total_paths=None):
                return False, None
        
        handler = ConcreteHandler()
        assert handler.config == mock_config
        mock_load_config.assert_called_once_with('config.yaml')

    @patch('gapbf.PathHandler.Config.load_config')
    def test_get_attempted_paths_creates_file(self, mock_load_config):
        """Test get_attempted_paths creates CSV file if it doesn't exist."""
        mock_config = Mock()
        mock_config.paths_log_file_path = './test_paths.csv'
        mock_load_config.return_value = mock_config
        
        class ConcreteHandler(PathHandler):
            def handle_path(self, path, total_paths=None):
                return False, None
        
        with patch('os.path.isfile', return_value=False), \
             patch('builtins.open', mock_open()) as mock_file:
            
            handler = ConcreteHandler()
            paths = handler.get_attempted_paths()
            
            # Should create file and write header
            mock_file.assert_called()
            assert paths == []

    @patch('gapbf.PathHandler.Config.load_config')
    def test_get_attempted_paths_reads_existing_file(self, mock_load_config):
        """Test get_attempted_paths reads from existing CSV file."""
        mock_config = Mock()
        mock_config.paths_log_file_path = './test_paths.csv'
        mock_load_config.return_value = mock_config
        
        csv_content = "timestamp,path,result\n2023-01-01 12:00:00,[1,2,3],failed\n2023-01-01 12:01:00,[4,5,6],failed\n"
        
        class ConcreteHandler(PathHandler):
            def handle_path(self, path, total_paths=None):
                return False, None
        
        with patch('os.path.isfile', return_value=True), \
             patch('builtins.open', mock_open(read_data=csv_content)):
            
            handler = ConcreteHandler()
            paths = handler.get_attempted_paths()
            
            assert '[1,2,3]' in paths
            assert '[4,5,6]' in paths
            assert len(paths) == 2


class TestADBHandler:
    """Tests for the ADBHandler class."""
    
    @patch('gapbf.PathHandler.Config.load_config')
    @patch('subprocess.run')
    def test_adbhandler_init_starts_adb_server(self, mock_subprocess, mock_load_config):
        """Test ADBHandler initialization starts ADB server."""
        mock_config = Mock()
        mock_config.stdout_normal = 'Failed'
        mock_config.stdout_success = 'Success'
        mock_config.stdout_error = 'Error'
        mock_config.attempt_delay = 1000
        mock_config.paths_log_file_path = './test.csv'
        mock_config.adb_timeout = 30
        mock_config.total_paths = 100
        mock_load_config.return_value = mock_config
        
        with patch.object(ADBHandler, 'get_attempted_paths', return_value=[]):
            handler = ADBHandler(mock_config)
            
            # Should start ADB server
            mock_subprocess.assert_called_once_with(["adb", "start-server"], check=True)
            assert handler.current_path_number == 0

    @patch('gapbf.PathHandler.Config.load_config')
    @patch('subprocess.run')
    def test_handle_path_skips_attempted_path(self, mock_subprocess, mock_load_config):
        """Test handle_path skips already attempted paths."""
        mock_config = Mock()
        mock_config.stdout_normal = 'Failed'
        mock_config.stdout_success = 'Success' 
        mock_config.stdout_error = 'Error'
        mock_config.attempt_delay = 1000
        mock_config.paths_log_file_path = './test.csv'
        mock_config.adb_timeout = 30
        mock_config.total_paths = 100
        mock_load_config.return_value = mock_config
        
        with patch.object(ADBHandler, 'get_attempted_paths', return_value=['[1, 2, 3]']):
            handler = ADBHandler(mock_config)
            
            success, path = handler.handle_path(['1', '2', '3'], total_paths=100)
            
            assert success is False
            assert path is None
            assert handler.current_path_number == 1

    @patch('gapbf.PathHandler.Config.load_config')
    @patch('subprocess.run')
    @patch('gapbf.PathHandler.LogHandler')
    def test_handle_path_success(self, mock_log_handler, mock_subprocess, mock_load_config):
        """Test handle_path returns success when decrypt succeeds."""
        mock_config = Mock()
        mock_config.stdout_normal = 'Failed'
        mock_config.stdout_success = 'Data successfully decrypted'
        mock_config.stdout_error = 'Error'
        mock_config.attempt_delay = 1000
        mock_config.paths_log_file_path = './test.csv'
        mock_config.adb_timeout = 30
        mock_config.total_paths = 100
        mock_load_config.return_value = mock_config
        
        # Mock successful subprocess result
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = 'Data successfully decrypted'
        mock_result.stderr = ''
        mock_subprocess.return_value = mock_result
        
        with patch.object(ADBHandler, 'get_attempted_paths', return_value=[]):
            handler = ADBHandler(mock_config)
            
            success, path = handler.handle_path(['1', '2', '3'], total_paths=100)
            
            assert success is True
            assert path == [1, 2, 3]
            
            # Should call decrypt command
            mock_subprocess.assert_called_with(
                ["adb", "shell", "twrp", "decrypt", "123"],
                capture_output=True,
                text=True,
                timeout=30
            )

    @patch('gapbf.PathHandler.Config.load_config')
    @patch('subprocess.run')
    def test_handle_path_timeout(self, mock_subprocess, mock_load_config):
        """Test handle_path handles subprocess timeout."""
        mock_config = Mock()
        mock_load_config.return_value = mock_config
        
        mock_subprocess.side_effect = subprocess.TimeoutExpired(cmd='test', timeout=30)
        
        with patch.object(ADBHandler, 'get_attempted_paths', return_value=[]), \
             patch('sys.exit') as mock_exit:
            
            handler = ADBHandler(mock_config)
            handler.handle_path(['1', '2', '3'])
            
            mock_exit.assert_called_once_with(1)


class TestTestHandler:
    """Tests for the TestHandler class."""
    
    @patch('gapbf.PathHandler.Config.load_config')
    def test_testhandler_init(self, mock_load_config):
        """Test TestHandler initialization."""
        mock_config = Mock()
        mock_config.test_path = ['1', '2', '3', '4', '5']  # Nodes as strings
        mock_config.path_prefix = ['1', '2']
        mock_config.path_suffix = ['4', '5']
        mock_config.excluded_nodes = ['6', '7']
        mock_load_config.return_value = mock_config
        
        handler = TestHandler(mock_config)
        
        assert handler.test_path == ['1', '2', '3', '4', '5']

    @patch('gapbf.PathHandler.Config.load_config')
    def test_handle_path_success(self, mock_load_config):
        """Test handle_path returns success for correct test path."""
        mock_config = Mock()
        mock_config.test_path = ['1', '2', '3', '4', '5']
        mock_config.path_prefix = []
        mock_config.path_suffix = []
        mock_config.excluded_nodes = []
        mock_load_config.return_value = mock_config
        
        handler = TestHandler(mock_config)
        
        success, path = handler.handle_path(['1', '2', '3', '4', '5'])
        
        assert success is True
        assert path == ['1', '2', '3', '4', '5']

    @patch('gapbf.PathHandler.Config.load_config')
    def test_handle_path_failure(self, mock_load_config):
        """Test handle_path returns failure for incorrect path."""
        mock_config = Mock()
        mock_config.test_path = ['1', '2', '3', '4', '5']
        mock_config.path_prefix = []
        mock_config.path_suffix = []
        mock_config.excluded_nodes = []
        mock_load_config.return_value = mock_config
        
        handler = TestHandler(mock_config)
        
        success, path = handler.handle_path(['1', '2', '3'])
        
        assert success is False
        assert path is None


class TestPrintHandler:
    """Tests for the PrintHandler class."""
    
    @patch('gapbf.PathHandler.Config.load_config')
    def test_printhandler_init(self, mock_load_config):
        """Test PrintHandler initialization."""
        mock_config = Mock()
        mock_config.grid_size = 3
        mock_load_config.return_value = mock_config
        
        grid_nodes = ['1', '2', '3', '4', '5', '6', '7', '8', '9']
        handler = PrintHandler(mock_config, grid_nodes)
        assert handler.grid_size == 3

    @patch('gapbf.PathHandler.Config.load_config')
    @patch('builtins.print')
    def test_handle_path_prints_grid(self, mock_print, mock_load_config):
        """Test handle_path prints the grid representation."""
        mock_config = Mock()
        mock_config.grid_size = 3
        mock_load_config.return_value = mock_config
        
        grid_nodes = ['1', '2', '3', '4', '5', '6', '7', '8', '9']
        handler = PrintHandler(mock_config, grid_nodes)
        
        success, path = handler.handle_path(['1', '2', '3'])
        
        assert success is False  # PrintHandler always returns False
        assert path is None
        
        # Should have printed something (grid representation)
        assert mock_print.call_count > 0

    @patch('gapbf.PathHandler.Config.load_config')
    def test_render_path_3x3(self, mock_load_config):
        """Test render_path method for 3x3 grid."""
        mock_config = Mock()
        mock_config.grid_size = 3
        mock_load_config.return_value = mock_config
        
        grid_nodes = ['1', '2', '3', '4', '5', '6', '7', '8', '9']
        handler = PrintHandler(mock_config, grid_nodes)
        grid_rows = handler.render_path(['1', '5', '9'])  # Nodes as strings
        
        # Grid should be 3x3
        assert len(grid_rows) == 3
        
        # Path nodes should be marked
        assert '●' in grid_rows[0]  # Node 1 is in first row
        assert '●' in grid_rows[1]  # Node 5 is in middle
        assert '●' in grid_rows[2]  # Node 9 is in last row


class TestLogHandler:
    """Tests for the LogHandler class."""
    
    @patch('gapbf.PathHandler.Config.load_config')
    def test_loghandler_init(self, mock_load_config):
        """Test LogHandler initialization."""
        mock_config = Mock()
        mock_config.paths_log_file_path = './test_paths.csv'
        mock_load_config.return_value = mock_config
        
        handler = LogHandler(mock_config)
        assert handler.config.paths_log_file_path == './test_paths.csv'

    @patch('gapbf.PathHandler.Config.load_config')
    def test_handle_path_logs_to_csv(self, mock_load_config):
        """Test handle_path logs information to CSV file."""
        mock_config = Mock()
        mock_config.paths_log_file_path = './test_paths.csv'
        mock_load_config.return_value = mock_config
        
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = 'test output'
        
        with patch('builtins.open', mock_open()) as mock_file:
            handler = LogHandler(mock_config)
            
            result = handler.handle_path('2023-01-01 12:00:00', [1, 2, 3], mock_result, 'test info')
            
            assert result is True
            mock_file.assert_called_with('./test_paths.csv', 'a', newline='')


class TestPathHandlerIntegration:
    """Integration tests for PathHandler classes."""
    
    def test_log_handler_real_file(self):
        """Test LogHandler with real file operations."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            temp_file = f.name
        
        try:
            with patch('gapbf.PathHandler.Config.load_config') as mock_load:
                mock_config = Mock()
                mock_config.paths_log_file_path = temp_file
                mock_load.return_value = mock_config
                
                handler = LogHandler(mock_config)
                
                mock_result = Mock()
                mock_result.returncode = 0
                mock_result.stdout = 'test output'
                
                # Log a path attempt
                handler.handle_path('2023-01-01 12:00:00', [1, 2, 3], mock_result, 'test')
                
                # Verify file contents
                with open(temp_file, 'r') as f:
                    content = f.read()
                    assert '2023-01-01 12:00:00' in content
                    assert '[1, 2, 3]' in content
                    
        finally:
            os.unlink(temp_file)

    @patch('gapbf.PathHandler.Config.load_config')
    @patch('subprocess.run')
    def test_adb_handler_integration(self, mock_subprocess, mock_load_config):
        """Test ADBHandler integration with mocked subprocess."""
        mock_config = Mock()
        mock_config.stdout_normal = 'Failed to decrypt'
        mock_config.stdout_success = 'Data successfully decrypted'
        mock_config.stdout_error = 'Error'
        mock_config.attempt_delay = 100  # Short delay for testing
        mock_config.paths_log_file_path = './test.csv'
        mock_config.adb_timeout = 30
        mock_config.total_paths = 100
        mock_load_config.return_value = mock_config
        
        # Mock failed attempt
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = 'Failed to decrypt'
        mock_result.stderr = ''
        mock_subprocess.return_value = mock_result
        
        with patch.object(ADBHandler, 'get_attempted_paths', return_value=[]), \
             patch('PathHandler.LogHandler'), \
             patch('time.sleep'):  # Speed up the test
            
            handler = ADBHandler(mock_config)
            
            success, path = handler.handle_path(['1', '2', '3'], total_paths=100)
            
            assert success is False
            assert path is None
            
            # Verify ADB command was called
            expected_command = ["adb", "shell", "twrp", "decrypt", "123"]
            mock_subprocess.assert_called_with(
                expected_command,
                capture_output=True,
                text=True,
                timeout=30
            )
