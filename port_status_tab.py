from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QScrollArea, QGridLayout, QHBoxLayout,
    QFrame, QSizePolicy, QSpacerItem, QCheckBox, QComboBox, QSpinBox,
    QLineEdit, QGroupBox, QDialog, QTextEdit, QMessageBox
)
from PySide6.QtGui import QPixmap, QIcon, QIntValidator, QTextCursor, QPalette, QColor
from PySide6.QtCore import Qt, QTimer, QObject, Signal, QThread, QObject, Signal, Slot, QRunnable, QThreadPool, \
    QMetaObject, Q_ARG, QSize
from portStatus import start_goip_monitoring, get_goip_status_data, launch_view_tabs, update_notification_settings_from_ui
from utils import status_map, is_port_open, signal_to_level, NETWORK_LABEL, get_appdata_path, reload_devices, \
    resource_path
import json
import os

#from test_00 import get_goip_status_fake_data # testing data

NOTIFICATION_FILE = get_appdata_path("notification_setting.json")
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



class MonitorWorker(QObject):
    finished = Signal()
    def __init__(self, run_callback):
        super().__init__()
        self.run_callback = run_callback

    def run(self):
        self.run_callback()
        self.finished.emit()

class IconLoaderSignals(QObject):
    result = Signal(object)  # will carry a Python object (list of results)


class IconLoaderWorker(QRunnable):
    def __init__(self, tasks, cache):
        super().__init__()
        self.tasks = tasks
        self.cache = cache  # reference to PortStatusTab.pixmap_cache
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
                    Qt.SmoothTransformation
                )
                self.cache[cache_key] = pixmap
            results.append((goip_label, port_idx, row_idx, tooltip, pixmap))
        self.signals.result.emit(results)


