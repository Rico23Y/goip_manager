import time
import pytz
from datetime import datetime, timedelta
from PySide6.QtCore import Qt, QTimer, QDateTime, QTime
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox,
    QPushButton, QScrollArea, QGroupBox, QFrame, QTimeEdit, QMessageBox,
    QDateTimeEdit, QGridLayout, QSpinBox, QSizePolicy
)

# Your restart implementation (must exist)
from app.services.restart_scheduler import (
    next_occurrences_for_block,
    find_next_event,
)
from app.core.config import get_appdata_path
from app.repositories.device_repository import DeviceRepository
from app.repositories.restart_settings_repository import RestartSettingsRepository
from app.ui.widgets.schedule_block import ScheduleBlock
from app.ui.tabs.restart_worker import RestartWorker


RESTART_FILE = get_appdata_path("restart_setting.json")

class RestartTab(QWidget):
    def __init__(
        self,
        device_repository: DeviceRepository,
        settings_file=RESTART_FILE,
        parent=None
    ):
        super().__init__(parent)

        self.device_repository = device_repository
        self.settings_file = settings_file
        self.settings_repository = RestartSettingsRepository(self.settings_file)

        self.devices = self.device_repository.load_devices()

        self.scheduler_running = False
        self.scheduler_timer = QTimer(self)
        self.scheduler_timer.timeout.connect(self._scheduler_tick)

        self.active_workers = []

        # Custom date control flags
        self.custom_applied = False   # whether Apply was clicked
        self.custom_running = False   # whether custom time is currently ticking
        self.custom_now = None        # timezone-aware datetime when custom applied

        self._build_ui()

        # UI timer runs every second and updates clocks / next-reset live
        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self._update_time_display)
        self.ui_timer.start(1000)
        self._update_time_display()

        # load settings if present
        self._load_settings()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)

        # --- ADD: Schedule Running banner ---
        self.banner_label = QLabel("Schedule Running")
        self.banner_label.setStyleSheet("""
            background-color: #75f567;
            color: black;
            font-weight: bold;
            padding: 5px;
            border: 1px solid black;
        """)
        self.banner_label.setAlignment(Qt.AlignCenter)
        self.banner_label.setVisible(False)  # hidden by default
        main_layout.addWidget(self.banner_label)

        # timezone + custom date row
        tz_frame = QFrame()
        tz_layout = QHBoxLayout(tz_frame)
        self.top_date_label = QLabel()
        self.custom_checkbox = QCheckBox("Set custom date")
        self.custom_dt_edit = QDateTimeEdit()
        self.custom_dt_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.custom_dt_edit.setDateTime(QDateTime.currentDateTime())
        self.custom_dt_edit.setEnabled(False)

        # edit/apply buttons for custom
        self.custom_edit_btn = QPushButton("Edit")
        self.custom_apply_btn = QPushButton("Apply")
        self.custom_edit_btn.setEnabled(False)
        self.custom_apply_btn.setEnabled(False)
        self.custom_edit_btn.clicked.connect(self._on_custom_edit)
        self.custom_apply_btn.clicked.connect(self._on_custom_apply)

        self.tz_dropdown = QComboBox()
        self.tz_dropdown.addItems(pytz.all_timezones)
        # try to detect system tz
        try:
            sys_tzinfo = datetime.now().astimezone().tzinfo
            tzname = getattr(sys_tzinfo, "zone", None) or sys_tzinfo.tzname(datetime.now())
            if tzname and tzname in pytz.all_timezones:
                idx = self.tz_dropdown.findText(tzname)
                if idx != -1:
                    self.tz_dropdown.setCurrentIndex(idx)
        except Exception:
            pass

        self.auto_btn = QPushButton("Auto")
        self.sync_btn = QPushButton("Sync")
        self.auto_btn.clicked.connect(self._set_auto_timezone)
        self.sync_btn.clicked.connect(self._sync_time_display)

        tz_layout.addWidget(self.top_date_label)
        tz_layout.addWidget(self.custom_checkbox)
        tz_layout.addWidget(self.custom_dt_edit)
        tz_layout.addWidget(self.custom_edit_btn)
        tz_layout.addWidget(self.custom_apply_btn)
        tz_layout.addWidget(QLabel("Timezone:"))
        tz_layout.addWidget(self.tz_dropdown)
        tz_layout.addWidget(self.auto_btn)
        tz_layout.addWidget(self.sync_btn)

        self.custom_checkbox.stateChanged.connect(self._on_custom_checkbox)
        main_layout.addWidget(tz_frame)

        # Scroll area for devices & blocks
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        self.content = QWidget()  # ✅ store so we can style later
        self.scroll_layout = QVBoxLayout(self.content)
        self.scroll_layout.setAlignment(Qt.AlignTop)  # 🔹 Force top alignment

        # Main devices group
        self.main_devices_group = self._create_main_devices_group()
        self.scroll_layout.addWidget(self.main_devices_group)

        # Blocks container
        self.blocks_container = QVBoxLayout()
        self.scroll_layout.addLayout(self.blocks_container)

        self.add_block_btn = QPushButton("Add Schedule Block")
        self.add_block_btn.clicked.connect(self._add_block)
        self.scroll_layout.addWidget(self.add_block_btn)

        scroll.setWidget(self.content)  # ✅ use stored QWidget
        main_layout.addWidget(scroll)

        # status + controls
        status_frame = QFrame()
        status_layout = QHBoxLayout(status_frame)
        self.next_reset_label = QLabel("Next reset: N/A")
        self.current_label = QLabel("Current: N/A")
        self.time_left_label = QLabel("Time Left: N/A")

        self.start_btn = QPushButton("Start Scheduled Restart")
        self.start_btn.setStyleSheet("background-color: green; color: white; font-weight: bold;")
        self.start_btn.clicked.connect(self._start_or_cancel_scheduler)

        self.auto_start_checkbox = QCheckBox("Start Scheduled upon opening the app")

        status_layout.addWidget(self.next_reset_label)
        status_layout.addWidget(self.current_label)
        status_layout.addWidget(self.time_left_label)
        status_layout.addStretch()
        status_layout.addWidget(self.auto_start_checkbox)
        status_layout.addWidget(self.start_btn)
        main_layout.addWidget(status_frame)

        # Save button
        save_row = QHBoxLayout()
        self.save_btn = QPushButton("Save Settings")
        self.save_btn.clicked.connect(self.save_settings)
        save_row.addStretch()
        save_row.addWidget(self.save_btn)
        main_layout.addLayout(save_row)

    def auto_start(self):
        if not self.scheduler_running:
            self.start_scheduler()

    def _start_or_cancel_scheduler(self):
        if not self.scheduler_running:
            self.start_scheduler()
        else:
            self.cancel_scheduler()


    def start_scheduler(self):

        any_hours = False
        for i in range(self.blocks_container.count()):
            item = self.blocks_container.itemAt(i)
            blk = item.widget() if item else None
            if blk and blk.hours:
                any_hours = True
                break
        if not any_hours:
            QMessageBox.warning(self, "No schedules", "Add at least one schedule (hour) before starting.")
            return
        self.banner_label.setVisible(True)
        self.start_btn.setText("Cancel Scheduled Restart")
        self.start_btn.setStyleSheet("background-color: red; color: white; font-weight: bold;")

        self.scheduler_running = True

        # Disable most UI (except main devices group)
        self._set_controls_enabled(False)
        self.next_reset_label.setStyleSheet("background-color: #d6f5d6; padding: 4px; border-radius: 4px;")
        self.scheduler_timer.start(1000)
        # immediately perform a tick so next reset shows up now
        self._scheduler_tick()
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Start Scheduled Restart")


    def cancel_scheduler(self):
        self.banner_label.setVisible(False)
        if not self.scheduler_running:
            return
        self.scheduler_running = False
        self.scheduler_timer.stop()

        self.start_btn.setText("Start Scheduled Restart")
        self.start_btn.setStyleSheet("background-color: green; color: white; font-weight: bold;")

        # Re-enable UI
        self._set_controls_enabled(True)
        self.next_reset_label.setText("Next reset: N/A")
        self.time_left_label.setText("Time Left: N/A")
        self.next_reset_label.setStyleSheet("")
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Cancel Scheduled Restart")


    def _on_custom_checkbox(self, state):
        checked = bool(state)
        # When checked: enable edit/apply controls. Disable timezone controls per spec.
        self.custom_dt_edit.setEnabled(True)
        self.custom_edit_btn.setEnabled(True)
        self.custom_apply_btn.setEnabled(True)
        if checked:
            self.tz_dropdown.setEnabled(False)
            self.auto_btn.setEnabled(False)
            self.sync_btn.setEnabled(False)
            # initially in "edit" mode (not applied)
            self.custom_applied = False
            self.custom_running = False
            self.custom_now = None
            self.custom_dt_edit.setReadOnly(False)
        else:
            # turning off custom: revert to normal timezone-driven mode
            self.custom_dt_edit.setEnabled(False)
            self.custom_edit_btn.setEnabled(False)
            self.custom_apply_btn.setEnabled(False)
            self.custom_applied = False
            self.custom_running = False
            self.custom_now = None
            self.tz_dropdown.setEnabled(True)
            self.auto_btn.setEnabled(True)
            self.sync_btn.setEnabled(True)
        self._update_time_display()

    def _on_custom_edit(self):
        # Allows editing the custom datetime; pause any running custom clock
        if not self.custom_checkbox.isChecked():
            return
        self.custom_applied = False
        self.custom_running = False
        self.custom_dt_edit.setReadOnly(False)
        self.custom_apply_btn.setEnabled(True)
        self.custom_edit_btn.setEnabled(False)

    def _on_custom_apply(self):
        # Apply the custom datetime: localize to current tz (tz dropdown value at time of checking)
        if not self.custom_checkbox.isChecked():
            return
        qdt = self.custom_dt_edit.dateTime()
        try:
            py_dt = qdt.toPython()
        except Exception:
            py_dt = qdt.toPyDateTime()
        # use selected timezone (even when tz dropdown disabled it's kept at last value)
        try:
            tz = pytz.timezone(self.tz_dropdown.currentText())
        except Exception:
            tz = pytz.UTC
        try:
            if py_dt.tzinfo is None:
                aware = tz.localize(py_dt)
            else:
                aware = py_dt.astimezone(tz)
        except Exception:
            aware = py_dt.replace(tzinfo=tz)
        self.custom_now = aware
        self.custom_applied = True
        self.custom_running = True
        self.custom_dt_edit.setReadOnly(True)
        self.custom_apply_btn.setEnabled(False)
        self.custom_edit_btn.setEnabled(True)
        # update display immediately
        self._update_time_display()

    def _set_auto_timezone(self):
        # Try to detect system timezone name and set dropdown accordingly. Fall back to matching offset.
        try:
            tzinfo = datetime.now().astimezone().tzinfo
            tzname = getattr(tzinfo, "zone", None) or tzinfo.tzname(datetime.now())
            if tzname and tzname in pytz.all_timezones:
                idx = self.tz_dropdown.findText(tzname)
                if idx != -1:
                    self.tz_dropdown.setCurrentIndex(idx)
                    return
            # fallback match by offset
            offset = datetime.now(tzinfo).utcoffset()
            if offset is not None:
                for tz in pytz.all_timezones:
                    try:
                        if datetime.now(pytz.timezone(tz)).utcoffset() == offset:
                            idx = self.tz_dropdown.findText(tz)
                            if idx != -1:
                                self.tz_dropdown.setCurrentIndex(idx)
                                return
                    except Exception:
                        continue
        except Exception:
            pass
        QMessageBox.information(self, "Auto Timezone", "Could not determine system timezone automatically.")

    def _sync_time_display(self):
        # Force an immediate refresh of the time display
        self._update_time_display()

    # ---------- main devices group ----------
    def _create_main_devices_group(self):
        group = QGroupBox("Devices to Restart (Main)")
        group.setMaximumHeight(150)
        layout = QVBoxLayout(group)

        btn_row = QHBoxLayout()
        sel_all = QPushButton("Select All")
        desel_all = QPushButton("Deselect All")
        rev = QPushButton("Reverse Selection")
        sel_all.clicked.connect(lambda: [cb.setChecked(True) for cb in getattr(self, "main_device_checkboxes", [])])
        desel_all.clicked.connect(lambda: [cb.setChecked(False) for cb in getattr(self, "main_device_checkboxes", [])])
        rev.clicked.connect(lambda: [cb.setChecked(not cb.isChecked()) for cb in getattr(self, "main_device_checkboxes", [])])
        btn_row.addWidget(sel_all); btn_row.addWidget(desel_all); btn_row.addWidget(rev)
        layout.addLayout(btn_row)

        devs_scroll = QScrollArea()
        devs_scroll.setWidgetResizable(True)
        dev_container = QWidget()
        dev_layout = QHBoxLayout(dev_container)
        dev_layout.setContentsMargins(0, 0, 0, 0)
        self.main_device_checkboxes = []
        for d in self.devices:
            cb = QCheckBox(d.goip)
            self.main_device_checkboxes.append(cb)
            dev_layout.addWidget(cb)
        devs_scroll.setWidget(dev_container)
        devs_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        layout.addWidget(devs_scroll)

        bottom = QHBoxLayout()
        refresh_btn = QPushButton("Refresh Available Devices")

        restart_now_btn = QPushButton("Restart Immediately")
        refresh_btn.clicked.connect(self._refresh_devices)

        restart_now_btn.clicked.connect(self._restart_immediately)
        bottom.addWidget(refresh_btn); bottom.addWidget(restart_now_btn)
        layout.addLayout(bottom)
        return group

    def _refresh_devices(self):
        self.devices = self.device_repository.load_devices()

        # Refresh the main device checkboxes.
        if hasattr(self, "main_device_checkboxes"):
            selected_indices = {
                index
                for index, checkbox in enumerate(
                    self.main_device_checkboxes,
                    start=1
                )
                if checkbox.isChecked()
            }

            for checkbox in self.main_device_checkboxes:
                checkbox.setParent(None)
                checkbox.deleteLater()

            self.main_device_checkboxes.clear()

            scroll_area = self.main_devices_group.findChild(QScrollArea)

            if scroll_area is not None and scroll_area.widget() is not None:
                dev_container = scroll_area.widget()
                dev_layout = dev_container.layout()

                if dev_layout is not None:
                    for index, device in enumerate(self.devices, start=1):
                        checkbox = QCheckBox(f"GOIP {index}")
                        checkbox.setChecked(index in selected_indices)
                        self.main_device_checkboxes.append(checkbox)
                        dev_layout.addWidget(checkbox)

        # Refresh each schedule block through its own method.
        for index in range(self.blocks_container.count()):
            item = self.blocks_container.itemAt(index)
            block = item.widget()

            if isinstance(block, ScheduleBlock):
                block.refresh_devices(self.devices)

        QMessageBox.information(
            self,
            "Devices Refreshed",
            "Devices have been refreshed in all blocks."
        )

    def _add_block(self):
        blk = ScheduleBlock(self.devices, self)
        self.blocks_container.addWidget(blk)

    # ---------- helper to enable/disable controls while scheduler runs ----------
    def _set_controls_enabled(self, enabled: bool):
        """
        Enable/disable most of the UI while keeping the Main Devices group usable.
        This intentionally does NOT toggle the main_devices_group or the scheduler Start/Cancel buttons,
        so the user can still start/stop and restart devices immediately while scheduled run is active.
        """
        # timezone / custom controls
        for w in [self.tz_dropdown, self.auto_btn, self.sync_btn,
                  self.custom_checkbox, self.custom_dt_edit, self.custom_edit_btn, self.custom_apply_btn,
                  self.top_date_label]:
            try:
                w.setEnabled(enabled)
            except Exception:
                pass

        # add-block and save
        try:
            self.add_block_btn.setEnabled(enabled)
        except Exception:
            pass
        try:
            self.save_btn.setEnabled(enabled)
        except Exception:
            pass

        # disable/enable all schedule blocks (but don't touch main_devices_group)
        try:
            for i in range(self.blocks_container.count()):
                item = self.blocks_container.itemAt(i)
                widget = item.widget() if item else None
                if widget:
                    widget.setEnabled(enabled)
        except Exception:
            pass

    # ---------- worker cleanup ----------
    def _create_finished_slot(self, worker):
        def on_finished():
            try:
                self.active_workers.remove(worker)
            except Exception:
                pass

        return on_finished

    # ---------- immediate restart ----------
    def _restart_immediately(self):
        device_indices = [i + 1 for i, cb in enumerate(self.main_device_checkboxes) if cb.isChecked()]
        if not device_indices:
            QMessageBox.warning(self, "No device", "Please select at least one device.")
            return

        reply = QMessageBox.question(self, "Confirm",
                                     f"Are you sure you want to restart GOIPs: {', '.join(map(str, device_indices))}?")
        if reply != QMessageBox.Yes:
            return

        for n in device_indices:
            w = RestartWorker(self.device_repository, n - 1)
            w.finished.connect(self._create_finished_slot(w))
            self.active_workers.append(w)
            w.start()

    # ---------- scheduling ----------
    def _current_reference_datetime(self):
        """
        Returns timezone-aware 'now' according to UI state:
         - If custom_applied and custom_running: use and advance custom_now
         - If custom_applied but not running (rare): return custom_now (static)
         - Else: return datetime.now(tz from tz_dropdown)
        """
        if self.custom_checkbox.isChecked() and self.custom_applied:
            # use stored custom_now
            return self.custom_now
        # else return actual now in selected timezone
        try:
            tz = pytz.timezone(self.tz_dropdown.currentText())
        except Exception:
            tz = pytz.UTC
        return datetime.now(tz)

    def _gather_all_next_entries(self):
        now = self._current_reference_datetime()
        # Do not modify custom_now while gathering scheduled events.
        try:
            tz = pytz.timezone(self.tz_dropdown.currentText())
        except Exception:
            tz = pytz.UTC

        entries = []
        for i in range(self.blocks_container.count()):
            item = self.blocks_container.itemAt(i)
            block = item.widget() if item else None
            if not block:
                continue

            entries.extend(next_occurrences_for_block(block, now, tz))

        return entries

    def _find_next_event(self):
        entries = self._gather_all_next_entries()
        return find_next_event(entries)

    def _scheduler_tick(self):
        if not self.scheduler_running:
            return

        # if custom_running, advance the custom_now by one second
        if self.custom_checkbox.isChecked() and self.custom_applied and self.custom_running and self.custom_now is not None:
            self.custom_now += timedelta(seconds=1)

        now = self._current_reference_datetime().replace(microsecond=0)
        next_dt, block, hour = self._find_next_event()

        if not next_dt:
            self.next_reset_label.setText("Next reset: N/A")
            self.time_left_label.setText("Time Left: N/A")
            return

        next_dt = next_dt.replace(microsecond=0)

        delta = next_dt - now
        if delta.total_seconds() < 0:
            delta = timedelta(seconds=0)
        seconds = delta.total_seconds()


        if hasattr(self, "restart_phase_seconds") and self.restart_phase_seconds > 0:
            # Red "Restarting" phase
            self.banner_label.setText(f"Restarting, resuming in {self.restart_phase_seconds} seconds")
            self.banner_label.setStyleSheet("""
                background-color: red;
                color: white;
                font-weight: bold;
                padding: 5px;
                border: 1px solid black;
            """)
            self.next_reset_label.setStyleSheet("background-color: red; padding: 4px; border-radius: 4px;")
            self.restart_phase_seconds -= 1
            return  # Skip the normal schedule display while in restart phase

        if seconds <= 10:
            # Blink red/green when under 5 seconds
            color = "red" if seconds % 2 == 0 else "yellow"
            self.banner_label.setText(f"Restarting in {int(seconds)} Second{'s' if seconds != 1 else ''}")
            self.banner_label.setStyleSheet(f"""
                background-color: {color};
                color: black;
                font-weight: bold;
                padding: 5px;
                border: 1px solid black;
            """)
            self.next_reset_label.setStyleSheet("background-color: yellow; padding: 4px; border-radius: 4px;")

        elif seconds <= 60:
            # Solid yellow for last 60 seconds
            self.banner_label.setText(f"Restarting in {int(seconds)} Second{'s' if seconds != 1 else ''}")
            self.banner_label.setStyleSheet("""
                background-color: yellow;
                color: black;
                font-weight: bold;
                padding: 5px;
                border: 1px solid black;
            """)
            self.next_reset_label.setStyleSheet("background-color: yellow; padding: 4px; border-radius: 4px;")

        else:
            # Normal green banner
            self.banner_label.setText("Schedule Running")
            self.banner_label.setStyleSheet("""
                background-color: #75f567;
                color: black;
                font-weight: bold;
                padding: 5px;
                border: 1px solid black;
            """)
            self.next_reset_label.setStyleSheet("background-color: #d6f5d6; padding: 4px; border-radius: 4px;")

        # Trigger when due (allow small tolerance of 1 second)
        if seconds <= 1:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Countdown reached Zero, Restart Triggered")
            self.restart_phase_seconds = 66

            device_indices = [i for i, cb in enumerate(block.device_checkboxes) if cb.isChecked()]
            for di in device_indices:
                w = RestartWorker(self.device_repository, di)
                w.finished.connect(self._create_finished_slot(w))
                self.active_workers.append(w)
                w.start()

            # yearly cleanup
            if block.years:
                exec_year = next_dt.year
                if exec_year in block.years:
                    block.years.discard(exec_year)
                    if block.yearly_widget:
                        block._remove_yearly()
                        if block.years:
                            block._create_yearly_widget()
                            for y in sorted(block.years):
                                block._add_year_row_widget(y)

            self._update_time_display()


    # ---------- time / UI updates ----------
    def _update_time_display(self):
        # If custom_applied and running, advance custom_now by one second here as well
        if self.custom_checkbox.isChecked() and self.custom_applied and self.custom_running and self.custom_now is not None:
            # already advanced in scheduler tick when scheduler running; but keep advancing here for UI if scheduler not running
            if not self.scheduler_running:
                self.custom_now += timedelta(seconds=1)

        if self.custom_checkbox.isChecked() and self.custom_applied and self.custom_now is not None:
            ref = self.custom_now
        else:
            try:
                tz = pytz.timezone(self.tz_dropdown.currentText())
            except Exception:
                tz = pytz.UTC
            ref = datetime.now(tz)

        self.top_date_label.setText(ref.strftime("[%B %d, %Y %A %H:%M:%S]"))
        # Always show next reset/time-left live
        next_dt, _, _ = self._find_next_event()
        if next_dt:
            now = self.custom_now if (
                        self.custom_checkbox.isChecked() and self.custom_applied and self.custom_now is not None) else datetime.now(
                pytz.timezone(self.tz_dropdown.currentText()))
            delta = next_dt - now
            if delta.total_seconds() < 0:
                delta = timedelta(seconds=0)

            secs = int(delta.total_seconds())

            # Break into components
            minutes = secs // 60
            hours = minutes // 60
            days = hours // 24
            months = days // 30
            years = months // 12

            s = secs % 60
            m = minutes % 60
            h = hours % 24
            d = days % 30
            mo = months % 12
            y = years

            # Build parts dynamically
            parts = []
            if y > 0:
                parts.append(f"{y}y")
            if mo > 0 or y > 0:
                parts.append(f"{mo}mo")
            if d > 0 or mo > 0 or y > 0:
                parts.append(f"{d}d")
            if h > 0 or d > 0 or mo > 0 or y > 0:
                parts.append(f"{h}h")
            if m > 0 or h > 0 or d > 0 or mo > 0 or y > 0:
                parts.append(f"{m}m")
            parts.append(f"{s}s")  # Always show seconds if nothing else

            self.next_reset_label.setText("Next reset: " + next_dt.strftime("%Y-%m-%d %A %H:%M:%S"))
            self.time_left_label.setText("Time Left: " + " ".join(parts))
            self.current_label.setText("Current: " + now.strftime("%Y-%m-%d %A %H:%M:%S"))
        else:
            if not self.scheduler_running:
                self.next_reset_label.setText("Next reset: N/A")
                self.time_left_label.setText("Time Left: N/A")

    # ---------- persistence ----------
    def save_settings(self):
        blocks = []
        for i in range(self.blocks_container.count()):
            item = self.blocks_container.itemAt(i)
            blk = item.widget() if item else None
            if blk and hasattr(blk, "to_dict"):
                blocks.append(blk.to_dict())

        data = {
            "timezone": self.tz_dropdown.currentText(),
            "custom_date": bool(self.custom_checkbox.isChecked()),
            "custom_datetime": self.custom_dt_edit.dateTime().toString("yyyy-MM-dd HH:mm:ss"),
            "main_devices": [i + 1 for i, cb in enumerate(self.main_device_checkboxes) if cb.isChecked()],
            "blocks": blocks,
            "auto_start": self.auto_start_checkbox.isChecked()  # ✅ new
        }
        try:
            self.settings_repository.save_settings(data)
            QMessageBox.information(self, "Saved", "Restart settings saved.")
        except Exception:
            QMessageBox.warning(self, "Save Failed", "Could not save restart settings.")

    def _load_settings(self):
        data = self.settings_repository.load_settings()
        if not data:
            return

        tz = data.get("timezone")
        if tz and tz in pytz.all_timezones:
            idx = self.tz_dropdown.findText(tz)
            if idx != -1:
                self.tz_dropdown.setCurrentIndex(idx)

        self.custom_checkbox.setChecked(bool(data.get("custom_date", False)))
        try:
            dtstr = data.get("custom_datetime", QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss"))
            self.custom_dt_edit.setDateTime(QDateTime.fromString(dtstr, "yyyy-MM-dd HH:mm:ss"))
        except Exception:
            pass

        for i, cb in enumerate(self.main_device_checkboxes):
            cb.setChecked((i + 1) in data.get("main_devices", []))

        for blk_data in data.get("blocks", []):
            blk = ScheduleBlock(self.devices, self)
            blk.load_from_dict(blk_data)
            self.blocks_container.addWidget(blk)

        # ✅ Load auto_start setting
        self.auto_start_checkbox.setChecked(data.get("auto_start", False))
        if self.auto_start_checkbox.isChecked():
            self.auto_start()


# factory
def create_restart_tab(device_repository: DeviceRepository):
    return RestartTab(device_repository)
