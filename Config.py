import yaml
from dataclasses import dataclass, field, asdict
from typing import List, Union, Set, Tuple

@dataclass
class Config:
    config_file_path: str = ''
    grid_size: int = 0
    path_min_length: int = 0
    path_max_length: int = 0
    path_max_node_distance: int = 1
    path_prefix: Tuple[Union[int, str]] = ()
    path_suffix: Tuple[Union[int, str]] = ()
    excluded_nodes: List[Union[int, str]] = field(default_factory=list)
    attempt_delay: float = 0.0
    test_path: Tuple[Union[int, str]] = ()
    stdout_normal: str = Tuple[str]
    stdout_success: str = ''
    stdout_error: str = ''
    paths_log_file_path: str = ''
    process_log_file_path: str = ''
    adb_timeout: int = 30
    total_paths: int = 0

    def __post_init__(self):
        if not isinstance(self.config_file_path, str):
            raise TypeError(
                f"config_file_path must be a string, got {type(self.config_file_path).__name__}")
        if not isinstance(self.grid_size, int):
            raise TypeError(
                f"grid_size must be an integer, got {type(self.grid_size).__name__}")
        if not isinstance(self.path_min_length, int):
            raise TypeError(
                f"path_min_length must be an integer, got {type(self.path_min_length).__name__}")
        if not isinstance(self.path_max_length, int):
            raise TypeError(
                f"path_max_length must be an integer, got {type(self.path_max_length).__name__}")
        if not isinstance(self.path_max_node_distance, int):
            raise TypeError(
                f"path_max_node_distance must be an integer, got {type(self.path_max_node_distance).__name__}")
        if not all(isinstance(item, (int, str)) for item in self.path_prefix):
            raise TypeError(
                "All items in path_prefix must be either integer or string")
        if not all(isinstance(item, (int, str)) for item in self.path_suffix):
            raise TypeError(
                "All items in path_suffix must be either integer or string")
        if not all(isinstance(item, (int, str)) for item in self.excluded_nodes):
            raise TypeError(
                "All items in excluded_nodes must be either integer or string")
        if not isinstance(self.attempt_delay, float):
            raise TypeError(
                f"attempt_delay must be a float, got {type(self.attempt_delay).__name__}")
        if not all(isinstance(item, (int, str)) for item in self.test_path):
            raise TypeError(
                "All items in test_path must be either integer or string")
        if not isinstance(self.stdout_normal, str):
            raise TypeError(
                f"Stdout_normal must be a string, got {type(self.stdout_normal).__name__}")
        if not isinstance(self.stdout_success, str):
            raise TypeError(
                f"stdout_success must be a string, got {type(self.stdout_success).__name__}")
        if not isinstance(self.stdout_error, str):
            raise TypeError(
                f"stdout_error must be a string, got {type(self.stdout_error).__name__}")
        if not isinstance(self.paths_log_file_path, str):
            raise TypeError(
                f"paths_log_file_path must be a string, got {type(self.paths_log_file_path).__name__}")
        if not isinstance(self.process_log_file_path, str):
            raise TypeError(
                f"process_log_file_path must be a string, got {type(self.process_log_file_path).__name__}")
        if not isinstance(self.adb_timeout, int):
            raise TypeError(
                f"adb_timeout must be an integer, got {type(self.adb_timeout).__name__}")

    @classmethod
    def load_config(cls, config_file_path: str) -> 'Config':
        try:
            with open(config_file_path, 'r') as f:
                config_data = yaml.safe_load(f)
        except FileNotFoundError:
            raise ValueError(f"Configuration file not found: {config_file_path}")
        except yaml.YAMLError:
            raise ValueError(f"Invalid YAML format in configuration file: {config_file_path}")

        loaded_config = cls(
            config_file_path=str(config_file_path),
            grid_size=int(config_data.get('grid_size', 0)),
            path_min_length=int(config_data.get('path_min_length', 4)),  # Default to 4 (Android minimum)
            path_max_length=int(config_data.get('path_max_length', 0)),
            path_max_node_distance=int(
                config_data.get('path_max_node_distance', 1)),
            path_prefix=list(config_data.get('path_prefix', [])),
            path_suffix=list(config_data.get('path_suffix', [])),
            excluded_nodes=list(config_data.get('excluded_nodes', [])),
            attempt_delay=float(config_data.get('attempt_delay', 0.0)),
            test_path=list(config_data.get('test_path', [])),
            stdout_normal=str(config_data.get(
                'outputstrings', {}).get('stdout_normal', '')),
            stdout_success=str(config_data.get(
                'outputstrings', {}).get('stdout_success', '')),
            stdout_error=str(config_data.get(
                'outputstrings', {}).get('stdout_error', '')),
            paths_log_file_path=str(
                config_data.get('paths_log_file_path', '')),
            process_log_file_path=str(
                config_data.get('process_log_file_path', '')),
            adb_timeout=int(config_data.get('adb_timeout', 30)),
            total_paths=int(config_data.get('total_paths', 0))
        )
        return loaded_config


def __repr__(self) -> str:
    return f"Config({self.config_file_path})"