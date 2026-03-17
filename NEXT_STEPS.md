# GAPBF Next Steps

This file tracks the most important remaining work after the current refactor and CLI modernization.

## What Is Already In Good Shape

- Path generation was reworked around Android-style movement legality instead of static graph shortcuts
- Configuration validation is centralized in Pydantic
- Run history and attempts are stored in SQLite
- The CLI now exposes `run`, `history`, `check-device`, and `status`
- Handler output is centralized instead of scattered across direct `print()` calls
- The current automated test suite is passing

## Known Gaps

### 1. Real-device validation still matters

The codebase is in a much stronger state, but final confidence still depends on exercising the CLI against an actual TWRP-connected device.

Recommended checks:

- Confirm `gapbf check-device` behaves correctly with and without a connected device
- Confirm `gapbf status` reports meaningful resume information across interrupted runs
- Confirm the configured `stdout_*` match strings align with the specific TWRP build in use

### 2. 6x6 support is still provisional

The 6x6 node mapping is currently based on an assumption, not a verified reference implementation.

Recommended follow-up:

- Validate the character mapping against real TWRP behavior or source references
- Add an explicit verification note or test fixture once the mapping is confirmed

### 3. CLI ergonomics can still improve

The CLI is now serviceable and much cleaner than before, but it is not yet fully polished.

Recommended follow-up:

- Add richer command help/examples
- Consider a dedicated `config validate` or `config show` command
- Consider a clearer distinction between operator-facing output and debug logging

### 4. Documentation can be expanded further

The README now reflects the current public state, but deeper operational docs would still help.

Recommended follow-up:

- Add a short troubleshooting section for common ADB/TWRP failures
- Add example recovery workflows for 3x3, 4x4, and 5x5 devices
- Add notes on database location, cleanup, and backup

### 5. Packaging and release work remains

The project is installable and runnable via `uv`, but it is not yet fully release-shaped.

Recommended follow-up:

- Decide on versioning and release cadence
- Add changelog/release notes workflow
- Consider publishing a first tagged release after device-level smoke testing

## Suggested Pre-PR / Pre-Release Checklist

- Run `uv run python -m pytest`
- Smoke-test `gapbf --help`
- Smoke-test `gapbf status`
- Smoke-test `gapbf history --limit 1`
- If hardware is available, smoke-test `gapbf check-device`
- Re-read `config.yaml` defaults for public-facing sanity
- Review README wording for any claims that are stronger than current evidence

## Longer-Term Ideas

- Add export/reporting commands for past runs
- Improve resume UX for multi-device or multi-config workflows
- Add stronger integration testing around database-backed resume behavior
- Consider structured logging for easier troubleshooting
- Consider packaging improvements for easier installation outside a development environment
