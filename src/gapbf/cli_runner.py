import logging
import time

import typer

from .cli_definitions import console
from .cli_helpers import (
    build_path_finder,
    load_config,
    print_dry_run_summary,
    print_resume_summary,
    print_run_summary,
    resolve_total_paths,
)
from .cli_live import (
    LiveRunState,
    drive_live_dashboard,
    format_elapsed,
    render_live_dashboard,
    run_in_background,
)
from .Output import Output
from .runtime import RunController, RunSession, UserRequestedStop


def execute_search(
    path_finder,
    logger: logging.Logger,
    session: RunSession,
    db_path: str,
    state: LiveRunState,
    total_paths_future,
) -> None:
    logger.info("Starting brute force search")
    state.set_search_status("Running")
    controller = RunController(state)
    search_future = run_in_background(lambda: controller.execute_search(path_finder))
    start_time = time.monotonic()
    try:
        drive_live_dashboard(
            state,
            "GAPBF Live Run",
            total_paths_future,
            allow_pause=True,
            done_callback=search_future.done,
        )
        success, successful_path = search_future.result()
        elapsed_time = time.monotonic() - start_time
        if success:
            if successful_path is not None:
                session.finish("success", successful_path)
            console.print(render_live_dashboard(state, "GAPBF Live Run", allow_pause=True))
            console.print(f"Success: pattern found {successful_path}")
            console.print(f"Elapsed: {format_elapsed(elapsed_time)}")
            logger.info(f"Successfully found pattern: {successful_path} in {elapsed_time:.2f}s")
            return
        state.mark_completed()
        session.finish("completed")
        console.print(render_live_dashboard(state, "GAPBF Live Run", allow_pause=True))
        console.print("Search completed without finding a successful pattern")
        console.print(f"Elapsed: {format_elapsed(elapsed_time)}")
        if session.database is not None:
            console.print(f"History: {db_path}")
        logger.info(
            f"Search completed without finding successful pattern after {elapsed_time:.2f}s"
        )
    except UserRequestedStop:
        state.mark_interrupted()
        session.finish("interrupted")
        console.print(render_live_dashboard(state, "GAPBF Live Run", allow_pause=True))
        console.print("Search stopped by operator request")
        console.print(f"Elapsed: {format_elapsed(time.monotonic() - start_time)}")
        raise typer.Exit(code=0)
    except KeyboardInterrupt:
        state.mark_interrupted()
        session.finish("interrupted")
        console.print(render_live_dashboard(state, "GAPBF Live Run", allow_pause=True))
        console.print("Search interrupted by user")
        console.print(f"Elapsed: {format_elapsed(time.monotonic() - start_time)}")
        raise typer.Exit(code=0)
    except typer.Exit:
        raise
    except Exception as error:
        state.mark_error(str(error))
        session.finish("error")
        logger.error(f"Error during search: {error}", exc_info=True)
        raise typer.Exit(code=1) from error


def run_command_impl(
    mode: str,
    config_path: str,
    log_level: str,
    log_file: str | None,
    dry_run: bool,
    setup_logging,
) -> None:
    from . import main as main_module

    setup_logging(log_level, log_file)
    logger = logging.getLogger("gapbf")
    config = load_config(config_path, logger)
    if dry_run:
        path_finder = build_path_finder(config, logger)
        total_paths = resolve_total_paths(config, path_finder, logger, calculate=False)
        print_dry_run_summary(config, total_paths, path_finder)
        return
    state = LiveRunState(config=config, mode=mode, total_paths=None, paths_tested=0)
    output_adapter = Output(
        console,
        silent=True,
        event_sink=lambda _event, payload: state.set_feedback(str(payload.get("message", _event))),
    )
    try:
        session = main_module.open_run_session(config, mode, output_adapter)
        logger.info(
            "Prepared run session for mode=%s device=%s run_id=%s",
            mode,
            session.device_id or "None",
            session.run_id or "None",
        )
    except Exception as error:
        logger.error(f"Failed to initialize run session: {error}")
        raise typer.Exit(code=1) from error
    path_finder = session.path_finder
    total_paths = resolve_total_paths(config, path_finder, logger, calculate=False)
    state.total_paths = total_paths
    if total_paths is not None:
        state.total_paths_state = "ready"
    session.attach_state(state)
    if session.resume_info is not None and session.resume_info.attempted_count > 0:
        print_resume_summary(session.resume_info)
    print_run_summary(config, mode, total_paths, session.resume_info, session.device_id)
    total_paths_future = None
    if total_paths is None:
        state.mark_total_paths_counting()
        total_paths_future = path_finder.calculate_total_paths_async()
    try:
        execute_search(path_finder, logger, session, config.db_path, state, total_paths_future)
    finally:
        session.close()
