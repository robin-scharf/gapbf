import logging
from itertools import islice

import typer
from rich.table import Table

from .cli_definitions import console, output
from .cli_live import (
    LiveRunState,
    drive_live_dashboard,
    render_live_dashboard,
)
from .Config import Config
from .Database import ResumeInfo, RunDatabase
from .PathFinder import PathFinder


def validate_mode(value):
    valid_modes = "apt"
    if not set(value).issubset(set(valid_modes)):
        raise typer.BadParameter(
            f"Invalid mode: {value}. Allowed values are combinations of {', '.join(valid_modes)}."
        )
    return value


def generate_sample_paths(path_finder, limit=10):
    yield from islice(path_finder, limit)


def load_config(config_path: str, logger: logging.Logger) -> Config:
    try:
        config = Config.load_config(config_path)
        logger.info(f"Loaded configuration from {config_path}")
        return config
    except Exception as error:
        logger.error(f"Failed to load configuration: {error}")
        raise typer.Exit(code=1) from error


def build_path_finder(config: Config, logger: logging.Logger) -> PathFinder:
    from . import main as main_module

    try:
        path_finder = main_module.create_path_finder(config)
        logger.info("Initialized PathFinder")
        return path_finder
    except Exception as error:
        logger.error(f"Failed to initialize PathFinder: {error}")
        raise typer.Exit(code=1) from error


def resolve_total_paths(
    config: Config, path_finder: PathFinder, logger: logging.Logger, *, calculate: bool
) -> int | None:
    if config.total_paths > 0 and not calculate:
        logger.info(f"Using configured total_paths={config.total_paths}")
        return config.total_paths
    if not calculate:
        logger.info("Skipping expensive total_paths calculation")
        return None
    total_paths = path_finder.total_paths
    logger.info(f"Calculated total_paths={total_paths}")
    return total_paths


def format_total_paths(total_paths: int | None) -> str:
    return f"{total_paths:,}" if total_paths is not None else "Unknown"


def print_dry_run_summary(config: Config, total_paths: int | None, path_finder: PathFinder) -> None:
    from . import main as main_module

    summary = Table(title="Dry Run", show_header=False)
    summary.add_column("Field", style="cyan")
    summary.add_column("Value")
    summary.add_row("Total paths", format_total_paths(total_paths))
    summary.add_row("Grid", f"{config.grid_size}x{config.grid_size}")
    summary.add_row("Length", f"{config.path_min_length} to {config.path_max_length}")
    summary.add_row("Prefix", str(config.path_prefix or "None"))
    summary.add_row("Suffix", str(config.path_suffix or "None"))
    summary.add_row(
        "Excluded", str(list(config.excluded_nodes) if config.excluded_nodes else "None")
    )
    console.print(summary)
    sample_table = Table(title="First Paths")
    sample_table.add_column("#", justify="right")
    sample_table.add_column("Path")
    for count, path in enumerate(main_module._generate_sample_paths(path_finder, 10), start=1):
        sample_table.add_row(str(count), "".join(path))
    console.print(sample_table)


def print_resume_summary(resume_info: ResumeInfo) -> None:
    output.show_resume(
        resume_info.attempted_count,
        status=resume_info.latest_status,
        started_at=resume_info.latest_started_at,
    )


def print_run_summary(
    config: Config,
    mode: str,
    total_paths: int | None,
    resume_info: ResumeInfo | None = None,
    device_id: str | None = None,
) -> None:
    summary = Table(title="GAPBF Run Summary", show_header=False)
    summary.add_column("Field", style="cyan")
    summary.add_column("Value")
    summary.add_row("Grid", f"{config.grid_size}x{config.grid_size}")
    summary.add_row("Path length", f"{config.path_min_length} to {config.path_max_length}")
    summary.add_row("Prefix", str(config.path_prefix or "None"))
    summary.add_row("Suffix", str(config.path_suffix or "None"))
    summary.add_row("Excluded", str(config.excluded_nodes or "None"))
    summary.add_row("Total paths", format_total_paths(total_paths))
    summary.add_row(
        "Handlers",
        ", ".join(
            item["class_"].__name__
            for item in [
                __import__("gapbf.cli_definitions", fromlist=["handler_classes"]).handler_classes[
                    key
                ]
                for key in mode
            ]
        ),
    )
    if device_id is not None:
        summary.add_row("Device", device_id)
    if resume_info is not None:
        summary.add_row("Resumable attempts", f"{resume_info.attempted_count:,}")
        summary.add_row("Latest run status", str(resume_info.latest_status or "None"))
        summary.add_row("Latest success", str(resume_info.latest_successful_attempt or "None"))
    console.print(summary)


