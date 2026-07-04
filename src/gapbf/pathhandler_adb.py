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

# Non-normal results worth retrying in place with exponential backoff:
# transient device/transport hiccups, not real decrypt failures.
RETRYABLE_CLASSIFICATIONS = {"timeout", "unknown_response", "transport_error"}
_MAX_BACKOFF_SECONDS = 300.0


class ADBHandler(PathHandler):
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
        self.terminal_attempt_history = self.database.get_terminal_attempt_history(
            config,
            device_id,
        )
        self.resume_attempt_count = len(self.terminal_attempt_history)
        self.current_path_number = 0

        if self.resume_attempt_count > 0:
            self.logger.info(
                "Resuming from previous session: "
                f"{self.resume_attempt_count} paths already attempted"
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

    def inconclusive_paths(self) -> list[list[str]]:
        """Previously-attempted patterns with no terminal result, retried
        first on restart. Nodes are single chars, so split the stored
        attempt string back into a path."""
        return [
            list(attempt)
            for attempt in self.database.get_inconclusive_attempts(
                self.config, self.device_id
            )
        ]

    def handle_path(
        self, path: list[str], total_paths: int | None = None
    ) -> tuple[bool, list[str] | None]:
        self.current_path_number += 1
        attempt_key = "".join(path)
        attempt_hash = self.database.attempt_hash_for(
            self.device_id,
            self.config.grid_size,
            attempt_key,
        )
        known_result = self.terminal_attempt_history.get(attempt_hash)

        if known_result is not None:
            percentage = (self.current_path_number / total_paths * 100) if total_paths else 0
            if known_result.result_classification == "success":
                self.logger.info("Returning cached successful path for device %s", self.device_id)
                self.output.show_adb_success(path)
                return True, path
            self.output.show_adb_skip(self.current_path_number, total_paths, percentage, path)
            self.logger.info(f"Skipping previously failed path: {path}")
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

        # Retry non-normal results (timeout / transport / unknown) with
        # exponential backoff; real decrypt outcomes break out immediately.
        for retry in range(self.config.retry_max + 1):
            classified_result = self._execute_and_log(command, attempt_key)
            if classified_result.classification not in RETRYABLE_CLASSIFICATIONS:
                break
            if retry < self.config.retry_max:
                delay = min(
                    self.config.retry_base_delay * (2**retry), _MAX_BACKOFF_SECONDS
                )
                self.logger.warning(
                    "Non-normal result %r for path %s; backoff %.1fs then retry %d/%d",
                    classified_result.classification, path, delay,
                    retry + 1, self.config.retry_max,
                )
                if delay > 0:
                    time.sleep(delay)

        if classified_result.classification in {"normal_failure", "success"}:
            terminal_entry = self.database.get_terminal_attempt_entry(
                self.config,
                self.device_id,
                attempt_key,
            )
            if terminal_entry is not None:
                self.terminal_attempt_history[attempt_hash] = terminal_entry

        if classified_result.classification == "timeout":
            self.output.show_adb_timeout(self.current_path_number, total_paths)
            return False, None
        if classified_result.classification == "transport_error":
            self.output.show_adb_error(
                self.current_path_number, total_paths, classified_result.stderr
            )
            return False, None

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
            f"returncode={classified_result.returncode}, "
            f"stdout={classified_result.stdout!r}, stderr={classified_result.stderr!r}"
        )
        self.output.show_adb_unexpected(self.current_path_number, total_paths)
        return False, None

    def _execute_and_log(
        self, command: list[str], attempt_key: str
    ) -> ADBResponseClassification:
        """Run one adb attempt, log it, return the classified result.

        Timeouts and transport errors are surfaced as their own
        classifications so the caller's retry loop can act on them.
        """
        started_at = time.perf_counter()
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.config.adb_timeout,
            )
        except subprocess.TimeoutExpired:
            self.logger.error(
                f"ADB command timed out after {self.config.adb_timeout}s: {attempt_key}"
            )
            classified = ADBResponseClassification(
                classification="timeout",
                response=f"Timeout after {self.config.adb_timeout}s",
                stdout="",
                stderr="",
                returncode=-1,
            )
        except Exception as error:
            self.logger.error(f"Failed to execute ADB command: {error}")
            classified = ADBResponseClassification(
                classification="transport_error",
                response=f"Execution error: {error}",
                stdout="",
                stderr=str(error),
                returncode=-2,
            )
        else:
            classified = self._classify_result(result)

        self.database.log_attempt(
            self.run_id,
            attempt_key,
            classified.response,
            classified.classification,
            classified.returncode,
            (time.perf_counter() - started_at) * 1000,
            stdout=classified.stdout,
            stderr=classified.stderr,
        )
        return classified

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
