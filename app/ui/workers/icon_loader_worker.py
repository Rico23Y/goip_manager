import os

from PySide6.QtCore import Qt, QObject, Signal, QRunnable
from PySide6.QtGui import QPixmap


class IconLoaderSignals(QObject):
    result = Signal(object)


class IconLoaderWorker(QRunnable):
    def __init__(self, tasks, cache):
        super().__init__()
        self.tasks = tasks
        self.cache = cache

        self.signals = IconLoaderSignals()

    def run(self):
        results = []

        for goip_label, port_idx, row_idx, tooltip, icon_path in self.tasks:
            cache_key = (icon_path, row_idx)

            if cache_key in self.cache:
                pixmap = self.cache[cache_key]
            else:
                if not os.path.exists(icon_path):
                    continue

                pixmap = QPixmap(icon_path).scaledToHeight(
                    20 if row_idx == 0 else 18,
                    Qt.SmoothTransformation,
                )
                self.cache[cache_key] = pixmap

            results.append(
                (goip_label, port_idx, row_idx, tooltip, pixmap)
            )

        self.signals.result.emit(results)
