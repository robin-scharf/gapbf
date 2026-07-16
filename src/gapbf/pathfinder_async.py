from __future__ import annotations

from concurrent.futures import Future
from threading import Thread
from typing import Callable


def _run_async(callback: Callable[[], int]) -> Future[int]:
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
