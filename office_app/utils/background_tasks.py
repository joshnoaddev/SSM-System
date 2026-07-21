"""Small Qt-native adapter for running blocking work off the UI thread."""

from __future__ import annotations

import traceback
from typing import Any, Callable

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot


class TaskSignals(QObject):
    """Signals emitted by :class:`BackgroundTask` on the Qt event loop."""

    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()


class BackgroundTask(QRunnable):
    """Run a callable in ``QThreadPool`` and marshal its result back to Qt."""

    def __init__(self, function: Callable[[], Any]) -> None:
        super().__init__()
        self.function = function
        self.signals = TaskSignals()
        self.done = False

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = self.function()
        except Exception:
            self.signals.failed.emit(traceback.format_exc())
        else:
            self.signals.succeeded.emit(result)
        finally:
            self.done = True
            self.signals.finished.emit()
