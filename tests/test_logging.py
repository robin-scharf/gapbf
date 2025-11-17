import pytest
import logging
import sys
from unittest.mock import patch, Mock
from gapbf.Logging import setup_logging


class TestLogging:
    """Tests for the logging setup functions."""
    
    def test_setup_logging_default(self):
        """Test that setup_logging configures logging with defaults."""
        # Clear any existing handlers
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        
        logger = setup_logging()
        
        assert logger is root_logger
        assert root_logger.level == logging.ERROR
        assert len(root_logger.handlers) >= 1

    def test_setup_logging_custom_level(self):
        """Test that setup_logging accepts custom log level."""
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        
        setup_logging(log_level='debug')
        
        assert root_logger.level == logging.DEBUG
        
        # Check that a StreamHandler was added
        stream_handlers = [h for h in root_logger.handlers if isinstance(h, logging.StreamHandler)]
        assert len(stream_handlers) >= 1

    def test_setup_logging_formatter_applied(self):
        """Test that the formatter is applied to handlers."""
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        
        setup_logging()
        
        # Check that handlers have the expected formatter
        for handler in root_logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                assert handler.formatter is not None

    def test_setup_logging_with_file(self, tmp_path):
        """Test setup_logging with file output."""
        log_file = tmp_path / "test.log"
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        
        setup_logging(log_file=str(log_file))
        
        # Should have both stdout and file handlers
        assert len(root_logger.handlers) == 2
        file_handlers = [h for h in root_logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1

    def test_setup_logging_level_mapping(self):
        """Test that string log levels map correctly."""
        test_cases = [
            ('critical', logging.CRITICAL),
            ('error', logging.ERROR),
            ('warning', logging.WARNING),
            ('debug', logging.DEBUG),
            ('info', logging.INFO),
        ]
        
        for level_str, expected_level in test_cases:
            root_logger = logging.getLogger()
            root_logger.handlers.clear()
            
            setup_logging(log_level=level_str)
            assert root_logger.level == expected_level