def show_status_dashboard(
    config: Config,
    mode: str,
    device_id: str | None,
    resume_info: ResumeInfo | None,
    total_paths: int | None,
    total_paths_future,
) -> None:
    state = LiveRunState(
        config=config,
        mode=mode,
        total_paths=total_paths,
        total_paths_state="ready" if total_paths is not None else "unknown",
        paths_tested=resume_info.attempted_count if resume_info is not None else 0,
    )
    state.attach_device_id(device_id)
    state.attach_resume_info(resume_info)
    state.set_search_status("Status")
    state.set_feedback(
        "Waiting for exact total path count"
        if total_paths_future is not None
        else "Status is ready"
    )
    if total_paths_future is not None:
        state.mark_total_paths_counting()
        closed_early = drive_live_dashboard(
            state,
            "GAPBF Live Status",
            total_paths_future,
            allow_pause=False,
            done_callback=total_paths_future.done,
        )
        if closed_early:
            state.set_search_status("Closed")
            state.set_feedback("Status view closed by user")
    console.print(render_live_dashboard(state, "GAPBF Live Status", allow_pause=False))


def history_command_impl(config: str) -> None:
    logger = logging.getLogger("gapbf")
    run_config = load_config(config, logger)
    database = RunDatabase(run_config.db_path)
    try:
        rows = database.list_runs(20)
    finally:
        database.close()
    if not rows:
        console.print("No recorded runs found")
        return
    table = Table(title="Recent Runs")
    for column in ["Run", "Started", "Status", "Mode", "Device", "Attempts", "Success"]:
        table.add_column(column, justify="right" if column == "Attempts" else "left")
    for row in rows:
        table.add_row(
            row["run_id"][:8],
            row["started_at"],
            row["status"],
            row["mode"],
            row["device_id"],
            str(row["attempt_count"]),
            row["successful_attempt"] or "-",
        )
    console.print(table)


def check_device_command_impl(config: str) -> None:
    from . import main as main_module

    logger = logging.getLogger("gapbf")
    run_config = load_config(config, logger)
    try:
        device_id = main_module.detect_device_id(run_config.adb_timeout)
    except RuntimeError as error:
        console.print(f"Device check failed: {error}")
        raise typer.Exit(code=1) from error
    table = Table(title="ADB Device")
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("Device", device_id)
    table.add_row("ADB timeout", f"{run_config.adb_timeout}s")
    console.print(table)


def status_command_impl(config: str, mode: str, calculate_total_paths: bool) -> None:
    from . import main as main_module

    logger = logging.getLogger("gapbf")
    run_config = load_config(config, logger)
    path_finder = build_path_finder(run_config, logger)
    total_paths = resolve_total_paths(run_config, path_finder, logger, calculate=False)
    total_paths_future = None
    if total_paths is None and (
        calculate_total_paths or main_module._should_auto_count_status_totals()
    ):
        total_paths_future = path_finder.calculate_total_paths_async()
    device_id = None
    resume_info = None
    if "a" in mode:
        try:
            resume_context = main_module.load_resume_context(run_config)
            device_id = resume_context.device_id
            resume_info = resume_context.resume_info
        except RuntimeError as error:
            console.print(f"Device check failed: {error}")
            raise typer.Exit(code=1) from error
    show_status_dashboard(run_config, mode, device_id, resume_info, total_paths, total_paths_future)
