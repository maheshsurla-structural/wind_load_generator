# core/worker.py
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
import traceback, sys

class WorkerSignals(QObject):
    finished = Signal(object)     # result or None
    error = Signal(str)           # formatted traceback
    progress = Signal(int)        # 0–100
    status = Signal(str)          # message

class Worker(QRunnable):
    """
    Generic worker for running functions in background threads.
    """

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.finished.emit(result)
        except Exception:
            exc_type, value, tb = sys.exc_info()
            trace = "".join(traceback.format_exception(exc_type, value, tb))
            self.signals.error.emit(trace)
