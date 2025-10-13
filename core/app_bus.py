# core/app_bus.py
from PySide6.QtCore import QObject, Signal

class AppBus(QObject):
    """
    Centralized global signal hub for the entire application.
    Any widget or controller can subscribe or emit.
    """

    # ---- Unit system ----
    unitsChanged = Signal(str, str)  # (length, force)

    # ---- Control data ----
    controlDataChanged = Signal(object)  # ControlDataModel

    # ---- Wind load input ----
    windGroupsUpdated = Signal(object)  # WindLoadInputModel

    # ---- Pair load cases ----
    pairCasesUpdated = Signal(object)  # PairWindLoadModel

    # ---- Progress / status ----
    progressStarted = Signal(str)      # message
    progressUpdated = Signal(int)      # %
    progressFinished = Signal(bool, str)  # success, message


# Singleton pattern
_app_bus: AppBus | None = None

def get_app_bus() -> AppBus:
    global _app_bus
    if _app_bus is None:
        _app_bus = AppBus()
    return _app_bus
