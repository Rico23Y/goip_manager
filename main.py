import edge_driver_updater, sys, json, os, time, atexit, ctypes
from PySide6.QtCore import Signal, Qt, QUrl
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout,
    QListWidget, QStackedWidget, QMessageBox, QStyleFactory
)
from PySide6.QtGui import QIcon, QPalette, QColor
from utils import signals, get_appdata_path, resource_path
from login_tab import create_login_tab, DeviceRow
from port_status_tab import create_port_status_tab
from inbox_sms_tab import create_inbox_sms_tab
from restart_tab import create_restart_tab
from console_tab import create_console_tab, DualOutput

app_version = 1.3

def set_app_user_model_id(app_id="GoIP.Manager"):
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass

def qss_url(*parts) -> str:
    """Return a local file path for QSS url()."""
    return resource_path(*parts).replace("\\", "/")



# Ensure redirection is global and not repeated
if not isinstance(sys.stdout, DualOutput):
    sys.stdout = DualOutput(sys.__stdout__)
    sys.stderr = DualOutput(sys.__stderr__)

# Register exit logging
def on_exit():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Application exited.")

def apply_global_light_theme(app: QApplication) -> None:
    """
    Pin the entire app to a light theme regardless of OS theme.
    - Force Fusion style (prevents platform-specific dark palettes)
    - Apply a light QPalette for all base roles
    """
    # Consistent cross-platform base style
    try:
        app.setStyle(QStyleFactory.create("Fusion"))
    except Exception:
        app.setStyle("Fusion")

    # Build a light palette
    pal = QPalette()

    # Windows / panels
    pal.setColor(QPalette.Window, QColor("#f8f9fa"))
    pal.setColor(QPalette.WindowText, Qt.black)

    # Input backgrounds
    pal.setColor(QPalette.Base, QColor("#ffffff"))
    pal.setColor(QPalette.AlternateBase, QColor("#f0f0f0"))
    pal.setColor(QPalette.Text, Qt.black)

    # Buttons
    pal.setColor(QPalette.Button, QColor("#ffffff"))
    pal.setColor(QPalette.ButtonText, Qt.black)

    # Tooltips
    pal.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
    pal.setColor(QPalette.ToolTipText, Qt.black)

    # Links / highlights
    pal.setColor(QPalette.Link, QColor("#357abd"))
    pal.setColor(QPalette.Highlight, QColor("#4a90e2"))
    pal.setColor(QPalette.HighlightedText, Qt.white)

    # Disabled state legibility
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor("#9e9e9e"))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#9e9e9e"))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#9e9e9e"))

    app.setPalette(pal)

    # Optional: a tiny global rule to remove focus borders if any platform injects them
    # (kept separate from your main stylesheet)
    app.setStyleSheet(app.styleSheet() + " *:focus { outline: none; } ")


