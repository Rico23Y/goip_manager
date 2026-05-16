import os
from PySide6.QtCore import Qt, QTimer, QSize, QRunnable, QThreadPool, Signal, QObject
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QPushButton,
    QHBoxLayout, QFrame
)
from PySide6.QtGui import QIcon
from inboxSMS import launch_inboxSMS_tabs
from utils import is_port_open, reload_devices, resource_path

_BTN_SIZE = QSize(28, 28)
_ICON_SIZE = QSize(18, 18)

# --- Worker signals ---
class WorkerSignals(QObject):
    result = Signal(str, str, bool)  # goip_label, ip, online

# --- Worker task ---
class PortCheckTask(QRunnable):
    def __init__(self, goip_label, ip):
        super().__init__()
        self.goip_label = goip_label
        self.ip = ip
        self.signals = WorkerSignals()

    def run(self):
        online = is_port_open(self.ip)
        self.signals.result.emit(self.goip_label, self.ip, online)

class InboxSMSTab(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("InboxSMSTab")
        self.goip_frame_cache = {}    # goip_label -> (ip_lbl, status_lbl)
        self.last_status_cache = {}   # goip_label -> (ip, online)
        self.threadpool = QThreadPool()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_status)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # Scrollable area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(scroll_widget)
        self.scroll_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(scroll_widget)
        main_layout.addWidget(self.scroll_area)

        # Bottom right "Open All in Browser" button
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        open_all_btn = QPushButton(" Open all inboxes in browser")
        open_all_btn.setIcon(QIcon(resource_path("icons", "browser.png")))
        open_all_btn.setIconSize(_ICON_SIZE)
        open_all_btn.setToolTip("Open all inboxes in browser")
        open_all_btn.clicked.connect(lambda: launch_inboxSMS_tabs(0))
        bottom_layout.addWidget(open_all_btn)
        main_layout.addLayout(bottom_layout)

        # Initial device list
        self.show_goip_sms_status()

    def start_updates(self):
        self.timer.start(2000)

    def stop_updates(self):
        self.timer.stop()

    def show_goip_sms_status(self):
        # Clear layout
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        devices = reload_devices()

        self.goip_frame_cache.clear()
        self.last_status_cache.clear()

        for idx, dev in enumerate(devices, start=1):
            goip_label = dev.get("goip", f"GOIP {idx}")
            ip = dev.get("ip", "")

            # Placeholder labels
            frame = QFrame()
            frame.setFrameShape(QFrame.NoFrame)
            frame.setStyleSheet(
                "QFrame { background-color: white; }"
                if idx % 2
                else "QFrame { background-color: #ebf3fc; }"
            )
            layout = QHBoxLayout(frame)

            goip_lbl = QLabel(goip_label)
            ip_lbl = QLabel(f"IP: {ip}")
            status_lbl = QLabel("Checking...")
            status_lbl.setStyleSheet("color: gray; font-weight: bold")

            # Browser button
            browser_btn = QPushButton(f"Open {goip_label} inbox in browser")
            browser_btn.setMinimumWidth(250)
            browser_btn.setIcon(QIcon(resource_path("icons", "browser.png")))
            browser_btn.setIconSize(_ICON_SIZE)
            browser_btn.setToolTip(f"Open {goip_label} inbox in browser")
            try:
                goip_number = int(goip_label.split()[-1])
            except ValueError:
                goip_number = idx
            browser_btn.clicked.connect(lambda _, n=goip_number: launch_inboxSMS_tabs(n))

            layout.addWidget(goip_lbl)
            layout.addWidget(ip_lbl)
            layout.addWidget(status_lbl)
            layout.addStretch()
            layout.addWidget(browser_btn)
            self.scroll_layout.addWidget(frame)

            # Cache for updates
            self.goip_frame_cache[goip_label] = (ip_lbl, status_lbl)
            self.last_status_cache[goip_label] = (ip, None)  # unknown yet

            # Threaded port check
            task = PortCheckTask(goip_label, ip)
            task.signals.result.connect(self.update_ui_status)
            self.threadpool.start(task)

    def update_status(self):
        devices = reload_devices()

        for idx, dev in enumerate(devices, start=1):
            goip_label = dev.get("goip", f"GOIP {idx}")
            ip = dev.get("ip", "")
            task = PortCheckTask(goip_label, ip)
            task.signals.result.connect(self.update_ui_status)
            self.threadpool.start(task)

    def update_ui_status(self, goip_label, ip, online):
        if goip_label in self.goip_frame_cache:
            ip_lbl, status_lbl = self.goip_frame_cache[goip_label]
            ip_lbl.setText(f"IP: {ip}" if ip != "" else "Empty IP address")
            status_lbl.setText("Online" if online else "Offline")
            status_lbl.setStyleSheet(
                "color: green; font-weight: bold" if online else "color: red; font-weight: bold"
            )
            self.last_status_cache[goip_label] = (ip, online)


def create_inbox_sms_tab():
    return InboxSMSTab()
