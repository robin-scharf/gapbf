# GAPBF (Graph-based Android Pattern Brute Force) - AI Coding Instructions

## Project Overview

This is a Python-based Android pattern brute force tool that uses TWRP recovery and ADB to attempt pattern decryption. The architecture follows a handler pattern where different execution modes (ADB, Test, Print) implement the same interface.

## Core Architecture

### Handler Pattern Implementation

- **PathHandler**: Abstract base class defining `handle_path()` interface
- **ADBHandler**: Executes actual ADB commands against Android device via TWRP
- **TestHandler**: Mock handler for testing against known patterns
- **PrintHandler**: Visual debugging handler that renders patterns as grids
- **LogHandler**: CSV logging for attempt tracking

### Configuration System

- **Config.py**: Dataclass-based configuration with YAML loading via `Config.load_config()`
- **config.yaml**: Central configuration file for grid size, path constraints, ADB settings
- Configuration is loaded once and shared across all handlers via `self.config = Config.load_config('config.yaml')`

### Path Generation Engine

- **PathFinder**: Core class containing hardcoded graph definitions for 3x3, 4x4, 5x5, 6x6 grids
- Uses depth-first search (DFS) with backtracking for path generation
- Supports path constraints: prefix, suffix, excluded nodes, min/max length
- Pre-calculates `total_paths` and updates `config.yaml` with the count

## Key Implementation Details

### Grid System

Android pattern grids use specific character mappings:

- 3x3: nodes 1-9
- 4x4: nodes 1-9 plus `:;<=?>@`
- 5x5: extends to include `@ABCDEFGHI`
- 6x6: extends to `OPQRST` (assumed mapping)

### TWRP Integration

- Uses `adb shell twrp decrypt <pattern>` commands
- Enforces 10-second timeout between attempts (TWRP limitation)
- Parses stdout for success/failure strings defined in config
- Tracks attempted paths in CSV to avoid duplicates on restart

### Command Line Interface

```bash
python3 main.py -m ap  # ADB + Print handlers
python3 main.py -m t   # Test handler only
```

## Development Patterns

### Error Handling

- Type validation in Config dataclass `__post_init__`
- Subprocess timeout handling with graceful exit
- CSV file creation/reading with malformed row handling

### Logging Strategy

- Singleton Logger class with configurable levels
- Separate process logging vs paths logging (CSV format)
- Timestamps in format: `%Y-%m-%d %H:%M:%S`

### File Organization

- Single-purpose classes in separate files
- Configuration loaded once per handler initialization
- CSV logging uses absolute paths from config

## Testing Approach

- TestHandler compares against `test_path` from config
- No formal test framework - uses built-in test mode
- Manual verification via PrintHandler visual output

## Common Operations

### Adding New Handler

1. Inherit from PathHandler
2. Implement `handle_path(self, path) -> Tuple[bool, List]`
3. Add to `handler_classes` dict in main.py with single-letter key
4. Return (True, path) for success, (False, None) for failure

### Modifying Grid Definitions

- Edit `_graphs` dict in PathFinder class
- Update both "graph" (node list) and "neighbors" (adjacency) entries
- Ensure neighbor relationships are bidirectional

### Configuration Changes

- Modify config.yaml for runtime settings
- Update Config dataclass if adding new fields
- Regenerate total_paths by running with new config

## Dependencies

- PyYAML for configuration loading
- Standard library: subprocess, csv, logging, dataclasses
- ADB must be available in PATH for ADBHandler
