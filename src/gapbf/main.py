import typer

from .cli_definitions import console, handler_classes
from .cli_helpers import (
    check_device_command_impl,
    generate_sample_paths,
    history_command_impl,
    status_command_impl,
    validate_mode,
)
from .cli_live import (
    LiveRunState,
)
from .cli_live import (
    handle_live_keypress as _handle_live_keypress,
)
from .cli_live import (
    should_auto_count_status_totals as _should_auto_count_status_totals,
)
from .cli_runner import run_command_impl
from .Config import Config
from .Database import detect_device_id
from .PathFinder import PathFinder
from .runtime import load_resume_context, open_run_session

app = typer.Typer(
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=True,
)


def create_path_finder(config: Config) -> PathFinder:
    return PathFinder(
        config.grid_size,
        config.path_min_length,
        config.path_max_length,
        config.path_max_node_distance,
        config.path_prefix,
        config.path_suffix,
        config.excluded_nodes,
    )


def _generate_sample_paths(path_finder, limit=10):
    yield from generate_sample_paths(path_finder, limit)


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    mode: str | None = typer.Option(
        None,
        "--mode",
        "-m",
        callback=lambda value: validate_mode(value) if value is not None else None,
    ),
    config: str = typer.Option("config.yaml", "--config", "-c"),
    log_level: str = typer.Option("error", "--logging", "-l"),
    log_file: str | None = typer.Option(None, "--log-file"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    if mode is None:
        console.print(ctx.get_help())
        raise typer.Exit(code=0)
    from .Logging import setup_logging

    run_command_impl(mode, config, log_level, log_file, dry_run, setup_logging)


@app.command("run")
def run_command(
    mode: str = typer.Option(..., "--mode", "-m", callback=validate_mode),
    config: str = typer.Option("config.yaml", "--config", "-c"),
    log_level: str = typer.Option("error", "--logging", "-l"),
    log_file: str | None = typer.Option(None, "--log-file"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Run the brute-force search."""
    from .Logging import setup_logging

    run_command_impl(mode, config, log_level, log_file, dry_run, setup_logging)


@app.command("history")
def history_command(
    config: str = typer.Option("config.yaml", "--config", "-c"),
    limit: int = typer.Option(20, min=1, max=200),
) -> None:
    """Show recent run history from the SQLite store."""
    _ = limit
    history_command_impl(config)


@app.command("check-device")
def check_device_command(
    config: str = typer.Option("config.yaml", "--config", "-c"),
) -> None:
    """Verify ADB connectivity and show the active device serial."""
    check_device_command_impl(config)


@app.command("status")
def status_command(
    config: str = typer.Option("config.yaml", "--config", "-c"),
    mode: str = typer.Option("a", "--mode", "-m", callback=validate_mode),
    calculate_total_paths: bool = typer.Option(
        False,
        "--calculate-total-paths",
        help="Compute an exact total path count. This can be slow for large configs.",
    ),
) -> None:
    """Show current config, device connectivity, and resume state."""
    status_command_impl(config, mode, calculate_total_paths)


@app.command("web")
def web_command(
    config: str = typer.Option("config.yaml", "--config", "-c"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port", min=1, max=65535),
    log_level: str = typer.Option("error", "--logging", "-l"),
    log_file: str | None = typer.Option(None, "--log-file"),
) -> None:
    """Serve the local web UI for controlling and monitoring GAPBF."""
    from .web import serve_web_ui

    console.print(f"Serving GAPBF web UI at http://{host}:{port}")
    console.print("Press Ctrl+C to stop the server")
    serve_web_ui(host=host, port=port, config_path=config, log_level=log_level, log_file=log_file)


def main() -> None:
    try:
        app()
    except typer.Exit as error:
        raise SystemExit(error.exit_code) from error


if __name__ == "__main__":
    main()


__all__ = [
    "LiveRunState",
    "_handle_live_keypress",
    "app",
    "create_path_finder",
    "detect_device_id",
    "handler_classes",
    "load_resume_context",
    "open_run_session",
    "_should_auto_count_status_totals",
    "validate_mode",
]
