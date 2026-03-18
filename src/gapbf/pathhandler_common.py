import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .Config import Config
from .Output import Output


@dataclass(frozen=True)
class ADBResponseClassification:
    classification: str
    response: str
    stdout: str
    stderr: str
    returncode: int


def _format_response(stdout: str, stderr: str) -> str:
    stdout_safe = stdout.replace("\n", "\\n")
    stderr_safe = stderr.replace("\n", "\\n")
    if stdout_safe and stderr_safe:
        return f"stdout={stdout_safe}; stderr={stderr_safe}"
    if stderr_safe:
        return f"stderr={stderr_safe}"
    return stdout_safe


def _marker_matches(marker: str, text: str) -> bool:
    return bool(marker) and marker in text


class PathHandler(ABC):
    def __init__(self, config: Config, output: Output):
        self.config = config
        self.output = output
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def handle_path(
        self, path: list[str], total_paths: int | None = None
    ) -> tuple[bool, list[str] | None]:
        raise NotImplementedError