class PortStatusTab(QWidget):
    def __init__(self):
        super().__init__()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_data)

        self.status_data = {}
        self.pixmap_cache = {}
        self.label_cache = {}
        self.goip_layouts = {}
        self.goip_frame_cache = {}
        self.monitor_running = False


        # Cache for static view comparison
        self.last_static_status = {}  # goip_label -> (ip, online)

        self.setup_ui()

        # New: separate timer for static view
        self.static_timer = QTimer(self)
        self.static_timer.timeout.connect(self.update_static_view)

        # Build initial static view once
        self.show_goip_ip_status()



    @Slot(list)
    def apply_icon_updates(self, results):
        for goip_label, port_idx, row_idx, tooltip, pixmap in results:
            self.update_port_ui(goip_label, port_idx, row_idx, None, tooltip, None)
            key = (goip_label, port_idx, row_idx)
            label = self.label_cache.get(key)
            if label:
                label.setPixmap(pixmap)

    def pause_updates(self):
        """Pause all timers to reduce CPU usage when hidden."""
        if self.static_timer.isActive():
            self.static_timer.stop()
        if self.timer.isActive():
            self.timer.stop()

    def resume_updates(self):
        """Resume timers only if monitoring is not running."""
        if not self.monitor_running:
            if not self.static_timer.isActive():
                self.static_timer.start(2000)  # static view update every 2 sec
        if not self.timer.isActive():
            self.timer.start(1000)  # live monitoring refresh

    def open_notification_settings(self):
        self.notification_window = NotificationSettingsDialog(self)
        self.notification_window.show()

    def update_port_ui(self, goip_label, port_idx, row_idx, value, tooltip=None, icon_path=None):
        key = (goip_label, port_idx, row_idx)
        label = self.label_cache.get(key)

        # If label is missing or removed from layout, recreate it
        if not label or label.parent() is None:
            layout = self.goip_layouts.get(goip_label)
            if not layout:
                return  # layout missing — skip safely

            label = QLabel()
            label.setAlignment(Qt.AlignCenter)
            self.label_cache[key] = label
            layout.addWidget(label, row_idx, port_idx + 1)

        # Row 0: SIM Icon, Row 1: Signal Icon
        if row_idx in (0, 1):
            if not icon_path:
                return

            # Cache and reuse scaled pixmap
            current_cache_key = label.property("pixmap_cache_key")
            new_pixmap = QPixmap(icon_path).scaledToHeight(20 if row_idx == 0 else 18, Qt.SmoothTransformation)
            new_cache_key = new_pixmap.cacheKey()

            if current_cache_key != new_cache_key:
                label.setPixmap(new_pixmap)
                label.setProperty("pixmap_cache_key", new_cache_key)

            if tooltip and tooltip != label.toolTip():
                label.setToolTip(tooltip)

        else:
            # Only update text if value has changed
            last_value = label.property("last_value")
            if last_value != value:
                label.setText(value)
                label.setProperty("last_value", value)

    def setup_ui(self):
        self.setLayout(QVBoxLayout())

        # Scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_area.setWidget(self.scroll_content)
        self.layout().addWidget(self.scroll_area)

        # Button bar
        self.button_bar = QHBoxLayout()
        self.run_button = QPushButton("Run Port Inspection")
        self.run_button.setStyleSheet("background-color: green; color: white; font-weight: bold;")
        self.notification_button = QPushButton("Advance Notification")
        self.open_all_browser_button = QPushButton("Open All Browser")
        self.run_button.setCheckable(True)

        self.notification_button.clicked.connect(self.open_notification_settings)

        for btn, icon in [
            (self.notification_button, "notification.png"),
            (self.open_all_browser_button, "browser.png"),
        ]:
            icon_path = resource_path("icons", icon)
            btn.setIcon(QIcon(icon_path))

        self.button_bar.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.button_bar.addWidget(self.run_button)
        self.button_bar.addWidget(self.notification_button)
        self.button_bar.addWidget(self.open_all_browser_button)

        self.layout().addLayout(self.button_bar)

        # Connections
        self.run_button.clicked.connect(self.toggle_monitoring)
        self.open_all_browser_button.clicked.connect(lambda: launch_view_tabs(0))
        self.show_goip_ip_status()

    def show_goip_ip_status(self):
        # Clear layout
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        devices = reload_devices()

        # Set goip -> ip map for hover tooltip use
        self.goip_ip_map = {dev.get("goip", f"GOIP {i + 1}"): dev.get("ip", "") for i, dev in enumerate(devices)}

        self.goip_frame_cache.clear()
        self.last_static_status.clear()

        # Ensure threadpool exists
        if not hasattr(self, "threadpool"):
            self.threadpool = QThreadPool()

        for idx, dev in enumerate(devices, start=1):
            goip_label = dev.get("goip", f"GOIP {idx}")
            ip = dev.get("ip", "")

            # Placeholder UI
            frame = QFrame()
            frame.setFrameShape(QFrame.NoFrame)
            palette = frame.palette()
            palette.setColor(QPalette.Window, QColor("#ebf3fc" if idx % 2 else "white"))
            frame.setAutoFillBackground(True)
            frame.setPalette(palette)
            layout = QHBoxLayout(frame)

            goip_lbl = QLabel(goip_label)
            ip_lbl = QLabel(f"IP: {ip}")
            status_lbl = QLabel("Checking...")
            status_lbl.setStyleSheet("color: gray; font-weight: bold")

            # Browser button
            browser_btn = QPushButton(f"Open {goip_label} Port Inspection in browser")
            browser_btn.setMinimumWidth(300)
            browser_btn.setIcon(QIcon(resource_path("icons", "browser.png")))
            browser_btn.setIconSize(_ICON_SIZE)
            browser_btn.setToolTip(f"Open {goip_label} inbox in browser")
            try:
                goip_number = int(goip_label.split()[-1])
            except ValueError:
                goip_number = idx
            browser_btn.clicked.connect(lambda _, n=goip_number: launch_view_tabs(n))

            # Attach attributes
            frame.goip_lbl = goip_lbl
            frame.ip_lbl = ip_lbl
            frame.status_lbl = status_lbl

            layout.addWidget(goip_lbl)
            layout.addWidget(ip_lbl)
            layout.addWidget(status_lbl)
            layout.addStretch()
            layout.addWidget(browser_btn)

            self.scroll_layout.addWidget(frame)
            self.goip_frame_cache[goip_label] = frame
            self.last_static_status[goip_label] = (ip, None)  # status unknown yet

            # Start threaded port check
            task = PortCheckTask(goip_label, ip)
            task.signals.result.connect(self.update_port_status)
            self.threadpool.start(task)

    # --- Add this method to PortStatusTab ---
    def update_port_status(self, goip_label, ip, online):
        if goip_label in self.goip_frame_cache:
            frame = self.goip_frame_cache[goip_label]
            frame.ip_lbl.setText(f"IP: {ip}" if ip != "" else "Empty IP address")
            frame.status_lbl.setText("Online" if online else "Offline")
            frame.status_lbl.setStyleSheet(
                "color: green; font-weight: bold" if online else "color: red; font-weight: bold"
            )
            self.last_static_status[goip_label] = (ip, online)

    def render_status_grid(self):
        # Clear previous UI
        for i in reversed(range(self.scroll_layout.count())):
            widget = self.scroll_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        # Header row (port numbers)
        self.scroll_layout.addWidget(self.build_header())

        # GOIP blocks
        for goip_label in sorted(self.status_data.keys(), key=lambda k: int(k.split()[1])):
            ports_data = self.status_data[goip_label].get("status", [])
            block = self.build_goip_block(goip_label, ports_data)
            self.scroll_layout.addWidget(block)

    def toggle_monitoring(self):
        if self.monitor_running:
            self.stop_monitoring()
            return

        # Disable buttons immediately
        self.run_button.setEnabled(False)
        self.run_button.setText("Loading...")
        self.run_button.setStyleSheet("background-color: gray; color: white; font-weight: bold;")
        self.notification_button.setEnabled(False)
        self.open_all_browser_button.setEnabled(False)

        # Start GOIP initialization in a thread
        self.thread = QThread()
        self.worker = MonitorWorker(lambda: start_goip_monitoring(True))
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        # After background init is done, call this
        self.worker.finished.connect(self.monitor_started_and_refresh)
        self.thread.start()
        self.static_timer.stop()

    def monitor_started_and_refresh(self):
        self.monitor_running = True
        self.run_button.setEnabled(True)
        self.run_button.setText("Stop Port Inspection")
        self.run_button.setStyleSheet("background-color: red; color: white; font-weight: bold;")
        self.run_button.setChecked(True)
        self.notification_button.setEnabled(True)
        self.open_all_browser_button.setEnabled(True)

        self.status_data = get_goip_status_data()
        self.render_status_grid()  # 💡 Renders the live GOIP status UI
        self.timer.start(1000)
        self.refresh_data()

    def stop_monitoring(self):
        start_goip_monitoring(False)
        self.timer.stop()  # ❗ Stop refreshing data
        self.monitor_running = False
        # Clear dynamic data/state
        self.label_cache.clear()
        self.goip_layouts.clear()
        self.run_button.setText("Run Port Inspection")
        self.run_button.setStyleSheet("background-color: green; color: white; font-weight: bold;")
        self.run_button.setChecked(False)
        self.show_goip_ip_status()  # ✅ Restore static online/offline view
        # Resume static updates
        self.static_timer.start(2000)

    def update_static_view(self):
        if self.monitor_running:
            return

        devices = reload_devices()

        # Update goip -> ip map
        self.goip_ip_map = {
            dev.get("goip", f"GOIP {i + 1}"): dev.get("ip", "")
            for i, dev in enumerate(devices)
        }

        # Ensure threadpool exists
        if not hasattr(self, "threadpool"):
            self.threadpool = QThreadPool()

        for idx, dev in enumerate(devices, start=1):
            goip_label = dev.get("goip", f"GOIP {idx}")
            ip = dev.get("ip", "")

            prev_status = self.last_static_status.get(goip_label)
            current_status = (ip, None)  # Status unknown yet

            if prev_status == (ip, None):
                continue  # Skip unchanged IP

            self.last_static_status[goip_label] = current_status

            frame = self.goip_frame_cache.get(goip_label)

            if not frame:
                # Build new frame
                frame = QFrame()
                frame.setFrameShape(QFrame.NoFrame)
                frame.setStyleSheet("background-color: #ebf3fc;" if idx % 2 else "background-color: white")
                layout = QHBoxLayout(frame)

                goip_lbl = QLabel(goip_label)
                ip_lbl = QLabel(f"IP: {ip}")
                status_lbl = QLabel("Checking...")
                status_lbl.setStyleSheet("color: gray; font-weight: bold")

                frame.goip_lbl = goip_lbl
                frame.ip_lbl = ip_lbl
                frame.status_lbl = status_lbl

                layout.addWidget(goip_lbl)
                layout.addWidget(ip_lbl)
                layout.addWidget(status_lbl)
                layout.addStretch()

                self.scroll_layout.addWidget(frame)
                self.goip_frame_cache[goip_label] = frame
            else:
                # Existing frame, mark status as checking
                frame.ip_lbl.setText(f"IP: {ip}")
                frame.status_lbl.setText("Checking...")
                frame.status_lbl.setStyleSheet("color: gray; font-weight: bold")

            # Start threaded port check
            task = PortCheckTask(goip_label, ip)
            task.signals.result.connect(self.update_port_status)
            self.threadpool.start(task)

    def refresh_data(self):
        if not self.monitor_running:
            return  # Safety check

        self.status_data = get_goip_status_data()
        icon_tasks = []  # collect icon jobs

        for goip_label in sorted(self.status_data.keys(), key=lambda k: int(k.split()[1])):
            goip_info = self.status_data[goip_label]
            ports = goip_info.get("status", [])
            is_running = goip_info.get("isRunning", True)
            description = goip_info.get("description", "")

            # 🔄 Update GOIP block background color and tooltip
            frame_layout = self.goip_layouts.get(goip_label)
            if frame_layout:
                parent_frame = frame_layout.parentWidget()
                if parent_frame:
                    new_color = "#ffe6e6" if not is_running else (
                        "white" if int(goip_label.split()[1]) % 2 else "#ebf3fc"
                    )
                    if parent_frame.property("bgColor") != new_color:
                        parent_frame.setStyleSheet(f"background-color: {new_color};")
                        parent_frame.setProperty("bgColor", new_color)

                    if parent_frame.toolTip() != description:
                        parent_frame.setToolTip(description)

            # Collect icon & text updates
            for port_idx, row in enumerate(ports):
                sim_status, signal, net, portChannel, statusDuration = row
                duration = f"{statusDuration // 3600:02}:{(statusDuration % 3600) // 60:02}:{statusDuration % 60:02}"
                tooltip = f"Port {port_idx + 1}{portChannel} {status_map.get(sim_status, 'Unknown')} {duration}"

                # 🔔 Use resource_path for icons
                icon_sim = resource_path("icons", f"light_{str(sim_status).zfill(2)}.png")
                icon_tasks.append((goip_label, port_idx, 0, tooltip, icon_sim))

                level = signal_to_level(signal)
                icon_signal = resource_path("icons", f"signal_status_{level}.png")
                icon_tasks.append((goip_label, port_idx, 1, None, icon_signal))

                # Update text fields immediately in UI thread
                self.update_port_ui(goip_label, port_idx, 2, str(signal))
                network_label = NETWORK_LABEL[net] if net < len(NETWORK_LABEL) else "?"
                self.update_port_ui(goip_label, port_idx, 3, network_label)

        # ✅ run icon scaling/loading in a thread
        if icon_tasks:
            worker = IconLoaderWorker(icon_tasks, self.pixmap_cache)
            worker.signals.result.connect(self.apply_icon_updates)
            self.threadpool.start(worker)

    def build_header(self):
        header_frame = QFrame()
        header_frame.setFrameShape(QFrame.NoFrame)
        grid = QGridLayout(header_frame)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)

        grid.addWidget(QLabel("    Ports   "), 0, 0)

        for i in range(32):
            lbl = QLabel(f"{i + 1}")
            lbl.setAlignment(Qt.AlignCenter)
            grid.addWidget(lbl, 0, i + 1)

        # Browser button
        browser_btn = QPushButton()
        browser_btn.setIcon(QIcon(resource_path("icons", "browser.png")))
        browser_btn.setToolTip("Open all in Browser")
        browser_btn.setFixedSize(24, 24)
        browser_btn.setFixedWidth(50)
        browser_btn.clicked.connect(lambda: launch_view_tabs(0))
        browser_btn.setStyleSheet("margin-top: -4px;")  # shift up by 5px visually

        grid.addWidget(browser_btn, 0, 33, alignment=Qt.AlignVCenter | Qt.AlignHCenter)

        header_frame.setMaximumHeight(40)  # allow enough height for the offset
        return header_frame

    def build_goip_block(self, goip_label, ports_data):
        # 🔍 Get isRunning and description info for this GOIP
        goip_info = self.status_data.get(goip_label, {})
        is_running = goip_info.get("isRunning", True)
        description = goip_info.get("description", "")

        # 📦 GOIP container frame
        frame = QFrame()
        frame.setFrameShape(QFrame.NoFrame)
        frame.setStyleSheet(f"background-color: white;")
        frame.setToolTip(description)  # Tooltip on hover
        frame.setMaximumHeight(150)

        # 🧱 Grid layout
        grid = QGridLayout(frame)
        self.goip_layouts[goip_label] = grid

        # 🏷 GOIP Label
        goip_name_label = QLabel(goip_label)
        goip_name_label.setToolTip(f"IP Address: {self.goip_ip_map.get(goip_label, 'Unknown')}")
        grid.addWidget(goip_name_label, 0, 0, 4, 1, alignment=Qt.AlignTop)

        for port_idx in range(32):
            try:
                sim_status, signal, net, portChannel, statusDuration = ports_data[port_idx]
            except IndexError:
                continue

            duration = f"{statusDuration // 3600:02}:{(statusDuration % 3600) // 60:02}:{statusDuration % 60:02}"

            # 🔌 SIM Status (Row 0)
            icon_sim = resource_path("icons", f"light_{str(sim_status).zfill(2)}.png")
            tooltip = f"Port {port_idx + 1}{portChannel}  {status_map.get(sim_status, 'Unknown')} {duration}"
            label = QLabel()
            label.setAlignment(Qt.AlignCenter)
            label.setPixmap(QPixmap(icon_sim).scaledToHeight(20, Qt.SmoothTransformation))
            label.setToolTip(tooltip)
            grid.addWidget(label, 0, port_idx + 1)
            self.label_cache[(goip_label, port_idx, 0)] = label

            # 📶 Signal Bar (Row 1)
            level = signal_to_level(signal)
            icon_signal = resource_path("icons", f"signal_status_{level}.png")
            label = QLabel()
            label.setAlignment(Qt.AlignCenter)
            label.setPixmap(QPixmap(icon_signal).scaledToHeight(18, Qt.SmoothTransformation))
            grid.addWidget(label, 1, port_idx + 1)
            self.label_cache[(goip_label, port_idx, 1)] = label

            # 🔢 Signal Value (Row 2)
            label = QLabel(str(signal))
            label.setAlignment(Qt.AlignCenter)
            grid.addWidget(label, 2, port_idx + 1)
            self.label_cache[(goip_label, port_idx, 2)] = label

            # 🌐 Network Label (Row 3)
            network_label = NETWORK_LABEL[net] if net < len(NETWORK_LABEL) else "?"
            label = QLabel(network_label)
            label.setAlignment(Qt.AlignCenter)
            grid.addWidget(label, 3, port_idx + 1)
            self.label_cache[(goip_label, port_idx, 3)] = label

        # 🌍 Browser Button
        btn = QPushButton()
        btn.setIcon(QIcon(resource_path("icons", "browser.png")))
        ip = self.goip_ip_map.get(goip_label, 'Unknown')
        btn.setToolTip(f"Launch {goip_label} ({ip}) in browser")
        btn.clicked.connect(lambda _, goip_num=int(goip_label.split()[1]): launch_view_tabs(goip_num))
        grid.addWidget(btn, 0, 33, 4, 1, alignment=Qt.AlignCenter)

        return frame


class NotificationSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Advanced Notification Settings")
        self.setWindowIcon(QIcon(resource_path("icons", "notification.png")))
        self.setMinimumSize(700, 500)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setAlignment(Qt.AlignCenter)

        wrapper = QWidget()
        wrapper.setLayout(QHBoxLayout())
        wrapper.layout().setAlignment(Qt.AlignCenter)
        outer_layout.addWidget(wrapper)

        self.container = QWidget()
        self.container.setObjectName("notification_container")
        self.container.setStyleSheet("""
            #notification_container {
                background-color: white;
                border: 1px solid #e3effc;
                border-radius: 8px;
            }
        """)
        self.container.setLayout(QVBoxLayout())
        wrapper.layout().addWidget(self.container)

        self.settings = self.load_settings()

        self.enable_all_checkbox = QCheckBox("Enable all notifications")
        self.enable_all_checkbox.setChecked(self.settings.get("enabled", True))
        self.container.layout().addWidget(self.enable_all_checkbox)

        self.build_sim_status_section()
        self.build_network_section()
        self.build_signal_section()

        save_btn = QPushButton("Save and Close")
        save_btn.clicked.connect(self.save_and_close)
        self.container.layout().addWidget(save_btn, alignment=Qt.AlignRight)

        self.toggle_sections()
        self.center_on_screen()

    def center_on_screen(self):
        screen_geometry = self.screen().availableGeometry()
        size = self.sizeHint()
        x = (screen_geometry.width() - size.width()) // 2
        y = (screen_geometry.height() - size.height()) // 2
        self.move(x, y)

    def load_settings(self):
        if os.path.exists(NOTIFICATION_FILE):
            with open(NOTIFICATION_FILE, "r") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    pass
        return {}

    def build_sim_status_section(self):
        self.sim_group = QGroupBox("SIM Status Notification")
        self.sim_group.setLayout(QVBoxLayout())

        self.sim_enable_checkbox = QCheckBox("Enable SIM Status Notification")
        self.sim_enable_checkbox.toggled.connect(self.update_sim_section_state)
        self.sim_group.layout().addWidget(self.sim_enable_checkbox)

        self.sim_inner = QWidget()
        self.sim_inner.setLayout(QVBoxLayout())
        self.sim_group.layout().addWidget(self.sim_inner)

        btn_layout = QHBoxLayout()
        select_all = QPushButton("Select All")
        deselect_all = QPushButton("Deselect All")
        reverse = QPushButton("Reverse Selection")
        btn_layout.addWidget(select_all)
        btn_layout.addWidget(deselect_all)
        btn_layout.addWidget(reverse)
        self.sim_inner.layout().addLayout(btn_layout)

        self.sim_status_checkboxes = {}
        grid = QGridLayout()
        for idx, (key, label) in enumerate(status_map.items()):
            icon_path = resource_path("icons", f"light_{str(key).zfill(2)}.png")
            cb = QCheckBox(f"{label}")
            cb.setIcon(QIcon(icon_path))
            self.sim_status_checkboxes[key] = cb
            grid.addWidget(cb, idx // 3, idx % 3)
        self.sim_inner.layout().addLayout(grid)
        self.container.layout().addWidget(self.sim_group)

        select_all.clicked.connect(lambda: [cb.setChecked(True) for cb in self.sim_status_checkboxes.values()])
        deselect_all.clicked.connect(lambda: [cb.setChecked(False) for cb in self.sim_status_checkboxes.values()])
        reverse.clicked.connect(lambda: [cb.setChecked(not cb.isChecked()) for cb in self.sim_status_checkboxes.values()])

        sim_config = self.settings.get("sim_status", {})
        self.sim_enable_checkbox.setChecked(sim_config.get("enabled", True))
        for key in sim_config.get("values", []):
            if key in self.sim_status_checkboxes:
                self.sim_status_checkboxes[key].setChecked(True)

        self.update_sim_section_state()

    def build_network_section(self):
        self.network_group = QGroupBox("Network Type Notification")
        self.network_group.setLayout(QVBoxLayout())

        self.network_enable_checkbox = QCheckBox("Enable Network Type Notification")
        self.network_enable_checkbox.toggled.connect(self.update_network_section_state)
        self.network_group.layout().addWidget(self.network_enable_checkbox)

        self.network_inner = QWidget()
        self.network_inner.setLayout(QHBoxLayout())
        self.network_group.layout().addWidget(self.network_inner)

        self.network_checkboxes = {}
        net_labels = ["NA", "Empty", "2G", "3G", "4G", "5G"]
        for label in net_labels:
            cb = QCheckBox(label)
            self.network_checkboxes[label] = cb
            self.network_inner.layout().addWidget(cb)

        self.network_operator = QComboBox()
        self.network_operator.addItems([">", "<"])
        self.network_count = QSpinBox()
        self.network_count.setRange(0, 32)
        self.network_inner.layout().addWidget(QLabel("Operator:"))
        self.network_inner.layout().addWidget(self.network_operator)
        self.network_inner.layout().addWidget(QLabel("Sim Count:"))
        self.network_inner.layout().addWidget(self.network_count)

        self.container.layout().addWidget(self.network_group)

        net_config = self.settings.get("network_type", {})
        self.network_enable_checkbox.setChecked(net_config.get("enabled", True))
        for label in net_config.get("values", []):
            if label in self.network_checkboxes:
                self.network_checkboxes[label].setChecked(True)
        self.network_operator.setCurrentText(net_config.get("operator", ">"))
        self.network_count.setValue(net_config.get("count", 0))

        self.update_network_section_state()

    def build_signal_section(self):
        self.signal_group = QGroupBox("Signal Notification")
        self.signal_group.setLayout(QVBoxLayout())

        self.signal_enable_checkbox = QCheckBox("Enable Signal Type Notification")
        self.signal_enable_checkbox.toggled.connect(self.update_signal_section_state)
        self.signal_group.layout().addWidget(self.signal_enable_checkbox)

        self.signal_inner = QWidget()
        self.signal_inner.setLayout(QVBoxLayout())
        self.signal_group.layout().addWidget(self.signal_inner)

        self.signal_bar_checkboxes = {}
        self.signal_bar_layout = QHBoxLayout()
        for i in range(6):
            cb = QCheckBox()
            cb.setIcon(QIcon(resource_path("icons", f"signal_status_{i}.png")))
            self.signal_bar_checkboxes[i] = cb
            self.signal_bar_layout.addWidget(cb)
            cb.clicked.connect(self.on_bar_clicked)
        self.signal_inner.layout().addLayout(self.signal_bar_layout)

        self.custom_signal_checkbox = QCheckBox("Custom signal strength range:")
        self.custom_signal_checkbox.stateChanged.connect(self.on_custom_checked)

        self.custom_signal_min = QLineEdit()
        self.custom_signal_min.setPlaceholderText("Min")
        self.custom_signal_min.setValidator(QIntValidator(0, 99))
        self.custom_signal_min.editingFinished.connect(self.enforce_custom_signal_range_consistency)

        self.custom_signal_max = QLineEdit()
        self.custom_signal_max.setPlaceholderText("Max")
        self.custom_signal_max.setValidator(QIntValidator(0, 99))
        self.custom_signal_max.editingFinished.connect(self.enforce_custom_signal_range_consistency)

        self.custom_operator = QComboBox()
        self.custom_operator.addItems([">", "<"])

        self.custom_count = QSpinBox()
        self.custom_count.setRange(0, 32)

        custom_layout = QHBoxLayout()
        custom_layout.addWidget(self.custom_signal_checkbox)
        custom_layout.addWidget(self.custom_signal_min)
        custom_layout.addWidget(QLabel("-"))
        custom_layout.addWidget(self.custom_signal_max)
        custom_layout.addWidget(QLabel("Operator:"))
        custom_layout.addWidget(self.custom_operator)
        custom_layout.addWidget(QLabel("Sim Count:"))
        custom_layout.addWidget(self.custom_count)

        self.signal_inner.layout().addLayout(custom_layout)
        self.container.layout().addWidget(self.signal_group)

        sig_config = self.settings.get("signal", {})
        self.signal_enable_checkbox.setChecked(sig_config.get("enabled", True))

        bar_config = sig_config.get("bar", {})
        for i in bar_config.get("values", []):
            if i in self.signal_bar_checkboxes:
                self.signal_bar_checkboxes[i].setChecked(True)

        custom_config = sig_config.get("custom", {})
        self.custom_signal_checkbox.setChecked(custom_config.get("enabled", False))
        self.custom_signal_min.setText(str(custom_config.get("min", "")))
        self.custom_signal_max.setText(str(custom_config.get("max", "")))
        self.custom_operator.setCurrentText(custom_config.get("operator", ">"))
        self.custom_count.setValue(custom_config.get("count", 0))

        self.update_custom_fields_state()
        self.update_signal_section_state()

    def on_bar_clicked(self):
        if any(cb.isChecked() for cb in self.signal_bar_checkboxes.values()):
            self.custom_signal_checkbox.setChecked(False)

    def on_custom_checked(self):
        if self.custom_signal_checkbox.isChecked():
            for cb in self.signal_bar_checkboxes.values():
                cb.setChecked(False)
        self.update_custom_fields_state()

    def update_custom_fields_state(self):
        custom_enabled = self.custom_signal_checkbox.isChecked()
        self.custom_signal_min.setEnabled(custom_enabled)
        self.custom_signal_max.setEnabled(custom_enabled)

    def update_sim_section_state(self):
        self.sim_inner.setEnabled(self.sim_enable_checkbox.isChecked())

    def update_network_section_state(self):
        self.network_inner.setEnabled(self.network_enable_checkbox.isChecked())

    def update_signal_section_state(self):
        self.signal_inner.setEnabled(self.signal_enable_checkbox.isChecked())

    def toggle_sections(self):
        enabled = self.enable_all_checkbox.isChecked()
        self.sim_group.setEnabled(enabled)
        self.network_group.setEnabled(enabled)
        self.signal_group.setEnabled(enabled)
        self.enable_all_checkbox.stateChanged.connect(self.toggle_sections)

    def enforce_custom_signal_range_consistency(self):
        min_text = self.custom_signal_min.text()
        max_text = self.custom_signal_max.text()

        if not min_text.isdigit() or not max_text.isdigit():
            return

        min_val = int(min_text)
        max_val = int(max_text)

        if min_val > max_val:
            self.custom_signal_max.setText(str(min_val))
        elif max_val < min_val:
            self.custom_signal_min.setText(str(max_val))

    def save_and_close(self):
        bar_enabled = not self.custom_signal_checkbox.isChecked()
        custom_enabled = self.custom_signal_checkbox.isChecked()


        new_settings = {
            "enabled": self.enable_all_checkbox.isChecked(),
            "sim_status": {
                "enabled": self.sim_enable_checkbox.isChecked(),
                "values": [k for k, cb in self.sim_status_checkboxes.items() if cb.isChecked()]
            },
            "network_type": {
                "enabled": self.network_enable_checkbox.isChecked(),
                "values": [k for k, cb in self.network_checkboxes.items() if cb.isChecked()],
                "operator": self.network_operator.currentText(),
                "count": self.network_count.value()
            },
            "signal": {
                "enabled": self.signal_enable_checkbox.isChecked(),
                "bar": {
                    "enabled": bar_enabled,
                    "values": [k for k, cb in self.signal_bar_checkboxes.items() if cb.isChecked()]
                },
                "custom": {
                    "enabled": custom_enabled,
                    "min": int(self.custom_signal_min.text() or "0"),
                    "max": int(self.custom_signal_max.text() or "0"),
                    "operator": self.custom_operator.currentText(),
                    "count": self.custom_count.value()
                }
            }
        }

        with open(NOTIFICATION_FILE, "w") as f:
            json.dump(new_settings, f, indent=4)

        update_notification_settings_from_ui()
        self.accept()

def create_port_status_tab():
    return PortStatusTab()
