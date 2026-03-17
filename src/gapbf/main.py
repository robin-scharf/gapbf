import logging
import sys
import time
from itertools import islice

from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table
import typer

from .Config import Config
from .Database import ResumeInfo, RunDatabase, detect_device_id
from .Output import Output
from .PathFinder import PathFinder
from .PathHandler import ADBHandler, PrintHandler, TestHandler
from .Logging import setup_logging

app = typer.Typer(
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=True,
)
console = Console()
output = Output(console)


handler_classes = {
    'a': {'class': ADBHandler, 'help': 'Attempt decryption via ADB shell on Android device'},
    'p': {'class': PrintHandler, 'help': 'Print attempted paths to the console'},
    't': {'class': TestHandler, 'help': 'Run mock brute force against test_path in config'},
}


def validate_mode(value):
    valid_modes = ''.join(handler_classes.keys())
    if not set(value).issubset(set(valid_modes)):
        available_options = ', '.join(valid_modes)
        raise typer.BadParameter(
            f"Invalid mode: {value}. Allowed values are combinations of {available_options}.")
    return value


def _generate_sample_paths(path_finder, limit=10):
    """Generate a limited number of sample paths for dry-run mode.
    
    Args:
        path_finder: PathFinder instance
        limit: Maximum number of paths to generate
        
    Yields:
        Path lists
    """
    yield from islice(path_finder, limit)


def _load_config(config_path: str, logger: logging.Logger) -> Config:
    try:
        config = Config.load_config(config_path)
        logger.info(f"Loaded configuration from {config_path}")
        return config
    except Exception as error:
        logger.error(f"Failed to load configuration: {error}")
        raise typer.Exit(code=1) from error


def _build_path_finder(config: Config, logger: logging.Logger) -> PathFinder:
    try:
        path_finder = PathFinder(
            config.grid_size,
            config.path_min_length,
            config.path_max_length,
            config.path_max_node_distance,
            config.path_prefix,
            config.path_suffix,
            config.excluded_nodes,
        )
        logger.info(f"Initialized PathFinder with {path_finder.total_paths} total possible paths")
        return path_finder
    except Exception as error:
        logger.error(f"Failed to initialize PathFinder: {error}")
        raise typer.Exit(code=1) from error


def _print_dry_run_summary(config: Config, path_finder: PathFinder) -> None:
    summary = Table(title="Dry Run", show_header=False)
    summary.add_column("Field", style="cyan")
    summary.add_column("Value")
    summary.add_row("Total paths", f"{path_finder.total_paths:,}")
    summary.add_row("Grid", f"{config.grid_size}x{config.grid_size}")
    summary.add_row("Length", f"{config.path_min_length} to {config.path_max_length}")
    summary.add_row("Prefix", str(config.path_prefix or 'None'))
    summary.add_row("Suffix", str(config.path_suffix or 'None'))
    summary.add_row("Excluded", str(list(config.excluded_nodes) if config.excluded_nodes else 'None'))
    console.print(summary)

    sample_table = Table(title="First Paths")
    sample_table.add_column("#", justify="right")
    sample_table.add_column("Path")
    for count, path in enumerate(_generate_sample_paths(path_finder, 10), start=1):
        sample_table.add_row(str(count), ''.join(path))
    console.print(sample_table)


def _print_resume_summary(resume_info: ResumeInfo) -> None:
    output.show_resume(
        resume_info.attempted_count,
        status=resume_info.latest_status,
        started_at=resume_info.latest_started_at,
    )


def _add_handlers(
    path_finder: PathFinder,
    config: Config,
    mode: str,
    logger: logging.Logger,
    database: RunDatabase | None,
    run_id: str | None,
    device_id: str | None,
) -> None:
    for mode_key in mode:
        handler_class = handler_classes[mode_key]['class']
        try:
            if handler_class == PrintHandler:
                handler = handler_class(config, path_finder.grid_nodes, output)
            elif handler_class == ADBHandler:
                if database is None or run_id is None or device_id is None:
                    raise RuntimeError('ADB mode requires an initialized run database and device id')
                handler = handler_class(
                    config,
                    database=database,
                    run_id=run_id,
                    device_id=device_id,
                    output=output,
                )
            else:
                handler = handler_class(config, output)
            path_finder.add_handler(handler)
            logger.info(f"Added handler: {handler_class.__name__}")
        except Exception as error:
            logger.error(f"Failed to initialize {handler_class.__name__}: {error}")
            raise typer.Exit(code=1) from error


