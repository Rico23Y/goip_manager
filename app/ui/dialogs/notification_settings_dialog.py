from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout,
    QGridLayout, QCheckBox, QComboBox, QSpinBox, QLineEdit,
    QGroupBox, QDialog,
)
from PySide6.QtGui import QIcon, QIntValidator
from PySide6.QtCore import Qt

from app.core.goip_status import status_map
from app.core.config import get_appdata_path
from app.utils.paths import resource_path
from app.repositories.notification_settings_repository import (
    NotificationSettingsRepository,
)
from app.services.port_status_orchestrator import (
    update_notification_settings_from_ui,
)

NOTIFICATION_FILE = get_appdata_path("notification_setting.json")
notification_settings_repository = NotificationSettingsRepository(
    NOTIFICATION_FILE
)


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

        self.enable_all_checkbox.stateChanged.connect(self.toggle_sections)
        self.toggle_sections()
        self.center_on_screen()

    def center_on_screen(self):
        screen_geometry = self.screen().availableGeometry()
        size = self.sizeHint()
        x = (screen_geometry.width() - size.width()) // 2
        y = (screen_geometry.height() - size.height()) // 2
        self.move(x, y)

    def load_settings(self):
        return notification_settings_repository.load_settings()

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

        notification_settings_repository.save_settings(new_settings)

        update_notification_settings_from_ui()
        self.accept()
