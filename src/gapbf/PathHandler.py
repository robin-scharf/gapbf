from abc import ABC, abstractmethod
import subprocess
import sys
import time
import os
import csv
import logging
import fcntl
from typing import Optional, List, Tuple
from datetime import datetime
from .Config import Config


class PathHandler(ABC):
    """Abstract base class for handling paths.
    
    All paths are represented as List[str] for consistency.
    All handlers should implement handle_path() which processes a single path
    and returns a tuple of (success: bool, path: Optional[List[str]]).
    """
    
    @abstractmethod
    def handle_path(self, path: List[str], total_paths: Optional[int] = None) -> Tuple[bool, Optional[List[str]]]:
        """Process a path and return whether it succeeded.
        
        Args:
            path: The path to process (list of string node identifiers)
            total_paths: Total number of paths for progress tracking
            
        Returns:
            Tuple of (success, path) where success is True if pattern found
        """
        pass
    
    def __init__(self, config: Config):
        """Initialize handler with configuration.
        
        Args:
            config: Configuration object containing all settings
        """
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def handle_path(self, path: List[Union[int, str]], total_paths: Optional[int] = None) -> Tuple[bool, Optional[List]]:
        """Process a path and return success status.
        
        Args:
            path: The path to process
            total_paths: Optional total number of paths for progress display
            
        Returns:
            Tuple of (success, path) where success is True if this is the correct path
        """
        pass
    
    def get_attempted_paths(self) -> Set[str]:
        """Retrieve paths that have already been attempted from CSV log.
        
        Uses file locking to ensure thread-safe access.
        
        Returns:
            Set of path strings that have been previously attempted
        """
        attempted_paths = set()
        paths_log_file_path = self.config.paths_log_file_path
        
        if not os.path.isfile(paths_log_file_path):
            self.logger.debug(f"Creating paths log file at {paths_log_file_path}")
            try:
                with open(paths_log_file_path, 'w', newline='') as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    try:
                        writer = csv.writer(f)
                        writer.writerow(['timestamp', 'path', 'result', 'info'])
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except Exception as e:
                self.logger.error(f"Error creating paths log file: {e}")
        else:
            self.logger.debug(f"Loading attempted paths from {paths_log_file_path}")
            try:
                with open(paths_log_file_path, newline='') as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)  # Shared lock for reading
                    try:
                        reader = csv.reader(f)
                        # Skip header row if it exists
                        first_row = next(reader, None)
                        if first_row and first_row[0] != 'timestamp':
                            # Not a header, process this row
                            if len(first_row) >= 2:
                                attempted_paths.add(first_row[1])
                        
                        # Process remaining rows
                        for row in reader:
                            if len(row) >= 2:
                                attempted_paths.add(row[1])
                            else:
                                self.logger.warning(f'Malformed row in CSV file: {row}')
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except Exception as e:
                self.logger.error(f"Error reading attempted paths: {e}")
                
        return attempted_paths


class ADBHandler(PathHandler):
    """Handles paths using ADB for Android device decryption via TWRP."""

    def __init__(self, config: Config):
        """Initialize ADBHandler and start ADB server.
        
        Args:
            config: Configuration object
        """
        super().__init__(config)
        self.attempted_paths = self.get_attempted_paths()
        self.current_path_number = len(self.attempted_paths)  # Resume from last position
        self.log_handler = LogHandler(config)
        
        # Log resume info if continuing previous session
        if self.current_path_number > 0:
            self.logger.info(f"Resuming from previous session: {self.current_path_number} paths already attempted")
        
        # Start ADB server
        try:
            subprocess.run(["adb", "start-server"], check=True, capture_output=True)
            self.logger.info("ADB server started successfully")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to start ADB server: {e}")
            raise
        except FileNotFoundError:
            self.logger.error("ADB command not found. Please install Android platform-tools")
            raise
    
    def handle_path(self, path: List[Union[int, str]], total_paths: Optional[int] = None) -> Tuple[bool, Optional[List]]:
        """Attempt to decrypt using the given path via ADB.
        
        Args:
            path: The pattern path to try
            total_paths: Total number of paths for progress display
            
        Returns:
            Tuple of (success, path) where success is True if decryption succeeded
        """
        self.current_path_number += 1
        
        # Check if already attempted
        path_str = str(path)
        if path_str in self.attempted_paths:
            percentage = (self.current_path_number / total_paths * 100) if total_paths else 0
            print(f"Path {self.current_path_number}/{total_paths} ({percentage:.1f}%): {path} - SKIPPED (already attempted)")
            self.logger.info(f"Skipping previously attempted path: {path}")
            return False, None
        
        # Calculate progress
        percentage = (self.current_path_number / total_paths * 100) if total_paths else 0
        self.logger.info(f"Trying path {self.current_path_number}/{total_paths}: {path} (length: {len(path)})")
        
        # Format path for TWRP
        formatted_path = ''.join(map(str, path))
        
        # Build ADB command
        if self.config.echo_commands:
            command = ["adb", "shell", f"echo '[GAPBF] Attempting: {formatted_path}' && twrp decrypt {formatted_path}"]
        else:
            command = ["adb", "shell", "twrp", "decrypt", formatted_path]
        
        # Execute command with timeout
        try:
            result = subprocess.run(
                command, 
                capture_output=True, 
                text=True, 
                timeout=self.config.adb_timeout
            )
        except subprocess.TimeoutExpired:
            self.logger.error(f"ADB command timed out after {self.config.adb_timeout}s for path: {path}")
            print(f"Path {self.current_path_number}/{total_paths} - TIMEOUT")
            return False, None
        except Exception as e:
            self.logger.error(f"Failed to execute ADB command: {e}")
            print(f"Path {self.current_path_number}/{total_paths} - ERROR: {e}")
            return False, None

        # Log the attempt
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        stdout_safe = result.stdout.replace('\n', '\\n')
        self.log_handler.handle_path(timestamp, path, result.returncode, stdout_safe)

        # Check for success
        if result.returncode == 0 and self.config.stdout_success in result.stdout:
            print(f"\n{'='*60}")
            print(f"SUCCESS! Path found: {path}")
            print(f"{'='*60}\n")
            return True, path

        # Check for normal failure
        if result.returncode == 0 and self.config.stdout_normal in result.stdout:
            # Countdown delay before next attempt
            delay_seconds = self.config.attempt_delay / 1000.0
            if delay_seconds > 0:
                for remaining in range(int(delay_seconds), 0, -1):
                    print(f'\rPath {self.current_path_number}/{total_paths} ({percentage:.1f}%): {path} - FAILED. Next attempt in {remaining}s...', end='')
                    time.sleep(1)
                print()  # New line after countdown
            else:
                print(f'Path {self.current_path_number}/{total_paths} ({percentage:.1f}%): {path} - FAILED')
            return False, None

        # Unexpected error
        self.logger.error(f"Unexpected ADB response: returncode={result.returncode}, stderr={result.stderr}")
        print(f"Path {self.current_path_number}/{total_paths} - UNEXPECTED ERROR")
        return False, None



class TestHandler(PathHandler):
    """Test handler that compares paths against a known test pattern.
    
    This handler is for testing the path generation algorithm without
    requiring an actual Android device. It simply checks if the generated
    path matches the configured test_path.
    """

    def __init__(self, config: Config, enable_logging: bool = False):
        """Initialize TestHandler.
        
        Args:
            config: Configuration object containing test_path
            enable_logging: If True, log attempts to CSV file
        """
        super().__init__(config)
        self.test_path = list(config.test_path)
        self.current_path_number = 0
        self.enable_logging = enable_logging
        
        # Create log handler if logging enabled
        if enable_logging:
            self.log_handler = LogHandler(config)
            self.logger.info("CSV logging enabled for TestHandler")
        
        # Print configuration for visibility
        print(f"[TEST] Grid size: {config.grid_size}")
        print(f"[TEST] Path max node distance: {config.path_max_node_distance}")
        print(f"[TEST] Path prefix: {config.path_prefix}")
        print(f"[TEST] Path suffix: {config.path_suffix}")
        print(f"[TEST] Excluded nodes: {config.excluded_nodes}")
        print(f"[TEST] Test path: {self.test_path} (length: {len(self.test_path)})")
        print(f"[TEST] CSV logging: {'enabled' if enable_logging else 'disabled'}")

    def handle_path(self, path: List[Union[int, str]], total_paths: Optional[int] = None) -> Tuple[bool, Optional[List]]:
        """Check if path matches the test pattern.
        
        Args:
            path: The path to test
            total_paths: Total number of paths for progress display
            
        Returns:
            Tuple of (success, path) where success is True if path matches test_path
        """
        self.current_path_number += 1
        percentage = (self.current_path_number / total_paths * 100) if total_paths else 0
        
        # Log attempt if enabled
        if self.enable_logging:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            result = "SUCCESS" if path == self.test_path else "FAILED"
            self.log_handler.handle_path(timestamp, path, result, f"Test attempt #{self.current_path_number}")
        
        if path == self.test_path:
            print(f"\n{'='*60}")
            print(f"[TEST] SUCCESS! Path {self.current_path_number}/{total_paths} ({percentage:.1f}%)")
            print(f"[TEST] Found: {path}")
            print(f"{'='*60}\n")
            return True, path
        else:
            print(f"[TEST] Path {self.current_path_number}/{total_paths} ({percentage:.1f}%): {path} - FAILED")
            return False, None



class PrintHandler(PathHandler):
    """Prints visual representation of paths for debugging and visibility.
    
    Shows both the pattern grid and the step numbers for each path.
    """

    def __init__(self, config: Config, grid_nodes: List[Union[int, str]]):
        """Initialize PrintHandler.
        
        Args:
            config: Configuration object
            grid_nodes: List of nodes in the grid (from PathFinder)
        """
        super().__init__(config)
        self.grid_size = config.grid_size
        self.grid_nodes = grid_nodes
        
        # Create mapping from grid position to node value
        self.node_positions = {}
        for i, node in enumerate(grid_nodes):
            row = i // self.grid_size
            col = i % self.grid_size
            self.node_positions[(row, col)] = node
    
    def handle_path(self, path: List[Union[int, str]], total_paths: Optional[int] = None) -> Tuple[bool, Optional[List]]:
        """Print visual representation of the path.
        
        Args:
            path: The path to visualize
            total_paths: Total number of paths (unused)
            
        Returns:
            Always returns (False, None) as this handler doesn't check for success
        """
        path_rows = self.render_path(path)
        steps_rows = self.render_path_steps(path)
        print(f"[PRINT] Path: {path}")
        for path_row, steps_row in zip(path_rows, steps_rows):
            print(f"  {path_row}    {steps_row}")
        print()
        return False, None

    def render_path(self, path: List[Union[int, str]]) -> List[str]:
        """Render the path as a grid with dots showing which nodes are used.
        
        Args:
            path: The path to render
            
        Returns:
            List of strings, one per row
        """
        rows = []
        for y in range(self.grid_size):
            row = []
            for x in range(self.grid_size):
                node_value = self.node_positions.get((y, x))
                if node_value in path:
                    row.append("●")
                else:
                    row.append("○")
            rows.append("".join(row))
        return rows

    def render_path_steps(self, path: List[Union[int, str]]) -> List[str]:
        """Render the path showing step numbers.
        
        Args:
            path: The path to render
            
        Returns:
            List of strings, one per row, showing step numbers
        """
        rows = []
        for y in range(self.grid_size):
            row = []
            for x in range(self.grid_size):
                node_value = self.node_positions.get((y, x))
                if node_value in path:
                    step_num = path.index(node_value) + 1
                    row.append(f"{step_num}")
                else:
                    row.append("·")
            rows.append(" ".join(row))
        return rows

    
class LogHandler(PathHandler):
    """Logs path attempts and responses to CSV file.
    
    This handler only writes to the log file and doesn't check for success.
    """

    def __init__(self, config: Config):
        """Initialize LogHandler.
        
        Args:
            config: Configuration object
        """
        super().__init__(config)

    def handle_path(self, timestamp: str, path: List[Union[int, str]], 
                    returncode: int, info: str) -> bool:
        """Log a path attempt to CSV.
        
        Note: This method has a different signature than the abstract method
        because it's used internally by ADBHandler for logging purposes.
        
        Args:
            timestamp: Timestamp of the attempt
            path: The path that was attempted
            returncode: Return code from the ADB command
            info: Additional information (stdout)
            
        Returns:
            True if logging succeeded
        """
        try:
            with open(self.config.paths_log_file_path, 'a', newline='') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # Exclusive lock for writing
                try:
                    writer = csv.writer(f)
                    writer.writerow([timestamp, path, returncode, info])
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            return True
        except Exception as e:
            self.logger.error(f"Failed to log path attempt: {e}")
            return False