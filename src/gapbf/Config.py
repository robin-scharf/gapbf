"""Configuration management for GAPBF.

Handles loading and validation of configuration from YAML files using Pydantic.
"""
import yaml
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from typing import List
from pathlib import Path


class Config(BaseModel):
    """Configuration model for GAPBF application with Pydantic validation.
    
    All node values (prefix, suffix, excluded_nodes, test_path) are stored
    as strings for consistency throughout the application.
    """
    
    # Pydantic v2 configuration
    model_config = ConfigDict(
        extra='forbid',  # Don't allow extra fields
        validate_assignment=True  # Validate on attribute assignment
    )
    
    # Configuration fields with validation
    config_file_path: str = ''
    grid_size: int = Field(default=0, ge=3, le=6)
    path_min_length: int = Field(default=4, ge=1)
    path_max_length: int = Field(default=0, ge=1)
    path_max_node_distance: int = Field(default=1, ge=1)
    path_prefix: List[str] = Field(default_factory=list)
    path_suffix: List[str] = Field(default_factory=list)
    excluded_nodes: List[str] = Field(default_factory=list)
    attempt_delay: float = Field(default=0.0, ge=0)
    test_path: List[str] = Field(default_factory=list)
    stdout_normal: str = ''
    stdout_success: str = ''
    stdout_error: str = ''
    paths_log_file_path: str = ''
    process_log_file_path: str = ''
    adb_timeout: int = Field(default=30, ge=1)
    total_paths: int = Field(default=0, ge=0)
    echo_commands: bool = True
    
    @field_validator('grid_size')
    @classmethod
    def validate_grid_size(cls, v: int) -> int:
        """Validate grid size is supported."""
        if v not in [3, 4, 5, 6]:
            raise ValueError(f'grid_size must be 3, 4, 5, or 6, got {v}')
        return v
    
    @model_validator(mode='after')
    def validate_path_constraints(self):
        """Validate path constraint relationships."""
        # Check min <= max
        if self.path_min_length > self.path_max_length and self.path_max_length > 0:
            raise ValueError(
                f'path_min_length ({self.path_min_length}) cannot exceed '
                f'path_max_length ({self.path_max_length})'
            )
        
        # Check prefix length
        if len(self.path_prefix) > self.path_max_length:
            raise ValueError(
                f'path_prefix length ({len(self.path_prefix)}) exceeds '
                f'path_max_length ({self.path_max_length})'
            )
        
        # Check suffix length
        if len(self.path_suffix) > self.path_max_length:
            raise ValueError(
                f'path_suffix length ({len(self.path_suffix)}) exceeds '
                f'path_max_length ({self.path_max_length})'
            )
        
        # Check combined prefix + suffix
        if len(self.path_prefix) + len(self.path_suffix) > self.path_max_length:
            raise ValueError(
                f'Combined prefix+suffix length exceeds path_max_length'
            )
        
        # Check for conflicts with excluded nodes
        prefix_set = set(self.path_prefix)
        suffix_set = set(self.path_suffix)
        excluded_set = set(self.excluded_nodes)
        
        if overlap := prefix_set & excluded_set:
            raise ValueError(f'path_prefix contains excluded nodes: {overlap}')
        if overlap := suffix_set & excluded_set:
            raise ValueError(f'path_suffix contains excluded nodes: {overlap}')
        
        return self

    @classmethod
    def load_config(cls, config_file_path: str) -> 'Config':
        """Load configuration from YAML file.
        
        Args:
            config_file_path: Path to the YAML configuration file
            
        Returns:
            Config object with loaded and validated configuration
            
        Raises:
            ValueError: If file not found or invalid YAML
            ValidationError: If configuration values fail Pydantic validation
        """
        try:
            with open(config_file_path, 'r') as f:
                config_data = yaml.safe_load(f)
        except FileNotFoundError:
            raise ValueError(f"Configuration file not found: {config_file_path}")
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {config_file_path}: {e}")

        # Handle nested outputstrings for backward compatibility
        output_strings = config_data.get('outputstrings', {})
        
        # Convert all node lists to strings for consistency
        def to_string_list(lst):
            return [str(item) for item in lst] if lst else []
        
        # Prepare data dict for Pydantic - it will handle type coercion and validation
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
            'stdout_normal': output_strings.get('stdout_normal', ''),
            'stdout_success': output_strings.get('stdout_success', ''),
            'stdout_error': output_strings.get('stdout_error', ''),
            'paths_log_file_path': config_data.get('paths_log_file_path', './paths_log.csv'),
            'process_log_file_path': config_data.get('process_log_file_path', './process_log.csv'),
            'adb_timeout': config_data.get('adb_timeout', 30),
            'total_paths': config_data.get('total_paths', 0),
            'echo_commands': config_data.get('echo_commands', True)
        }
        
        # Pydantic will automatically validate using Field constraints and validators
        return cls(**config_dict)

    def __repr__(self) -> str:
        """String representation of Config."""
        return f"Config(grid={self.grid_size}x{self.grid_size}, len={self.path_min_length}-{self.path_max_length})"