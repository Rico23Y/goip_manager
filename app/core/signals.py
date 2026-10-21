from PySide6.QtCore import QObject, Signal


class GoipSignals(QObject):
    wrongPassword = Signal(object)


signals = GoipSignals()
