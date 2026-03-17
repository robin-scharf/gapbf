# GAPBF

[![Pipeline status on GitLab CI][pipeline-badge]][pipeline-link]

GAPBF is a Linux-first Python CLI for brute-forcing Android pattern locks through TWRP recovery using a graph-based path generator.

It is intended for legitimate device recovery scenarios where you control the device, can boot into TWRP, and want to constrain the search space using partial knowledge of the original unlock pattern.

## Current Status

- Typer-based CLI with Rich output
- SQLite-backed run history and attempt persistence
- Resume-aware status reporting
- Correctness-focused path generation for Android-style pattern movement rules
- Tested with `pytest` and packaged via `uv`

## Constraints

- Linux-focused workflow
- Requires `adb` access to a device already booted into TWRP
- TWRP enforces an effective per-attempt delay; this project does not bypass that limit
- Large search spaces are still expensive, so partial pattern knowledge matters
- 6x6 pattern support is still based on an assumed mapping and should be treated as experimental

## How It Works

GAPBF generates valid pattern paths for Android-style grids and evaluates them through one or more handlers:

- `a`: send attempts to TWRP via `adb shell twrp decrypt ...`
- `p`: print generated paths for inspection/debugging
- `t`: compare generated paths against a configured test path

Run and attempt metadata is stored in SQLite so interrupted sessions can be inspected later with the CLI.

## Requirements

- Linux
- Python 3.11 or newer
- `uv`
- `adb`
- A device with pattern lock support and TWRP recovery available

## Installation

```bash
git clone git@github.com:robin-scharf/gapbf.git
cd gapbf
uv sync --dev
```

## Quick Start

Inspect the available commands:

```bash
uv run gapbf --help
```

Check that the device is visible to ADB/TWRP:

```bash
adb devices
uv run gapbf check-device
```

Review current configuration and resume state:

```bash
uv run gapbf status
```

Run the brute-force process:

```bash
uv run gapbf run -m a
```

Use combined modes when needed:

```bash
uv run gapbf run -m ap
uv run gapbf run -m t
```

Review stored run history:

```bash
uv run gapbf history
uv run gapbf history --limit 10
```

Legacy-compatible invocation is still supported:

```bash
uv run gapbf -m ap
```

## Configuration

Runtime configuration lives in [`config.yaml`](./config.yaml).

Important fields include:

- `grid_size`
- `path_min_length`
- `path_max_length`
- `path_max_node_distance`
- `path_prefix`
- `path_suffix`
- `excluded_nodes`
- `attempt_delay`
- `adb_timeout`
- `db_path`
- `stdout_normal`
- `stdout_success`
- `stdout_error`

Constrain the pattern space as aggressively as possible. Prefixes, suffixes, excluded nodes, and realistic path lengths have a much larger effect on runtime than implementation-level optimizations because TWRP remains the throughput bottleneck.

## Grid Mappings

3x3, 4x4, and 5x5 pattern grids are supported explicitly. The 6x6 mapping remains an informed assumption based on available TWRP and community references and is not yet independently verified.

Example 3x3 grid:

```text
[
    [1, 2, 3],
    [4, 5, 6],
    [7, 8, 9]
]
```

Example 4x4 grid:

```text
[
    [1, 2, 3, 4],
    [5, 6, 7, 8],
    [9, :, ;, <],
    [=, >, ?, @]
]
```

Example 5x5 grid:

```text
[
    [1, 2, 3, 4, 5],
    [6, 7, 8, 9, :],
    [;, <, =, >, ?],
    [@, A, B, C, D],
    [E, F, G, H, I]
]
```

Current 6x6 assumption:

```text
[
    [1, 2, 3, 4, 5, 6],
    [7, 8, 9, :, ;, <],
    [=, >, ?, @, A, B],
    [C, D, E, F, G, H],
    [I, J, K, L, M, N],
    [O, P, Q, R, S, T]
]
```

## Development

Run tests:

```bash
uv run python -m pytest
```

The project is packaged from [`src/gapbf`](./src/gapbf) and exposes the `gapbf` console script via [`pyproject.toml`](./pyproject.toml).

## Roadmap

See [`NEXT_STEPS.md`](./NEXT_STEPS.md) for follow-up work, known gaps, and suggested improvements before broader public distribution.

## License

This project is released under the GNU GPL-3.0 license. See [LICENSE](LICENSE) for details.

[pipeline-badge]: https://gitlab.com/timvisee/apbf/badges/master/pipeline.svg
[pipeline-link]: https://gitlab.com/timvisee/apbf/pipelines
