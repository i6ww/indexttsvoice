from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QThread, Signal


class AsyncJob(QThread):
    succeeded = Signal(object)
    failed = Signal(object)
    progress = Signal(object)

    def __init__(self, job: Callable[[Callable[[object], None]], Any]) -> None:
        super().__init__()
        self._job = job

    def run(self) -> None:
        try:
            result = asyncio.run(self._job(self.progress.emit))
        except BaseException as exc:  # noqa: BLE001 - surface worker errors in UI
            self.failed.emit(exc)
            return
        self.succeeded.emit(result)
