import logging
import sys

# Define a common formatter for all log levels
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(module)s: %(message)s")

class Logger:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Logger, cls).__new__(cls)
            
            # Root logger configuration
            root_logger = logging.getLogger()
            root_logger.setLevel(logging.CRITICAL)
            
            stream_handler = logging.StreamHandler(sys.stdout)
            stream_handler.setFormatter(formatter)
            
            root_logger.addHandler(stream_handler)
        
        return cls._instance

def get_logger(calling_function=None, log_level='critical'):
    # Create logger with the calling function name, or use root if None
    if calling_function is None:
        logger = logging.getLogger()
    else:
        logger = logging.getLogger(calling_function)
    
    # Clear existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Define a mapping from string values to corresponding logging levels
    log_level_mapping = {
        'critical': logging.CRITICAL,
        'error': logging.ERROR,
        'warning': logging.WARNING,
        'debug': logging.DEBUG,
        'info': logging.INFO
    }
    
    # Get the corresponding logging level or default to ERROR
    level = log_level_mapping.get(log_level.lower(), logging.ERROR)
    
    # Set the logging level
    logger.setLevel(level)
    
    # Add handler with formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger

def add_file_handler(logger, file_path):
    """Add a file handler to an existing logger."""
    file_handler = logging.FileHandler(file_path)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger