import logging
import subprocess
import time
from abc import ABC, abstractmethod

from .Config import Config
from .Database import RunDatabase
from .Output import Output


class PathHandler(ABC):
    """Abstract base class for handling generated paths."""

    def __init__(self, config: Config, output: Output):
        self.config = config
        self.output = output
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def handle_path(
        self, path: list[str], total_paths: int | None = None
    ) -> tuple[bool, list[str] | None]:
        raise NotImplementedError


class ADBHandler(PathHandler):
    """Handle paths by calling `adb shell twrp decrypt ...`."""

    def __init__(
        self,
        config: Config,
        database: RunDatabase,
        run_id: str,
        device_id: str,
        output: Output,
    ):
        super().__init__(config, output)
        self.database = database
        self.run_id = run_id
        self.device_id = device_id
        self.attempted_paths = self.database.get_attempted_paths(config, device_id)
        self.current_path_number = len(self.attempted_paths)

        if self.current_path_number > 0:
            self.logger.info(
                "Resuming from previous session: "
                f"{self.current_path_number} paths already attempted"
            )

        try:
            subprocess.run(["adb", "start-server"], check=True, capture_output=True)
            self.logger.info("ADB server started successfully")
        except subprocess.CalledProcessError as error:
            self.logger.error(f"Failed to start ADB server: {error}")
            raise
        except FileNotFoundError:
            self.logger.error("ADB command not found. Please install Android platform-tools")
            raise

    def handle_path(
        self, path: list[str], total_paths: int | None = None
    ) -> tuple[bool, list[str] | None]:
        self.current_path_number += 1
        attempt_key = "".join(path)

        if attempt_key in self.attempted_paths:
            percentage = (self.current_path_number / total_paths * 100) if total_paths else 0
            self.output.show_adb_skip(self.current_path_number, total_paths, percentage, path)
            self.database.log_attempt(
                self.run_id,
                attempt_key,
                "Skipped because the attempt already exists in the run history",
                "skipped",
                None,
                0.0,
            )
            self.logger.info(f"Skipping previously attempted path: {path}")
            return False, None

        percentage = (self.current_path_number / total_paths * 100) if total_paths else 0
        self.logger.info(
            f"Trying path {self.current_path_number}/{total_paths}: {path} (length: {len(path)})"
        )

        formatted_path = "".join(path)
        if self.config.echo_commands:
            command = [
                "adb",
                "shell",
                f"echo '[GAPBF] Attempting: {formatted_path}' && twrp decrypt {formatted_path}",
            ]
        else:
            command = ["adb", "shell", "twrp", "decrypt", formatted_path]

        started_at = time.perf_counter()
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.config.adb_timeout,
            )
        except subprocess.TimeoutExpired:
            self.database.log_attempt(
                self.run_id,
                attempt_key,
                f"Timeout after {self.config.adb_timeout}s",
                "timeout",
                -1,
                (time.perf_counter() - started_at) * 1000,
            )
            self.logger.error(
                f"ADB command timed out after {self.config.adb_timeout}s for path: {path}"
            )
            self.output.show_adb_timeout(self.current_path_number, total_paths)
            return False, None
        except Exception as error:
            self.database.log_attempt(
                self.run_id,
                attempt_key,
                f"Execution error: {error}",
                "error",
                -2,
                (time.perf_counter() - started_at) * 1000,
            )
            self.logger.error(f"Failed to execute ADB command: {error}")
            self.output.show_adb_error(self.current_path_number, total_paths, str(error))
            return False, None

        stdout_safe = result.stdout.replace("\n", "\\n")
        stderr_safe = result.stderr.replace("\n", "\\n") if result.stderr else ""
        response = stdout_safe if not stderr_safe else f"stdout={stdout_safe}; stderr={stderr_safe}"
        duration_ms = (time.perf_counter() - started_at) * 1000
        self.attempted_paths.add(attempt_key)

        if result.returncode == 0 and self.config.stdout_success in result.stdout:
            self.database.log_attempt(
                self.run_id,
                attempt_key,
                response,
                "success",
                result.returncode,
                duration_ms,
            )
            self.output.show_adb_success(path)
            return True, path

        if result.returncode == 0 and self.config.stdout_normal in result.stdout:
            self.database.log_attempt(
                self.run_id,
                attempt_key,
                response,
                "normal_failure",
                result.returncode,
                duration_ms,
            )
            self.output.show_adb_failure(
                self.current_path_number,
                total_paths,
                percentage,
                path,
                self.config.attempt_delay,
            )
            if self.config.attempt_delay > 0:
                time.sleep(self.config.attempt_delay)
            return False, None

        self.database.log_attempt(
            self.run_id,
            attempt_key,
            response,
            "unexpected_response",
            result.returncode,
            duration_ms,
        )
        self.logger.error(
            f"Unexpected ADB response: returncode={result.returncode}, stderr={result.stderr}"
        )
        self.output.show_adb_unexpected(self.current_path_number, total_paths)
        return False, None


class TestHandler(PathHandler):
    """Compare generated paths against a configured test pattern."""

    def __init__(self, config: Config, output: Output):
        super().__init__(config, output)
        self.test_path = list(config.test_path)
        self.current_path_number = 0
        self.output.show_test_configuration(
            grid_size=config.grid_size,
            path_max_node_distance=config.path_max_node_distance,
            path_prefix=config.path_prefix,
            path_suffix=config.path_suffix,
            excluded_nodes=config.excluded_nodes,
            test_path=self.test_path,
        )

    def handle_path(
        self, path: list[str], total_paths: int | None = None
    ) -> tuple[bool, list[str] | None]:
        self.current_path_number += 1
        percentage = (self.current_path_number / total_paths * 100) if total_paths else 0

        if path == self.test_path:
            self.output.show_test_result(
                success=True,
                current=self.current_path_number,
                total=total_paths,
                percentage=percentage,
                path=path,
            )
            return True, path

        self.output.show_test_result(
            success=False,
            current=self.current_path_number,
            total=total_paths,
            percentage=percentage,
            path=path,
        )
        return False, None


class PrintHandler(PathHandler):
    """Render generated paths visually for debugging."""

    def __init__(self, config: Config, grid_nodes: list[str], output: Output):
        super().__init__(config, output)
        self.grid_size = config.grid_size
        self.grid_nodes = grid_nodes
        self.node_positions = {}
        for index, node in enumerate(grid_nodes):
            row = index // self.grid_size
            col = index % self.grid_size
            self.node_positions[(row, col)] = node

    def handle_path(
        self, path: list[str], total_paths: int | None = None
    ) -> tuple[bool, list[str] | None]:
        path_rows = self.render_path(path)
        steps_rows = self.render_path_steps(path)
        self.output.show_print_path(path, path_rows, steps_rows)
        return False, None

    def render_path(self, path: list[str]) -> list[str]:
        rows = []
        for y in range(self.grid_size):
            row = []
            for x in range(self.grid_size):
                node_value = self.node_positions.get((y, x))
                row.append("●" if node_value in path else "○")
            rows.append("".join(row))
        return rows

    def render_path_steps(self, path: list[str]) -> list[str]:
        rows = []
        for y in range(self.grid_size):
            row = []
            for x in range(self.grid_size):
                node_value = self.node_positions.get((y, x))
                if node_value in path:
                    row.append(f"{path.index(node_value) + 1}")
                else:
                    row.append("·")
            rows.append(" ".join(row))
        return rows
