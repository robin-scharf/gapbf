"""Centralized logging configuration for GAPBF.

This module provides a simple interface for setting up logging across the application.
Uses Python's built-in logging module without unnecessary abstraction.
"""
import logging
import sys
from typing import Optional

# Log level mapping
_LEVEL_MAP = {
    'critical': logging.CRITICAL,
    'error': logging.ERROR,
    'warning': logging.WARNING,
    'debug': logging.DEBUG,
    'info': logging.INFO
}


def setup_logging(log_level: str = 'error', log_file: Optional[str] = None) -> logging.Logger:
    """Configure root logger for the application.
    
    This should be called once at application startup. All subsequent calls to
    logging.getLogger() will inherit this configuration.
    
    Args:
        log_level: Logging level as string ('error', 'warning', 'debug', 'info', 'critical')
        log_file: Optional path to log file. If None, only logs to stdout.
    
    Returns:
        The configured root logger
    """
    # Get numeric level, default to ERROR
    level = _LEVEL_MAP.get(log_level.lower(), logging.ERROR)
    
    # Clear any existing handlers to avoid duplicates
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)
    
    # Create formatter
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(module)s: %(message)s")
    
    # Add stdout handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    root_logger.addHandler(stdout_handler)
    
    # Add file handler if requested
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a specific module or class.
    
    Args:
        name: Name for the logger (typically __name__ or class name)
    
    Returns:
        Logger instance that inherits from root logger configuration
    """
    return logging.getLogger(name)