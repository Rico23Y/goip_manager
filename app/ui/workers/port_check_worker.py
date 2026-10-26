from threading import Event
from typing import Optional

from PySide6.QtCore import QObject, QRunnable, Signal

from app.goip.connection import is_port_open


class PortCheckSignals(QObject):
    result = Signal(str, str, bool)


class PortCheckWorker(QRunnable):
    def __init__(
        self,
        goip_label: str,
        ip: str,
        stop_event: Optional[Event] = None,
    ) -> None:
        super().__init__()
        self.goip_label = goip_label
        self.ip = ip
        self.stop_event = stop_event
        self.signals = PortCheckSignals()

    def run(self) -> None:
        if self.stop_event is not None and self.stop_event.is_set():
            return

        try:
            online = is_port_open(self.ip)
        except Exception as exc:
            print(f"Background thread error: {exc}")
            return

        if self.stop_event is not None and self.stop_event.is_set():
            return

        self.signals.result.emit(self.goip_label, self.ip, online)
