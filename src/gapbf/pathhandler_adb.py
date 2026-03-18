import subprocess
import time

from .Config import Config
from .Database import RunDatabase
from .Output import Output
from .pathhandler_common import (
    ADBResponseClassification,
    PathHandler,
    _format_response,
    _marker_matches,
)


class ADBHandler(PathHandler):
    def __init__(
        self,
        config: Config,
        database: RunDatabase,
        run_id: str,
        device_id: str,
        output: Output,
    ):
        from . import PathHandler as pathhandler_module

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
            pathhandler_module.subprocess.run(
                ["adb", "start-server"], check=True, capture_output=True
            )
            self.logger.info("ADB server started successfully")
        except pathhandler_module.subprocess.CalledProcessError as error:
            self.logger.error(f"Failed to start ADB server: {error}")
            raise
        except FileNotFoundError:
            self.logger.error("ADB command not found. Please install Android platform-tools")
            raise

    def handle_path(
        self, path: list[str], total_paths: int | None = None
    ) -> tuple[bool, list[str] | None]:
        from . import PathHandler as pathhandler_module

        self.current_path_number += 1
        attempt_key = "".join(path)

        if attempt_key in self.attempted_paths:
            percentage = (self.current_path_number / total_paths * 100) if total_paths else 0
            self.output.show_adb_skip(self.current_path_number, total_paths, percentage, path)
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
            result = pathhandler_module.subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.config.adb_timeout,
            )
        except pathhandler_module.subprocess.TimeoutExpired:
            self.database.log_attempt(
                self.run_id,
                attempt_key,
                f"Timeout after {self.config.adb_timeout}s",
                "timeout",
                -1,
                (time.perf_counter() - started_at) * 1000,
                stdout="",
                stderr="",
            )
            self.attempted_paths.add(attempt_key)
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
                "transport_error",
                -2,
                (time.perf_counter() - started_at) * 1000,
                stdout="",
                stderr=str(error),
            )
            self.attempted_paths.add(attempt_key)
            self.logger.error(f"Failed to execute ADB command: {error}")
            self.output.show_adb_error(self.current_path_number, total_paths, str(error))
            return False, None

        classified_result = self._classify_result(result)
        duration_ms = (time.perf_counter() - started_at) * 1000
        self.attempted_paths.add(attempt_key)
        self.database.log_attempt(
            self.run_id,
            attempt_key,
            classified_result.response,
            classified_result.classification,
            classified_result.returncode,
            duration_ms,
            stdout=classified_result.stdout,
            stderr=classified_result.stderr,
        )

        if classified_result.classification == "success":
            self.output.show_adb_success(path)
            return True, path
        if classified_result.classification == "normal_failure":
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
        if classified_result.classification == "configured_error":
            error_message = (
                classified_result.stderr or classified_result.stdout or "Configured error"
            )
            self.logger.error(f"ADB error marker matched for path {path}: {error_message}")
            self.output.show_adb_error(self.current_path_number, total_paths, error_message)
            return False, None

        self.logger.error(
            "Unexpected ADB response: "
            f"returncode={result.returncode}, stdout={result.stdout!r}, stderr={result.stderr!r}"
        )
        self.output.show_adb_unexpected(self.current_path_number, total_paths)
        return False, None

    def _classify_result(
        self, result: subprocess.CompletedProcess[str]
    ) -> ADBResponseClassification:
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        response = _format_response(stdout, stderr)

        if _marker_matches(self.config.stdout_error, stdout) or _marker_matches(
            self.config.stdout_error, stderr
        ):
            classification = "configured_error"
        elif _marker_matches(self.config.stdout_success, stdout):
            classification = "success"
        elif _marker_matches(self.config.stdout_normal, stdout):
            classification = "normal_failure"
        else:
            classification = "unknown_response"

        return ADBResponseClassification(
            classification=classification,
            response=response,
            stdout=stdout,
            stderr=stderr,
            returncode=result.returncode,
        )
