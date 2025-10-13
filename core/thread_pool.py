# core/thread_pool.py
from PySide6.QtCore import QThreadPool
_thread_pool = QThreadPool.globalInstance()

def run_in_thread(worker):
    _thread_pool.start(worker)
