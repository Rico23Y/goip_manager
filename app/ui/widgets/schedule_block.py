import calendar
from datetime import datetime

from PySide6.QtCore import Qt, QTime
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from app.utils.paths import resource_path

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# ---------- ScheduleBlock ----------
class ScheduleBlock(QGroupBox):
    def __init__(self, devices, parent_tab):
        super().__init__("Schedule Block")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.devices = devices
        self.parent_tab = parent_tab

        # data model
        self.hours = []  # ["HH:MM", ...]
        self.recurrence_mode = None  # None | "daily" | "weekly"
        self.daily_days = set()
        self.weekly_days = set()
        self.months = set()
        self.years = set()

        # UI refs
        self.device_checkboxes = []
        self.hours_ui_rows = []  # list of tuples (layout, delete_button)
        self.daily_widget = None
        self.weekly_widget = None
        self.monthly_widget = None
        self.yearly_widget = None

        # Buttons we will need to enable/disable later
        self.sel_all_btn = None
        self.desel_all_btn = None
        self.rev_btn = None
        self.add_month_btn = None
        self.switch_weekly_btn = None
        self.switch_daily_btn = None
        self.delete_daily_btn = None
        self.delete_weekly_btn = None
        self.delete_month_btn = None
        self.daily_desel_btn = None
        self.weekly_desel_btn = None

        self._build_ui()
        self._update_ui_state()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)

        # Device controls (select/deselect/reverse)
        ctrl_row = QHBoxLayout()
        self.sel_all_btn = QPushButton("Select All")
        self.desel_all_btn = QPushButton("Deselect All")
        self.rev_btn = QPushButton("Reverse Selection")
        self.sel_all_btn.clicked.connect(self._select_all_devices)
        self.desel_all_btn.clicked.connect(self._deselect_all_devices_with_check)
        self.rev_btn.clicked.connect(self._reverse_devices_with_check)
        ctrl_row.addWidget(self.sel_all_btn); ctrl_row.addWidget(self.desel_all_btn); ctrl_row.addWidget(self.rev_btn)
        layout.addLayout(ctrl_row)

        # Devices row (horizontal scroll)
        dev_scroll = QScrollArea()
        dev_scroll.setWidgetResizable(True)
        dev_scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)  # 🔹 don't expand vertically
        dev_scroll.setMaximumHeight(100)
        dev_container = QWidget()
        dev_layout = QHBoxLayout(dev_container)
        dev_layout.setContentsMargins(0, 0, 0, 0)

        for i, d in enumerate(self.devices):
            cb = QCheckBox(d.goip)
            cb.stateChanged.connect(lambda st, idx=i: self._device_toggled(idx, st))
            self.device_checkboxes.append(cb)
            dev_layout.addWidget(cb)
        dev_scroll.setWidget(dev_container)
        dev_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        layout.addWidget(dev_scroll)

        # Hours label + input + add hour button
        hours_input_row = QHBoxLayout()
        hours_input_row.addWidget(QLabel("Hours:"))

        self.time_input = QTimeEdit()
        self.time_input.setDisplayFormat("HH:mm")
        self.time_input.setTime(QTime.currentTime())
        hours_input_row.addWidget(self.time_input)

        add_hour_btn = QPushButton("Add Hour")
        add_hour_btn.clicked.connect(self._on_add_hour)
        hours_input_row.addWidget(add_hour_btn)
        hours_input_row.addStretch()  # push content to the left
        layout.addLayout(hours_input_row)

        # Hours container (chips row)
        self.hours_container = QHBoxLayout()
        self.hours_container.setAlignment(Qt.AlignLeft)
        layout.addLayout(self.hours_container)

        # Buttons row (daily/weekly/monthly/delete)
        buttons_row = QHBoxLayout()
        self.add_daily_btn = QPushButton("Add Daily")
        self.add_weekly_btn = QPushButton("Add Weekly")
        self.delete_block_btn = QPushButton("Delete Block")
        self.delete_block_btn.setStyleSheet("background-color: #e67373; color: white; font-weight: bold;")
        self.add_daily_btn.clicked.connect(self._on_add_daily)
        self.add_weekly_btn.clicked.connect(self._on_add_weekly)

        self.delete_block_btn.clicked.connect(self._delete_self)

        # Make all buttons expand equally
        for btn in [self.add_daily_btn, self.add_weekly_btn, self.delete_block_btn]:
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        buttons_row.addWidget(self.add_daily_btn)
        buttons_row.addWidget(self.add_weekly_btn)
        buttons_row.addWidget(self.delete_block_btn)

        layout.addLayout(buttons_row)

    def refresh_devices(self, devices: list) -> None:
        """Refresh the device checkboxes while preserving selections by index."""
        selected_indices = {
            index
            for index, checkbox in enumerate(self.device_checkboxes, start=1)
            if checkbox.isChecked()
        }

        self.devices = devices

        # Find the device scroll area and its layout.
        dev_scroll = self.findChild(QScrollArea)
        if dev_scroll is None or dev_scroll.widget() is None:
            return

        dev_container = dev_scroll.widget()
        dev_layout = dev_container.layout()

        if dev_layout is None:
            return

        # Remove the old checkboxes.
        while dev_layout.count():
            item = dev_layout.takeAt(0)
            widget = item.widget()

            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        self.device_checkboxes.clear()

        # Rebuild the checkboxes.
        for index, device in enumerate(self.devices, start=1):
            checkbox = QCheckBox(f"GOIP {index}")
            checkbox.setChecked(index in selected_indices)
            checkbox.stateChanged.connect(
                lambda state, idx=index: self._device_toggled(idx - 1, state)
            )

            self.device_checkboxes.append(checkbox)
            dev_layout.addWidget(checkbox)

        self._update_ui_state()


    # ---------- device helpers ----------
    def _select_all_devices(self):
        for cb in self.device_checkboxes:
            cb.setChecked(True)

    def _deselect_all_devices_with_check(self):
        # Prevent leaving zero selected if monthly/yearly exist OR if hours exist (prevent deselect all)
        if (self.monthly_widget or self.yearly_widget):
            QMessageBox.warning(self.parent_tab, "Cannot Deselect All",
                                "Monthly/Yearly is present. You must keep at least one device selected in this block.")
            return
        if self.hours:
            QMessageBox.warning(self.parent_tab, "Cannot Deselect All",
                                "At least one hour exists in this block. You must keep at least one device selected.")
            return
        for cb in self.device_checkboxes:
            cb.setChecked(False)

    def _reverse_devices_with_check(self):
        new_states = [not cb.isChecked() for cb in self.device_checkboxes]
        if (self.monthly_widget or self.yearly_widget) and not any(new_states):
            QMessageBox.warning(self.parent_tab, "Cannot Reverse",
                                "Reverse selection would leave zero devices while Monthly/Yearly present.")
            return
        if self.hours and not any(new_states):
            QMessageBox.warning(self.parent_tab, "Cannot Reverse",
                                "Reverse selection would leave zero devices while hours exist.")
            return
        for cb in self.device_checkboxes:
            cb.setChecked(not cb.isChecked())

    def _device_toggled(self, idx, state):
        # After toggle enforce that if monthly/yearly exist we don't allow zero devices
        selected_count = sum(1 for cb in self.device_checkboxes if cb.isChecked())
        if (self.monthly_widget or self.yearly_widget) and selected_count == 0:
            QMessageBox.warning(self.parent_tab, "Cannot Deselect",
                                "At least one device must remain selected while Monthly/Yearly is present.")
            # restore
            self.device_checkboxes[idx].setChecked(True)
            return

        # --- ADDED: Prevent unchecking last device if hours exist ---
        if self.hours and selected_count == 0:
            QMessageBox.warning(self.parent_tab, "Cannot Deselect",
                                "At least one device must remain selected when hours are present.")
            self.device_checkboxes[idx].setChecked(True)
            return

        self._update_ui_state()

    def has_selected_device(self):
        return any(cb.isChecked() for cb in self.device_checkboxes)

    # ---------- hours ----------
    def _on_add_hour(self):
        if not self.has_selected_device():
            QMessageBox.warning(self.parent_tab, "No Devices",
                                "Select at least one device in this block before adding hours.")
            return
        hour_str = self.time_input.time().toString("HH:mm")
        if hour_str in self.hours:
            QMessageBox.warning(self.parent_tab, "Duplicate Hour", f"{hour_str} already added in this block.")
            return
        self.hours.append(hour_str)

        # Create the hour "box"
        hour_box = QFrame()
        hour_box.setFrameShape(QFrame.StyledPanel)
        hour_box.setStyleSheet("""
            QWidget {
                        background-color: #f2f2f2;
                        border-radius: 6px;
                }
        """)
        box_layout = QHBoxLayout(hour_box)
        box_layout.setContentsMargins(8, 2, 8, 2)
        box_layout.setSpacing(5)

        lbl = QLabel(hour_str)
        del_btn = QPushButton()
        del_btn.setIcon(QIcon(resource_path("icons", "delete.png")))
        del_btn.setFixedSize(20, 20)
        del_btn.setIconSize(del_btn.size())
        del_btn.setStyleSheet("border: none;")
        del_btn.clicked.connect(lambda _, s=hour_str, w=hour_box: self._remove_hour(s, w))

        box_layout.addWidget(lbl)
        box_layout.addWidget(del_btn)

        self.hours_container.addWidget(hour_box)
        self.hours_ui_rows.append((hour_box, del_btn))
        self._update_ui_state()

    def _remove_hour(self, hour_str, widget):
        if hour_str in self.hours:
            self.hours.remove(hour_str)
        widget.setParent(None)
        widget.deleteLater()
        self.hours_ui_rows = [p for p in self.hours_ui_rows if p[0] != widget]
        self._update_ui_state()

    # ---------- block ops ----------
    def _delete_self(self):
        self.setParent(None)
        self.deleteLater()

    # ---------- daily ----------
    def _on_add_daily(self):
        if not self.hours:
            QMessageBox.warning(self.parent_tab, "Missing Hours", "Please add at least one hour before adding Daily.")
            return
        if not self.has_selected_device():
            QMessageBox.warning(self.parent_tab, "No Devices", "Please select device(s) before adding Daily.")
            return
        if self.weekly_widget:
            self._remove_weekly()
        if self.daily_widget:
            return
        self.recurrence_mode = "daily"
        self._create_daily_widget()
        self._update_ui_state()

    def _create_daily_widget(self):
        widget = QGroupBox("Daily (1-30). Leave empty for every day.")
        v = QVBoxLayout(widget)
        btn_row = QHBoxLayout()
        sel = QPushButton("Select All")
        desel = QPushButton("Deselect All")
        rev = QPushButton("Reverse")
        btn_row.addWidget(sel); btn_row.addWidget(desel); btn_row.addWidget(rev)
        v.addLayout(btn_row)

        grid = QGridLayout()
        self.daily_checkboxes = {}
        for i in range(1, 31):
            cb = QCheckBox(str(i))
            cb.setChecked(i in self.daily_days)
            cb.stateChanged.connect(lambda st, val=i: self._toggle_daily(val, st))
            r = (i - 1) // 6
            c = (i - 1) % 6
            grid.addWidget(cb, r, c)
            self.daily_checkboxes[i] = cb
        v.addLayout(grid)

        bottom = QHBoxLayout()
        self.add_month_btn = QPushButton("Add Monthly")
        self.switch_weekly_btn = QPushButton("Switch to Weekly")
        self.delete_daily_btn = QPushButton("Delete Daily")
        self.delete_daily_btn.setStyleSheet("background-color: #e67373; color: white; font-weight: bold;")
        self.add_month_btn.clicked.connect(self._on_add_monthly)
        self.switch_weekly_btn.clicked.connect(self._on_add_weekly)
        self.delete_daily_btn.clicked.connect(self._remove_daily)
        bottom.addWidget(self.add_month_btn); bottom.addWidget(self.switch_weekly_btn); bottom.addWidget(self.delete_daily_btn)
        v.addLayout(bottom)

        sel.clicked.connect(lambda: [cb.setChecked(True) for cb in self.daily_checkboxes.values()])
        desel.clicked.connect(self._daily_deselect_all_with_check)
        rev.clicked.connect(lambda: [cb.setChecked(not cb.isChecked()) for cb in self.daily_checkboxes.values()])

        self.daily_desel_btn = desel

        self.daily_widget = widget
        self.layout().addWidget(widget)

    def _daily_deselect_all_with_check(self):
        if self.monthly_widget:
            QMessageBox.warning(self.parent_tab, "Cannot Deselect All", "Monthly exists — keep at least one daily selected.")
            return
        for cb in self.daily_checkboxes.values():
            cb.setChecked(False)

    def _toggle_daily(self, val, state):
        if state:
            self.daily_days.add(val)
        else:
            if self.monthly_widget and len(self.daily_days) <= 1:
                QMessageBox.warning(self.parent_tab, "Cannot Deselect", "Monthly exists — at least one daily must remain selected.")
                self.daily_checkboxes[val].setChecked(True)
                return
            self.daily_days.discard(val)
        self._update_ui_state()

    def _remove_daily(self):
        if self.monthly_widget:
            return
        if not self.daily_widget:
            return
        self.daily_widget.setParent(None)
        self.daily_widget.deleteLater()
        self.daily_widget = None
        self.daily_days.clear()
        self.recurrence_mode = None
        self._update_ui_state()

    # ---------- weekly ----------
    def _on_add_weekly(self):
        if not self.hours:
            QMessageBox.warning(self.parent_tab, "Missing Hours", "Please add at least one hour before adding Weekly.")
            return
        if not self.has_selected_device():
            QMessageBox.warning(self.parent_tab, "No Devices", "Please select device(s) before adding Weekly.")
            return
        if self.daily_widget:
            self._remove_daily()
        if self.weekly_widget:
            return
        self.recurrence_mode = "weekly"
        self._create_weekly_widget()
        self._update_ui_state()

    def _create_weekly_widget(self):
        widget = QGroupBox("Weekly (Mon..Sun). Leave empty for every day.")
        v = QVBoxLayout(widget)
        row = QHBoxLayout()

        btn_row = QHBoxLayout()
        sel = QPushButton("Select All")
        desel = QPushButton("Deselect All")
        rev = QPushButton("Reverse")
        sel.clicked.connect(lambda: [cb.setChecked(True) for cb in self.weekday_checkboxes.values()])
        desel.clicked.connect(self._weekly_deselect_all_with_check)
        rev.clicked.connect(lambda: [cb.setChecked(not cb.isChecked()) for cb in self.weekday_checkboxes.values()])
        btn_row.addWidget(sel); btn_row.addWidget(desel); btn_row.addWidget(rev)
        v.addLayout(btn_row)

        self.weekday_checkboxes = {}
        for i, wd in enumerate(WEEKDAYS):
            cb = QCheckBox(wd)
            cb.setChecked(i in self.weekly_days)
            cb.stateChanged.connect(lambda st, idx=i: self._toggle_weekday(idx, st))
            row.addWidget(cb)
            self.weekday_checkboxes[i] = cb
        v.addLayout(row)

        bottom = QHBoxLayout()
        self.add_month_btn = QPushButton("Add Monthly")
        self.switch_daily_btn = QPushButton("Switch to Daily")
        self.delete_weekly_btn = QPushButton("Delete Weekly")
        self.delete_weekly_btn.setStyleSheet("background-color: #e67373; color: white; font-weight: bold;")
        self.add_month_btn.clicked.connect(self._on_add_monthly)
        self.switch_daily_btn.clicked.connect(self._on_add_daily)
        self.delete_weekly_btn.clicked.connect(self._remove_weekly)
        bottom.addWidget(self.add_month_btn); bottom.addWidget(self.switch_daily_btn); bottom.addWidget(self.delete_weekly_btn)
        v.addLayout(bottom)

        self.weekly_desel_btn = desel

        self.weekly_widget = widget
        self.layout().addWidget(widget)

    def _weekly_deselect_all_with_check(self):
        if self.monthly_widget:
            QMessageBox.warning(self.parent_tab, "Cannot Deselect All", "Monthly exists — keep at least one weekday selected.")
            return
        for cb in self.weekday_checkboxes.values():
            cb.setChecked(False)

    def _toggle_weekday(self, idx, state):
        if state:
            self.weekly_days.add(idx)
        else:
            if self.monthly_widget and len(self.weekly_days) <= 1:
                QMessageBox.warning(self.parent_tab, "Cannot Deselect", "Monthly exists — at least one weekday must remain selected.")
                self.weekday_checkboxes[idx].setChecked(True)
                return
            self.weekly_days.discard(idx)
        self._update_ui_state()

    def _remove_weekly(self):
        if self.monthly_widget:
            return
        if not self.weekly_widget:
            return
        self.weekly_widget.setParent(None)
        self.weekly_widget.deleteLater()
        self.weekly_widget = None
        self.weekly_days.clear()
        self.recurrence_mode = None
        self._update_ui_state()

    # ---------- monthly ----------
    def _on_add_monthly(self):
        # monthly requires daily or weekly to exist and have at least one selection
        if self.daily_widget:
            if not self.daily_days:
                QMessageBox.warning(self.parent_tab, "Daily Empty", "Daily must have at least one day before adding Monthly.")
                return
        elif self.weekly_widget:
            if not self.weekly_days:
                QMessageBox.warning(self.parent_tab, "Weekly Empty", "Weekly must have at least one day before adding Monthly.")
                return
        else:
            QMessageBox.warning(self.parent_tab, "Prerequisite Missing", "Monthly requires Daily or Weekly.")
            return
        if self.monthly_widget:
            return
        self._create_monthly_widget()
        self._update_ui_state()

    def _create_monthly_widget(self):
        widget = QGroupBox("Monthly (choose months)")
        v = QVBoxLayout(widget)
        month_row = QHBoxLayout()
        self.month_checkboxes = {}
        for m in range(1, 13):
            cb = QCheckBox(calendar.month_name[m])
            cb.setChecked(m in self.months)
            cb.stateChanged.connect(lambda st, v=m: self._toggle_month(v, st))
            month_row.addWidget(cb)
            self.month_checkboxes[m] = cb
        v.addLayout(month_row)

        bottom = QHBoxLayout()
        self.add_year_btn = QPushButton("Add Yearly")
        self.delete_month_btn = QPushButton("Delete Monthly")
        self.delete_month_btn.setStyleSheet("background-color: #e67373; color: white; font-weight: bold;")
        self.add_year_btn.clicked.connect(self._on_add_yearly)
        self.delete_month_btn.clicked.connect(self._remove_monthly)
        bottom.addWidget(self.add_year_btn); bottom.addWidget(self.delete_month_btn)
        v.addLayout(bottom)

        self.monthly_widget = widget
        self.layout().addWidget(widget)

    def _toggle_month(self, m, state):
        if state:
            self.months.add(m)
        else:
            if self.yearly_widget and len(self.months) <= 1:
                QMessageBox.warning(self.parent_tab, "Cannot Deselect", "Yearly exists — at least one month must remain selected.")
                self.month_checkboxes[m].setChecked(True)
                return
            self.months.discard(m)
        self._update_ui_state()

    def _remove_monthly(self):
        if self.yearly_widget:
            return
        if not self.monthly_widget:
            return
        self.monthly_widget.setParent(None)
        self.monthly_widget.deleteLater()
        self.monthly_widget = None
        self.months.clear()
        self._update_ui_state()

    # ---------- yearly ----------
    def _on_add_yearly(self):
        if not self.monthly_widget:
            QMessageBox.warning(self.parent_tab, "Prerequisite Missing", "Yearly requires Monthly.")
            return
        if self.yearly_widget:
            return
        self._create_yearly_widget()
        self._update_ui_state()

    def _create_yearly_widget(self):
        widget = QGroupBox("Yearly (add distinct future years)")
        v = QVBoxLayout(widget)
        row = QHBoxLayout()
        self.year_input = QSpinBox()
        self.year_input.setRange(datetime.now().year, datetime.now().year + 200)
        add_btn = QPushButton("Add Year")
        add_btn.clicked.connect(self._add_year)
        row.addWidget(QLabel("Year:"))
        row.addWidget(self.year_input)
        row.addWidget(add_btn)
        v.addLayout(row)

        self.years_container = QVBoxLayout()
        for y in sorted(self.years):
            self._add_year_row_widget(y)
        v.addLayout(self.years_container)

        delete_btn = QPushButton("Delete Yearly")
        delete_btn.setStyleSheet("background-color: #e67373; color: white; font-weight: bold;")
        delete_btn.clicked.connect(self._remove_yearly)
        v.addWidget(delete_btn)

        self.yearly_widget = widget
        self.layout().addWidget(widget)

    def _add_year(self):
        y = int(self.year_input.value())
        if y in self.years:
            QMessageBox.warning(self.parent_tab, "Duplicate Year", f"{y} already added")
            return
        if y < datetime.now().year:
            QMessageBox.warning(self.parent_tab, "Invalid Year", "Cannot add past years")
            return
        self.years.add(y)
        self._add_year_row_widget(y)
        self._update_ui_state()

    def _add_year_row_widget(self, y):
        row = QHBoxLayout()
        lab = QLabel(str(y))
        delb = QPushButton("Delete")
        delb.clicked.connect(lambda _, yy=y, r=row: self._remove_year(yy, r))
        row.addWidget(lab); row.addWidget(delb)
        self.years_container.addLayout(row)

    def _remove_year(self, y, layout):
        self.years.discard(y)
        while layout.count():
            it = layout.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        self._update_ui_state()

    def _remove_yearly(self):
        if not self.yearly_widget:
            return
        self.yearly_widget.setParent(None)
        self.yearly_widget.deleteLater()
        self.yearly_widget = None
        self.years.clear()
        self._update_ui_state()

    # ---------- state enforcement ----------
    def _update_ui_state(self):
        has_hours = len(self.hours) > 0
        self.add_daily_btn.setEnabled(has_hours and self.daily_widget is None)
        self.add_weekly_btn.setEnabled(has_hours and self.weekly_widget is None)

        # If daily/weekly present and only 1 hour => disable delete for last hour
        if (self.daily_widget or self.weekly_widget) and len(self.hours) == 1:
            for (_, del_btn) in self.hours_ui_rows:
                del_btn.setEnabled(False)
        else:
            for (_, del_btn) in self.hours_ui_rows:
                del_btn.setEnabled(True)

        # Device 'Deselect All' restrictions:
        # - If there are hours OR if daily/weekly exist OR monthly/yearly exist, disable the block's deselect-all
        if self.desel_all_btn:
            if has_hours or self.daily_widget or self.weekly_widget or self.monthly_widget or self.yearly_widget:
                self.desel_all_btn.setEnabled(False)
            else:
                self.desel_all_btn.setEnabled(True)

        # monthly present -> disable deleting daily/weekly and related switches
        if self.monthly_widget:
            if self.daily_widget:
                try:
                    self.delete_daily_btn.setEnabled(False)
                except Exception:
                    pass
            if self.weekly_widget:
                try:
                    self.delete_weekly_btn.setEnabled(False)
                except Exception:
                    pass
            # also disable switching between daily/weekly while monthly exists
            try:
                if self.switch_daily_btn:
                    self.switch_daily_btn.setEnabled(False)
            except Exception:
                pass
            try:
                if self.switch_weekly_btn:
                    self.switch_weekly_btn.setEnabled(False)
            except Exception:
                pass
            # disable daily/weekly's internal "Deselect All" buttons
            try:
                if self.daily_desel_btn:
                    self.daily_desel_btn.setEnabled(False)
            except Exception:
                pass
            try:
                if self.weekly_desel_btn:
                    self.weekly_desel_btn.setEnabled(False)
            except Exception:
                pass
        else:
            if self.daily_widget:
                try:
                    self.delete_daily_btn.setEnabled(True)
                except Exception:
                    pass
            if self.weekly_widget:
                try:
                    self.delete_weekly_btn.setEnabled(True)
                except Exception:
                    pass
            try:
                if self.switch_daily_btn:
                    self.switch_daily_btn.setEnabled(True)
            except Exception:
                pass
            try:
                if self.switch_weekly_btn:
                    self.switch_weekly_btn.setEnabled(True)
            except Exception:
                pass
            try:
                if self.daily_desel_btn:
                    self.daily_desel_btn.setEnabled(True)
            except Exception:
                pass
            try:
                if self.weekly_desel_btn:
                    self.weekly_desel_btn.setEnabled(True)
            except Exception:
                pass

        # yearly present -> disable delete monthly
        if self.yearly_widget and self.monthly_widget:
            try:
                if self.delete_month_btn:
                    self.delete_month_btn.setEnabled(False)
            except Exception:
                pass
        else:
            if self.monthly_widget:
                try:
                    if self.delete_month_btn:
                        self.delete_month_btn.setEnabled(True)
                except Exception:
                    pass

    # ---------- serialization ----------
    def to_dict(self):
        return {
            "main_devices": [i + 1 for i, cb in enumerate(self.device_checkboxes) if cb.isChecked()],
            "hours": list(self.hours),
            "recurrence_mode": self.recurrence_mode,
            "daily_days": sorted(list(self.daily_days)),
            "weekly_days": sorted(list(self.weekly_days)),
            "months": sorted(list(self.months)),
            "years": sorted(list(self.years))
        }

    def load_from_dict(self, data):
        for i, cb in enumerate(self.device_checkboxes):
            cb.setChecked((i + 1) in data.get("main_devices", []))

        for h in data.get("hours", []):
            if h not in self.hours:
                self.hours.append(h)

                # Create the hour "box" like in _on_add_hour
                hour_box = QFrame()
                hour_box.setFrameShape(QFrame.StyledPanel)
                hour_box.setStyleSheet("""
                    QWidget {
                        background-color: #f2f2f2;
                        border-radius: 6px;
                        }
                """)
                box_layout = QHBoxLayout(hour_box)

                box_layout.setContentsMargins(8, 2, 8, 2)
                box_layout.setSpacing(5)

                lbl = QLabel(h)
                del_btn = QPushButton()
                del_btn.setIcon(QIcon(resource_path("icons", "delete.png")))
                del_btn.setFixedSize(20, 20)
                del_btn.setIconSize(del_btn.size())
                del_btn.setStyleSheet("border: none;")
                del_btn.clicked.connect(lambda _, s=h, w=hour_box: self._remove_hour(s, w))

                box_layout.addWidget(lbl)
                box_layout.addWidget(del_btn)

                self.hours_container.addWidget(hour_box)
                self.hours_ui_rows.append((hour_box, del_btn))

        mode = data.get("recurrence_mode")
        if mode == "daily":
            self.recurrence_mode = "daily"
            self.daily_days = set(data.get("daily_days", []))
            self._create_daily_widget()
            for k, cb in getattr(self, "daily_checkboxes", {}).items():
                cb.setChecked(k in self.daily_days)
        elif mode == "weekly":
            self.recurrence_mode = "weekly"
            self.weekly_days = set(data.get("weekly_days", []))
            self._create_weekly_widget()
            for k, cb in getattr(self, "weekday_checkboxes", {}).items():
                cb.setChecked(k in self.weekly_days)

        months = data.get("months", [])
        if months:
            self.months = set(months)
            self._create_monthly_widget()
            for m, cb in getattr(self, "month_checkboxes", {}).items():
                cb.setChecked(m in self.months)

        years = data.get("years", [])
        if years:
            self.years = set(years)
            self._create_yearly_widget()
            for y in sorted(self.years):
                self._add_year_row_widget(y)

        self._update_ui_state()
