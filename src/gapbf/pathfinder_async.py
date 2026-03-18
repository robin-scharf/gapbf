from __future__ import annotations

from concurrent.futures import Future
from threading import Thread
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .PathFinder import PathFinder


def _run_async(callback) -> Future[int]:
    future: Future[int] = Future()

    def runner() -> None:
        if not future.set_running_or_notify_cancel():
            return
        try:
            future.set_result(callback())
        except Exception as error:
            future.set_exception(error)

    Thread(target=runner, name="gapbf-total-paths", daemon=True).start()
    return future


def calculate_total_paths_async(path_finder: PathFinder) -> Future[int]:
    return path_finder.calculate_total_paths_async()
