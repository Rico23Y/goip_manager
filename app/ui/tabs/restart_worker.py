from PySide6.QtCore import QThread, Signal

from app.repositories.device_repository import DeviceRepository
from app.services.restart_service import launch_restart_tabs


class RestartWorker(QThread):
    """Run a GOIP restart operation in a background thread."""

    finished = Signal()

    def __init__(
        self,
        device_repository: DeviceRepository,
        device_index: int,
    ) -> None:
        super().__init__()
        self.device_repository = device_repository
        self.device_index = device_index

    def run(self) -> None:
        try:
            try:
                launch_restart_tabs(
                    self.device_repository,
                    self.device_index + 1,
                )
            except Exception:
                pass
        finally:
            self.finished.emit()
