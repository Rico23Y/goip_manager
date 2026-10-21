import os
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout
from PySide6.QtGui import QTextCursor
from PySide6.QtCore import QObject, Signal

# Dedicated log file path for console

def get_log_path():
    appdata = os.getenv("APPDATA", os.path.expanduser("~"))
    log_dir = os.path.join(appdata, "GoIP.Manager", "logs")
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, "console.log")

LOG_FILE = get_log_path()

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# Buffer for in-memory logs (preload from file if it exists)
if os.path.exists(LOG_FILE):
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        console_log_buffer = [f.read()]  # load full file into buffer
else:
    console_log_buffer = []

class ConsoleSignalEmitter(QObject):
    log_updated = Signal(str)

# Global signal emitter
console_signal_emitter = ConsoleSignalEmitter()

import threading

class DualOutput:
    def __init__(self, *streams):
        # Store only valid streams (ignore None)
        self.streams = [s for s in streams if s is not None]
        # Lock to make writes thread-safe
        self._lock = threading.Lock()

    def write(self, message):
        with self._lock:
            # Keep logs in memory
            console_log_buffer.append(message)

            # Write to original streams
            for stream in self.streams:
                try:
                    stream.write(message)
                    stream.flush()
                except Exception:
                    pass  # skip broken streams safely

            # Write to file
            try:
                with open(LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(message)
            except Exception:
                pass

            # Notify UI
            try:
                console_signal_emitter.log_updated.emit(message)
            except Exception:
                pass

    def flush(self):
        with self._lock:
            for stream in self.streams:
                try:
                    stream.flush()
                except Exception:
                    pass

    def close(self):
        with self._lock:
            for stream in self.streams:
                try:
                    stream.close()
                except Exception:
                    pass


class ConsoleTab(QWidget):
    def __init__(self):
        super().__init__()
        self.setLayout(QVBoxLayout())
        self._connected = False  # Track if signal is connected

        # Text display
        self.console_output = QTextEdit(readOnly=True)
        self.console_output.setStyleSheet("""
            background-color: white;
            color: black;
            font-family: Consolas, monospace;
            font-size: 13px;
        """)
        self.layout().addWidget(self.console_output)

        # Clear button
        button_layout = QHBoxLayout()
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear_console)
        button_layout.addStretch()
        button_layout.addWidget(self.clear_button)
        self.layout().addLayout(button_layout)

        # Initial load of existing logs
        self.reload_from_buffer()

    def reload_from_buffer(self):
        """Refresh QTextEdit from the buffer."""
        self.console_output.clear()
        self.console_output.insertPlainText("".join(console_log_buffer))
        self.console_output.moveCursor(QTextCursor.End)

    def start_updates(self):
        """Show latest logs and start listening for new ones."""
        self.reload_from_buffer()
        if not self._connected:
            console_signal_emitter.log_updated.connect(self.append_log)
            self._connected = True

    def stop_updates(self):
        """Stop listening for new log events."""
        if self._connected:
            try:
                console_signal_emitter.log_updated.disconnect(self.append_log)
            except TypeError:
                # Not connected — avoid warning
                pass
            self._connected = False

    def append_log(self, text):
        self.console_output.moveCursor(QTextCursor.End)
        self.console_output.insertPlainText(text)
        self.console_output.moveCursor(QTextCursor.End)

    def clear_console(self):
        self.console_output.clear()
        console_log_buffer.clear()
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("")

def create_console_tab():
    return ConsoleTab()
