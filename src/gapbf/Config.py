"""Configuration management for GAPBF.

Handles loading and validation of configuration from YAML files using Pydantic.
"""

from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator


NODE_SEQUENCE = [str(index) for index in range(1, 10)] + list(":;<=>?@ABCDEFGHIJKLMNOPQRST")


def valid_nodes_for_grid(grid_size: int) -> list[str]:
    """Return the valid node identifiers for a given grid size."""
    return NODE_SEQUENCE[: grid_size * grid_size]


def merge_prefix_suffix(path_prefix: list[str], path_suffix: list[str]) -> list[str] | None:
    """Merge prefix and suffix constraints if they can describe a valid path."""
    if not path_prefix:
        return list(path_suffix)
    if not path_suffix:
        return list(path_prefix)

    max_overlap = min(len(path_prefix), len(path_suffix))
    for overlap in range(max_overlap, -1, -1):
        if overlap and path_prefix[-overlap:] != path_suffix[:overlap]:
            continue

        merged = path_prefix + path_suffix[overlap:]
        if len(merged) == len(set(merged)):
            return merged

    return None


class Config(BaseModel):
    """Configuration model for GAPBF application with Pydantic validation.

    All node values (prefix, suffix, excluded_nodes, test_path) are stored
    as strings for consistency throughout the application.
    """

    model_config = ConfigDict(
        extra='forbid',
        validate_assignment=True,
    )

    config_file_path: str = ''
    grid_size: int = Field(default=0, ge=3, le=6)
    path_min_length: int = Field(default=4, ge=1)
    path_max_length: int = Field(default=0, ge=1)
    path_max_node_distance: int = Field(default=1, ge=1)
    path_prefix: list[str] = Field(default_factory=list)
    path_suffix: list[str] = Field(default_factory=list)
    excluded_nodes: list[str] = Field(default_factory=list)
    attempt_delay: float = Field(default=0.0, ge=0)
    test_path: list[str] = Field(default_factory=list)
    stdout_normal: str = ''
    stdout_success: str = ''
    stdout_error: str = ''
    db_path: str = '~/.gapbf/gapbf.db'
    adb_timeout: int = Field(default=30, ge=1)
    total_paths: int = Field(default=0, ge=0)
    echo_commands: bool = True

    @field_validator('grid_size')
    @classmethod
    def validate_grid_size(cls, value: int) -> int:
        """Validate grid size is supported."""
        if value not in [3, 4, 5, 6]:
            raise ValueError(f'grid_size must be 3, 4, 5, or 6, got {value}')
        return value

    @field_validator('path_prefix', 'path_suffix', 'excluded_nodes', 'test_path', mode='before')
    @classmethod
    def normalize_node_lists(cls, value: Any) -> list[str]:
        """Normalize configured node lists to strings."""
        if value is None:
            return []
        if isinstance(value, (str, bytes)):
            raise ValueError('node lists must be sequences, not strings')
        return [str(item) for item in value]

    @field_validator('path_prefix', 'path_suffix', 'excluded_nodes', 'test_path')
    @classmethod
    def validate_unique_nodes(cls, value: list[str], info: ValidationInfo) -> list[str]:
        """Reject duplicate nodes inside a single constraint list."""
        if len(value) != len(set(value)):
            raise ValueError(f'{info.field_name} cannot contain duplicate nodes')
        return value

    @model_validator(mode='after')
    def validate_path_constraints(self) -> 'Config':
        """Validate path constraint relationships."""
        valid_nodes = set(valid_nodes_for_grid(self.grid_size))
        if self.path_max_length > len(valid_nodes):
            raise ValueError(
                f'path_max_length ({self.path_max_length}) cannot exceed available nodes ({len(valid_nodes)})'
            )

        for field_name in ('path_prefix', 'path_suffix', 'excluded_nodes', 'test_path'):
            field_nodes = getattr(self, field_name)
            invalid_nodes = sorted(set(field_nodes) - valid_nodes)
            if invalid_nodes:
                raise ValueError(
                    f'{field_name} contains invalid nodes for a {self.grid_size}x{self.grid_size} grid: {invalid_nodes}'
                )

        if self.path_min_length > self.path_max_length and self.path_max_length > 0:
            raise ValueError(
                f'path_min_length ({self.path_min_length}) cannot exceed '
                f'path_max_length ({self.path_max_length})'
            )

        if len(self.path_prefix) > self.path_max_length:
            raise ValueError(
                f'path_prefix length ({len(self.path_prefix)}) exceeds '
                f'path_max_length ({self.path_max_length})'
            )

        if len(self.path_suffix) > self.path_max_length:
            raise ValueError(
                f'path_suffix length ({len(self.path_suffix)}) exceeds '
                f'path_max_length ({self.path_max_length})'
            )

        merged_constraint = merge_prefix_suffix(self.path_prefix, self.path_suffix)
        if merged_constraint is None:
            raise ValueError('path_prefix and path_suffix cannot describe a valid non-repeating path')
        if len(merged_constraint) > self.path_max_length:
            raise ValueError('Combined prefix and suffix constraints exceed path_max_length')

        prefix_set = set(self.path_prefix)
        suffix_set = set(self.path_suffix)
        excluded_set = set(self.excluded_nodes)

        if overlap := prefix_set & excluded_set:
            raise ValueError(f'path_prefix contains excluded nodes: {overlap}')
        if overlap := suffix_set & excluded_set:
            raise ValueError(f'path_suffix contains excluded nodes: {overlap}')
        if overlap := set(self.test_path) & excluded_set:
            raise ValueError(f'test_path contains excluded nodes: {overlap}')

        return self

    @classmethod
    def load_config(cls, config_file_path: str) -> 'Config':
        """Load configuration from YAML file."""
        try:
            with open(config_file_path, 'r') as file_obj:
                config_data = yaml.safe_load(file_obj) or {}
        except FileNotFoundError:
            raise ValueError(f"Configuration file not found: {config_file_path}")
        except yaml.YAMLError as error:
            raise ValueError(f"Invalid YAML in {config_file_path}: {error}")

        def to_string_list(values: Any) -> list[str]:
            return [str(item) for item in values] if values else []

        config_dict = {
            'config_file_path': config_file_path,
            'grid_size': config_data.get('grid_size', 3),
            'path_min_length': config_data.get('path_min_length', 4),
            'path_max_length': config_data.get('path_max_length', 9),
            'path_max_node_distance': config_data.get('path_max_node_distance', 1),
            'path_prefix': to_string_list(config_data.get('path_prefix', [])),
            'path_suffix': to_string_list(config_data.get('path_suffix', [])),
            'excluded_nodes': to_string_list(config_data.get('excluded_nodes', [])),
            'attempt_delay': config_data.get('attempt_delay', 0.0),
            'test_path': to_string_list(config_data.get('test_path', [])),
            'stdout_normal': config_data.get('stdout_normal', ''),
            'stdout_success': config_data.get('stdout_success', ''),
            'stdout_error': config_data.get('stdout_error', ''),
            'db_path': config_data.get('db_path', '~/.gapbf/gapbf.db'),
            'adb_timeout': config_data.get('adb_timeout', 30),
            'total_paths': config_data.get('total_paths', 0),
            'echo_commands': config_data.get('echo_commands', True),
        }

        return cls(**config_dict)

    def __repr__(self) -> str:
        """String representation of Config."""
        return f"Config(grid={self.grid_size}x{self.grid_size}, len={self.path_min_length}-{self.path_max_length})"