def _print_run_summary(
    config: Config,
    path_finder: PathFinder,
    mode: str,
    resume_info: ResumeInfo | None = None,
    device_id: str | None = None,
) -> None:
    handler_names = ', '.join([handler_classes[item]['class'].__name__ for item in mode])
    summary = Table(title="GAPBF Run Summary", show_header=False)
    summary.add_column("Field", style="cyan")
    summary.add_column("Value")
    summary.add_row("Grid", f"{config.grid_size}x{config.grid_size}")
    summary.add_row("Path length", f"{config.path_min_length} to {config.path_max_length}")
    summary.add_row("Prefix", str(config.path_prefix or 'None'))
    summary.add_row("Suffix", str(config.path_suffix or 'None'))
    summary.add_row("Excluded", str(config.excluded_nodes or 'None'))
    summary.add_row("Total paths", f"{path_finder.total_paths:,}")
    summary.add_row("Handlers", handler_names)
    if device_id is not None:
        summary.add_row("Device", device_id)
    if resume_info is not None:
        summary.add_row("Resumable attempts", f"{resume_info.attempted_count:,}")
        summary.add_row("Latest run status", str(resume_info.latest_status or 'None'))
        summary.add_row("Latest success", str(resume_info.latest_successful_attempt or 'None'))
    console.print(summary)


def _execute_search(
    path_finder: PathFinder,
    logger: logging.Logger,
    database: RunDatabase | None,
    run_id: str | None,
    db_path: str,
) -> None:
    attempted_count = 0
    if path_finder.handlers and hasattr(path_finder.handlers[0], 'attempted_paths'):
        attempted_count = len(path_finder.handlers[0].attempted_paths)
        if attempted_count > 0:
            console.print(f"Resuming with {attempted_count:,} previously attempted paths")

    logger.info("Starting brute force search")
    start_time = time.time()

    try:
        success = False
        successful_path = None
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed:,.0f}/{task.total:,.0f}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task("Searching paths", total=path_finder.total_paths, completed=attempted_count)
            original_process = path_finder.process_path

            def process_with_progress(path):
                result_success, result_path = original_process(path)
                progress.update(task_id, advance=1)
                return result_success, result_path

            path_finder.process_path = process_with_progress
            try:
                success, successful_path = path_finder.dfs()
            finally:
                path_finder.process_path = original_process

        elapsed_time = time.time() - start_time
        hours, remainder = divmod(int(elapsed_time), 3600)
        minutes, seconds = divmod(remainder, 60)

        if success:
            if database is not None and run_id is not None and successful_path is not None:
                database.finish_run(run_id, 'success', ''.join(successful_path))
            console.print(f"Success: pattern found {successful_path}")
            console.print(f"Elapsed: {hours:02d}:{minutes:02d}:{seconds:02d}")
            logger.info(f"Successfully found pattern: {successful_path} in {elapsed_time:.2f}s")
            return

        if database is not None and run_id is not None:
            database.finish_run(run_id, 'completed')
        console.print("Search completed without finding a successful pattern")
        console.print(f"Elapsed: {hours:02d}:{minutes:02d}:{seconds:02d}")
        if database is not None:
            console.print(f"History: {db_path}")
        logger.info(f"Search completed without finding successful pattern after {elapsed_time:.2f}s")
    except KeyboardInterrupt:
        if database is not None and run_id is not None:
            database.finish_run(run_id, 'interrupted')
        elapsed_time = time.time() - start_time
        hours, remainder = divmod(int(elapsed_time), 3600)
        minutes, seconds = divmod(remainder, 60)
        console.print("Search interrupted by user")
        console.print(f"Elapsed: {hours:02d}:{minutes:02d}:{seconds:02d}")
        logger.info("Search interrupted by user")
        raise typer.Exit(code=0)
    except typer.Exit:
        raise
    except Exception as error:
        if database is not None and run_id is not None:
            database.finish_run(run_id, 'error')
        logger.error(f"Error during search: {error}", exc_info=True)
        raise typer.Exit(code=1) from error


