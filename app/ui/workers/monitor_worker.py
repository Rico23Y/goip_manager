from PySide6.QtCore import QObject, Signal


class MonitorWorker(QObject):
    finished = Signal()

    def __init__(self, run_callback) -> None:
        super().__init__()
        self.run_callback = run_callback

    def run(self) -> None:
        self.run_callback()
        self.finished.emit()
