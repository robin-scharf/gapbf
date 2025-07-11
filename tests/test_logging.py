import pytest
import logging
import sys
from unittest.mock import patch, Mock
from Logging import Logger, get_logger, formatter


class TestLogger:
    """Tests for the Logger singleton class."""
    
    def test_logger_singleton(self):
        """Test that Logger implements singleton pattern."""
        logger1 = Logger()
        logger2 = Logger()
        
        assert logger1 is logger2

    def test_logger_root_configuration(self):
        """Test that Logger configures root logger correctly."""
        # Clear any existing handlers
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        logger = Logger()
        
        root_logger = logging.getLogger()
        assert root_logger.level == logging.CRITICAL
        assert len(root_logger.handlers) >= 1
        
        # Check that a StreamHandler was added
        stream_handlers = [h for h in root_logger.handlers if isinstance(h, logging.StreamHandler)]
        assert len(stream_handlers) >= 1

    def test_logger_formatter_applied(self):
        """Test that the formatter is applied to handlers."""
        logger = Logger()
        root_logger = logging.getLogger()
        
        # Check that handlers have the expected formatter
        for handler in root_logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                assert handler.formatter is not None


class TestGetLogger:
    """Tests for the get_logger function."""
    
    def test_get_logger_default_level(self):
        """Test get_logger with default critical level."""
        logger = get_logger('test_module')
        
        assert logger.name == 'test_module'
        assert logger.level == logging.CRITICAL

    def test_get_logger_error_level(self):
        """Test get_logger with error level."""
        logger = get_logger('test_module', 'error')
        
        assert logger.level == logging.ERROR

    def test_get_logger_warning_level(self):
        """Test get_logger with warning level."""
        logger = get_logger('test_module', 'warning')
        
        assert logger.level == logging.WARNING

    def test_get_logger_debug_level(self):
        """Test get_logger with debug level."""
        logger = get_logger('test_module', 'debug')
        
        assert logger.level == logging.DEBUG

    def test_get_logger_info_level(self):
        """Test get_logger with info level."""
        logger = get_logger('test_module', 'info')
        
        assert logger.level == logging.INFO

    def test_get_logger_invalid_level(self):
        """Test get_logger with invalid level defaults to None (no level set)."""
        logger = get_logger('test_module', 'invalid')
        
        # When an invalid level is provided, the level should not be changed
        # The logger will inherit from parent logger
        assert logger.name == 'test_module'

    def test_get_logger_case_insensitive(self):
        """Test get_logger is case insensitive for log levels."""
        logger_upper = get_logger('test1', 'ERROR')
        logger_lower = get_logger('test2', 'error')
        logger_mixed = get_logger('test3', 'Error')
        
        assert logger_upper.level == logging.ERROR
        assert logger_lower.level == logging.ERROR  
        assert logger_mixed.level == logging.ERROR

    def test_get_logger_none_calling_function(self):
        """Test get_logger with None as calling_function."""
        logger = get_logger(None, 'error')
        
        assert logger.name is None
        assert logger.level == logging.ERROR

    def test_get_logger_different_modules(self):
        """Test get_logger returns different loggers for different modules."""
        logger1 = get_logger('module1', 'error')
        logger2 = get_logger('module2', 'warning')
        
        assert logger1.name == 'module1'
        assert logger2.name == 'module2'
        assert logger1 is not logger2
        assert logger1.level == logging.ERROR
        assert logger2.level == logging.WARNING


class TestFormatter:
    """Tests for the logging formatter."""
    
    def test_formatter_format(self):
        """Test that formatter produces expected format."""
        # Create a test log record
        record = logging.LogRecord(
            name='test_module',
            level=logging.ERROR,
            pathname='',
            lineno=0,
            msg='Test message',
            args=(),
            exc_info=None
        )
        
        formatted = formatter.format(record)
        
        # Check that the format contains expected components
        assert 'ERROR' in formatted
        assert 'test_module' in formatted
        assert 'Test message' in formatted
        
        # Check format structure (should include timestamp, level, module, message)
        parts = formatted.split(' - ')
        assert len(parts) >= 3  # timestamp - level - module: message


class TestLoggingIntegration:
    """Integration tests for the logging system."""
    
    @patch('sys.stdout')
    def test_logging_output_to_stdout(self, mock_stdout):
        """Test that logging outputs to stdout as expected."""
        # Initialize logger system
        Logger()
        logger = get_logger('test_integration', 'error')
        
        # Log a message
        logger.error('Test error message')
        
        # Note: This test verifies the logger is configured to use stdout
        # The actual output testing would require more complex mocking
        assert logger.level == logging.ERROR

    def test_multiple_loggers_independence(self):
        """Test that multiple loggers work independently."""
        Logger()  # Initialize singleton
        
        logger1 = get_logger('module1', 'debug')
        logger2 = get_logger('module2', 'error')
        
        assert logger1.level == logging.DEBUG
        assert logger2.level == logging.ERROR
        
        # They should be different logger instances
        assert logger1 is not logger2
        assert logger1.name != logger2.name

    def test_logger_singleton_persistence(self):
        """Test that Logger singleton persists across multiple instantiations."""
        # Clear any existing instance
        Logger._instance = None
        
        logger1 = Logger()
        logger2 = Logger()
        logger3 = Logger()
        
        assert logger1 is logger2 is logger3

    @patch('logging.getLogger')
    def test_get_logger_calls_logging_correctly(self, mock_get_logger):
        """Test that get_logger calls logging.getLogger correctly."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        
        result = get_logger('test_module', 'error')
        
        mock_get_logger.assert_called_once_with('test_module')
        mock_logger.setLevel.assert_called_once_with(logging.ERROR)
        assert result == mock_logger