class MainApp(QMainWindow):
    devices_changed = Signal()

    def __init__(self):
        super().__init__()
        self.config_file = get_appdata_path("devices.json")
        icon_path = resource_path("icons", "signal.png")
        self.setWindowIcon(QIcon(icon_path))
        self.setWindowTitle(f"GOIP Monitor App {app_version}v")
        self.resize(950, 600)

        central_widget = QWidget()
        main_layout = QHBoxLayout(central_widget)
        self.setCentralWidget(central_widget)

        # Sidebar
        self.sideBar = QListWidget()
        self.sideBar.setFixedWidth(170)

        # If you want the no-outline tweak at the app level, do it safely via QApplication.instance()
        app_instance = QApplication.instance()
        if app_instance is not None:
            app_instance.setStyleSheet(app_instance.styleSheet() + " *:focus { outline: none; } ")

        # Stacked widget
        self.stackedWidget = QStackedWidget()

        # Tabs
        self.login_tab = create_login_tab(self)
        self.login_tab_index = self.stackedWidget.addWidget(self.login_tab)
        self.sideBar.addItem("Login")

        self.port_status_tab = create_port_status_tab()
        self.port_status_tab_index = self.stackedWidget.addWidget(self.port_status_tab)
        self.sideBar.addItem("Port Status")

        self.inbox_sms_tab = create_inbox_sms_tab()
        self.inbox_sms_tab_index = self.stackedWidget.addWidget(self.inbox_sms_tab)
        self.sideBar.addItem("Inbox SMS")

        self.restart_tab = create_restart_tab()
        self.restart_tab_index = self.stackedWidget.addWidget(self.restart_tab)
        self.sideBar.addItem("Restart")

        self.console_tab = create_console_tab()
        self.console_tab_index = self.stackedWidget.addWidget(self.console_tab)
        self.sideBar.addItem("Console Log")

        main_layout.addWidget(self.sideBar)
        main_layout.addWidget(self.stackedWidget)

        # Tab switching
        self.sideBar.currentRowChanged.connect(self.handle_tab_change)
        self.last_tab_index = 0
        self.sideBar.setCurrentRow(0)

        # Signals
        self.devices_changed.connect(self.inbox_sms_tab.show_goip_sms_status)
        self.devices_changed.connect(self.port_status_tab.show_goip_ip_status)
        self.devices_changed.connect(self.handle_devices_changed)
        signals.wrongPassword.connect(self.handle_wrong_password)

        self.load_devices_from_file()

        self.stackedWidget.currentChanged.connect(self.on_tab_changed)

        # Apply your modern light stylesheet to this window and its children
        self.setStyleSheet(self.load_stylesheet())

    def load_stylesheet(self):
        approved = qss_url("icons", "approved.png")
        approved_grey = qss_url("icons", "approved_grey.png")
        down_arrow = qss_url("icons", "down.png")

        qss = """
        QMainWindow {
            background: #f8f9fa;
        }

        QListWidget {
            background: #ffffff;
            border-right: 1px solid #e0e0e0;
            font-size: 14px;
            padding: 8px;
        }
        QListWidget::item {
            padding: 10px;
            border-radius: 6px;
        }
        QListWidget::item:selected {
            background: #4a90e2;
            color: white;
        }
        QListWidget::item:hover {
            background: #e8f0fe;
            color: #357abd;
        }

        QStackedWidget {
            background: #ffffff;
            border: none;
        }

        QPushButton {
            background: #72adf2;
            color: white;
            border: none;
            border-radius: 6px;
            padding: 8px 14px;
            font-size: 13px;
        }
        QPushButton:hover {
            background: #357abd;
        }
        QPushButton:disabled {
            background: #d6d6d6;
            color: #9e9e9e;
        }

        /* Inputs */
        QLineEdit {
            border: 1px solid #b5d9ff;
            border-radius: 6px;
            padding: 6px;
            background: #ffffff;
            font-size: 13px;
        }
        QLineEdit:focus {
            border: 1px solid #4a90e2;
        }

        QTextEdit, QPlainTextEdit {
            border: 1px solid #b5d9ff;
            border-radius: 6px;
            padding: 6px;
            background: #ffffff;
            font-size: 13px;
        }

        /* --- Modern CheckBox --- */
        QCheckBox {
            spacing: 6px;
            font-size: 13px;
            color: #333333;
        }

        QCheckBox::indicator {
            width: 18px;
            height: 18px;
            border-radius: 4px;
            border: 1px solid #bcbcbc;
            background: #ffffff;
        }

        QCheckBox::indicator:hover {
            border: 1px solid #4a90e2;
        }

        QCheckBox::indicator:checked {
            border: 1px solid #4a90e2;
            background: #e8f0fe;
            image: url(__APPROVED__);
        }

        /* --- Modern ComboBox --- */
        QComboBox {
            border: 1px solid #d0d0d0;
            border-radius: 6px;
            padding: 6px 30px 6px 8px;
            font-size: 13px;
        }
        
        QComboBox:focus {
            border: 1px solid #4a90e2;
        }
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 28px;
            border-left: 1px solid #d0d0d0;
            border-top-right-radius: 6px;
            border-bottom-right-radius: 6px;
            background: #f9f9f9;
        }
        QComboBox::down-arrow {
            image: url(__DOWN__);
            width: 12px;
            height: 12px;
            margin-right: 8px;
        }

        /* --- ComboBox dropdown list --- */
        QComboBox QAbstractItemView {
            border: 1px solid #d0d0d0;
            border-radius: 6px;
            background: #ffffff;
            padding: 2px;
        }

        QComboBox QAbstractItemView::item {
            padding: 6px;
            color: #000000;
            background: #ffffff;
        }

        QComboBox QAbstractItemView::item:selected {
            background: #4a90e2;
            color: #ffffff;
        }

        QComboBox QAbstractItemView::item:hover {
            background: #e8f0fe;
            color: #357abd;
        }

        /* Disabled CheckBox text */
        QCheckBox:disabled {
            color: #aaaaaa;
        }

        /* Disabled unchecked indicator */
        QCheckBox::indicator:disabled {
            background: #f0f0f0;
            border: 1px solid #cccccc;
        }

        /* Disabled checked indicator */
        QCheckBox::indicator:checked:disabled {
            background: #e0e0e0;
            border: 1px solid #cccccc;
            image: url(__APPROVED_GREY__);
        }

        /* --- Scroll Areas --- */
        QScrollArea {
            background: #f5faff;
            border: none;
        }
        QScrollArea > QWidget > QWidget {
            background: #f5faff;
        }

        /* --- Modern ScrollBar --- */
        QScrollBar:vertical {
            border: none;
            background: #f1f1f1;
            width: 12px;
            margin: 2px 0 2px 0;
            border-radius: 6px;
        }
        QScrollBar::handle:vertical {
            background: #9ecfff;
            border-radius: 6px;
            min-height: 20px;
        }
        QScrollBar::handle:vertical:hover {
            background: #4a90e2;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0;
            border: none;
            background: none;
        }

        QScrollBar:horizontal {
            border: none;
            background: #f1f1f1;
            height: 12px;
            margin: 0 2px 0 2px;
            border-radius: 6px;
        }
        QScrollBar::handle:horizontal {
            background: #c1c1c1;
            border-radius: 6px;
            min-width: 20px;
        }
        QScrollBar::handle:horizontal:hover {
            background: #4a90e2;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0;
            border: none;
            background: none;
        }
        """

        return (
            qss.replace("__APPROVED__", approved)
            .replace("__APPROVED_GREY__", approved_grey)
            .replace("__DOWN__", down_arrow)
        )

    def closeEvent(self, event):
        super().closeEvent(event)

    def message_running(self, message_about,message_type):
        msg = QMessageBox(self)
        msg.setIconPixmap(QIcon(resource_path("icons", "notification.png")).pixmap(64, 64))
        msg.setWindowTitle("Devices Updated")
        msg.setText(
            f"{message_about}.\n"
            f"The current {message_type} will be stopped."
        )
        msg.setStandardButtons(QMessageBox.Close)
        msg.setDefaultButton(QMessageBox.Close)

        # ✅ Show modal popup
        msg.exec()

    def handle_devices_changed(self):
        port_status = self.port_status_tab.monitor_running
        scheduled_restart = self.restart_tab.scheduler_running
        message_about = "The device list has been updated"

        if port_status and scheduled_restart:
            self.port_status_tab.stop_monitoring()
            self.restart_tab.cancel_scheduler()
            self.message_running(message_about, "port inspection and scheduled restart")

        elif port_status:
            self.port_status_tab.stop_monitoring()
            self.message_running(message_about, "port inspection")

        elif scheduled_restart:
            self.restart_tab.cancel_scheduler()
            self.message_running(message_about, "scheduled restart")

    def handle_wrong_password(self):
        port_status = self.port_status_tab.monitor_running
        scheduled_restart = self.restart_tab.scheduler_running
        message_about = "Wrong login username or password, excessive retry will locked down the device"

        if port_status and scheduled_restart:
            self.port_status_tab.stop_monitoring()
            self.restart_tab.cancel_scheduler()
            self.message_running(message_about, "port inspection and scheduled restart")

        elif port_status:
            self.port_status_tab.stop_monitoring()
            self.message_running(message_about, "port inspection")

        elif scheduled_restart:
            self.restart_tab.cancel_scheduler()
            self.message_running(message_about, "scheduled restart")

    def on_tab_changed(self, index):
        """Start/stop updates depending on visible tab."""
        if index == self.inbox_sms_tab_index:
            self.inbox_sms_tab.start_updates()
        else:
            self.inbox_sms_tab.stop_updates()

        if index == self.console_tab_index:
            self.console_tab.start_updates()
        else:
            self.console_tab.stop_updates()

    def handle_tab_change(self, new_index):
        login_tab_index = self.login_tab_index
        port_status_index = self.port_status_tab_index
        console_tab_index = self.console_tab_index

        if self.last_tab_index == login_tab_index and new_index != login_tab_index:
            if self.devices_layout.has_unsaved_changes():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Do you want to save them?",
                    QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                    QMessageBox.Save
                )

                if reply == QMessageBox.Save:
                    self.save_devices_to_file()
                elif reply == QMessageBox.Cancel:
                    self.sideBar.setCurrentRow(self.last_tab_index)
                    return

        if self.last_tab_index == port_status_index:
            self.port_status_tab.pause_updates()
        if new_index == port_status_index:
            self.port_status_tab.resume_updates()

        if self.last_tab_index != console_tab_index and new_index == console_tab_index:
            self.console_tab.start_updates()
        elif self.last_tab_index == console_tab_index and new_index != console_tab_index:
            self.console_tab.stop_updates()

        self.stackedWidget.setCurrentIndex(new_index)
        self.last_tab_index = new_index

    def add_device_row(self, ip="", username="", password=""):
        row = DeviceRow(self.devices_layout, self)
        row.ip_input.setText(str(ip) if ip else "")
        row.username_input.setText(str(username) if username else "")
        row.password_input.setText(str(password) if password else "")
        self.devices_layout.addWidget(row)
        self.devices_layout.update_goip_labels()
        self.devices_layout.update_delete_buttons()

    def get_device_rows(self):
        return [
            self.devices_layout.itemAt(i).widget()
            for i in range(self.devices_layout.count())
            if isinstance(self.devices_layout.itemAt(i).widget(), DeviceRow)
        ]

    def save_devices_to_file(self):
        data = []
        for index, row in enumerate(self.get_device_rows(), start=1):
            row_data = row.to_dict()
            row_data["goip"] = f"GOIP {index}"
            data.append(row_data)

        with open(self.config_file, "w") as f:
            json.dump(data, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
            self.devices_changed.emit()
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Saved File")

    def load_devices_from_file(self):
        global devices
        if os.path.exists(self.config_file):
            with open(self.config_file, "r") as f:
                try:
                    devices = json.load(f)
                    if devices:
                        for dev in devices:
                            self.add_device_row(
                                ip=dev.get("ip", ""),
                                username=dev.get("username", ""),
                                password=dev.get("password", "")
                            )
                        return
                except json.JSONDecodeError:
                    print("Invalid JSON")

        self.add_device_row()


if __name__ == "__main__":
    set_app_user_model_id("GoIP.Manager")
    # Guard console redirection
    if not isinstance(sys.stdout, DualOutput):
        sys.stdout = DualOutput(sys.__stdout__)
        sys.stderr = DualOutput(sys.__stderr__)

    # Optional: block app launch if Edge driver update fails
    if not edge_driver_updater.check_and_update_driver():
        sys.exit(0)

    atexit.register(on_exit)

    # ✅ Create QApplication only if not already running
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    # 🔒 Force light mode regardless of OS theme
    apply_global_light_theme(app)

    window = MainApp()
    window.show()
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Opened Successfully")
    sys.exit(app.exec())