def _run_command(mode: str, config_path: str, log_level: str, log_file: str | None, dry_run: bool) -> None:
    setup_logging(log_level, log_file)
    logger = logging.getLogger('gapbf')
    config = _load_config(config_path, logger)
    path_finder = _build_path_finder(config, logger)

    database = None
    run_info = None
    resume_info = None
    if 'a' in mode and not dry_run:
        try:
            database = RunDatabase(config.db_path)
            device_id = detect_device_id(config.adb_timeout)
            resume_info = database.get_resume_info(config, device_id)
            run_info = database.create_run(config, device_id, mode)
            logger.info(f"Created run {run_info.run_id} for device {run_info.device_id}")
        except Exception as error:
            logger.error(f"Failed to initialize SQLite run logging: {error}")
            raise typer.Exit(code=1) from error

    if dry_run:
        _print_dry_run_summary(config, path_finder)
        return

    _add_handlers(
        path_finder,
        config,
        mode,
        logger,
        database,
        run_info.run_id if run_info else None,
        run_info.device_id if run_info else None,
    )
    if resume_info is not None and resume_info.attempted_count > 0:
        _print_resume_summary(resume_info)
    _print_run_summary(config, path_finder, mode, resume_info, run_info.device_id if run_info else None)

    try:
        _execute_search(
            path_finder,
            logger,
            database,
            run_info.run_id if run_info else None,
            config.db_path,
        )
    finally:
        if database is not None:
            database.close()


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    mode: str | None = typer.Option(None, "--mode", "-m", callback=lambda value: validate_mode(value) if value is not None else None),
    config: str = typer.Option('config.yaml', "--config", "-c"),
    log_level: str = typer.Option('error', "--logging", "-l"),
    log_file: str | None = typer.Option(None, "--log-file"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    if mode is None:
        console.print(ctx.get_help())
        raise typer.Exit(code=0)
    _run_command(mode, config, log_level, log_file, dry_run)


@app.command("run")
def run_command(
    mode: str = typer.Option(..., "--mode", "-m", callback=validate_mode),
    config: str = typer.Option('config.yaml', "--config", "-c"),
    log_level: str = typer.Option('error', "--logging", "-l"),
    log_file: str | None = typer.Option(None, "--log-file"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Run the brute-force search."""
    _run_command(mode, config, log_level, log_file, dry_run)


@app.command("history")
def history_command(
    config: str = typer.Option('config.yaml', "--config", "-c"),
    limit: int = typer.Option(20, min=1, max=200),
) -> None:
    """Show recent run history from the SQLite store."""
    logger = logging.getLogger('gapbf')
    run_config = _load_config(config, logger)
    database = RunDatabase(run_config.db_path)
    try:
        rows = database.list_runs(limit)
    finally:
        database.close()

    if not rows:
        console.print("No recorded runs found")
        return

    table = Table(title="Recent Runs")
    table.add_column("Run")
    table.add_column("Started")
    table.add_column("Status")
    table.add_column("Mode")
    table.add_column("Device")
    table.add_column("Attempts", justify="right")
    table.add_column("Success")
    for row in rows:
        table.add_row(
            row['run_id'][:8],
            row['started_at'],
            row['status'],
            row['mode'],
            row['device_id'],
            str(row['attempt_count']),
            row['successful_attempt'] or '-',
        )
    console.print(table)


@app.command("check-device")
def check_device_command(
    config: str = typer.Option('config.yaml', "--config", "-c"),
) -> None:
    """Verify ADB connectivity and show the active device serial."""
    logger = logging.getLogger('gapbf')
    run_config = _load_config(config, logger)
    try:
        device_id = detect_device_id(run_config.adb_timeout)
    except RuntimeError as error:
        console.print(f"Device check failed: {error}")
        raise typer.Exit(code=1) from error

    table = Table(title="ADB Device")
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("Device", device_id)
    table.add_row("ADB timeout", f"{run_config.adb_timeout}s")
    console.print(table)


@app.command("status")
def status_command(
    config: str = typer.Option('config.yaml', "--config", "-c"),
    mode: str = typer.Option('a', "--mode", "-m", callback=validate_mode),
) -> None:
    """Show current config, device connectivity, and resume state."""
    logger = logging.getLogger('gapbf')
    run_config = _load_config(config, logger)
    path_finder = _build_path_finder(run_config, logger)

    device_id = None
    resume_info = None
    if 'a' in mode:
        try:
            device_id = detect_device_id(run_config.adb_timeout)
        except RuntimeError as error:
            console.print(f"Device check failed: {error}")
            raise typer.Exit(code=1) from error

        database = RunDatabase(run_config.db_path)
        try:
            resume_info = database.get_resume_info(run_config, device_id)
        finally:
            database.close()

    _print_run_summary(run_config, path_finder, mode, resume_info, device_id)


def main() -> None:
    try:
        app()
    except typer.Exit as error:
        raise SystemExit(error.exit_code) from error


if __name__ == "__main__":
    main()
