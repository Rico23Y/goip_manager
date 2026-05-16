import os, json, calendar, time, pytz
from datetime import datetime, timedelta
from PySide6.QtCore import Qt, QTimer, QDateTime, QTime, QThread, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox,
    QPushButton, QScrollArea, QGroupBox, QFrame, QTimeEdit, QMessageBox,
    QDateTimeEdit, QGridLayout, QSpinBox, QSizePolicy
)

# Your restart implementation (must exist)
from restart import launch_restart_tabs
from utils import get_appdata_path, resource_path

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

DEVICES_FILE = get_appdata_path("devices.json")
RESTART_FILE = get_appdata_path("restart_setting.json")

# ---------- Helpers ----------
def _days_in_month(year, month):
    return calendar.monthrange(year, month)[1]


def _next_occurrence_search(now, hour, minute, recurrence, selected_days, selected_weekdays, selected_months,
                            selected_years, tz, max_days=365 * 5):
    """
    Forward search that honors:
    - recurrence: 'daily' or 'weekly'
    - selected_days: day-of-month set (1..31)
    - selected_weekdays: set(0..6)
    - selected_months: set(1..12)
    - selected_years: set(year ints)
    Special rule: if selected day > days in month for that month, it's treated as day 1 next month.
    """
    start_dt = now
    start_date = now.date()
    for offset in range(0, max_days + 1):
        candidate_date = start_date + timedelta(days=offset)
        y, m, d = candidate_date.year, candidate_date.month, candidate_date.day

        # Year filter
        if selected_years and y not in selected_years:
            continue

        # Month filter
        if selected_months and m not in selected_months:
            continue

        match = False
        if recurrence == "weekly":
            if selected_weekdays:
                if candidate_date.weekday() in selected_weekdays:
                    match = True
            else:
                match = True
        else:  # daily-like
            if selected_days:
                if d in selected_days:
                    match = True
                else:
                    # overflow mapping: if candidate day is 1, see if any selected_day > prev month's dim
                    if d == 1:
                        prev_m = m - 1
                        prev_y = y
                        if prev_m == 0:
                            prev_m = 12
                            prev_y -= 1
                        prev_dim = _days_in_month(prev_y, prev_m)
                        for s in selected_days:
                            if s > prev_dim:
                                match = True
                                break
            else:
                match = True

        if not match:
            continue

        try:
            candidate_naive = datetime(y, m, d, hour, minute)
        except ValueError:
            continue

        try:
            candidate_dt = tz.localize(candidate_naive)
        except Exception:
            candidate_dt = candidate_naive.replace(tzinfo=tz)

        if candidate_dt > start_dt:
            return candidate_dt
    return None


# ---------- Worker ----------
class RestartWorker(QThread):
    finished = Signal()

    def __init__(self, device_index):
        super().__init__()
        self.device_index = device_index  # -1 => all, otherwise 0-based index

    def run(self):
        try:
            try:
                launch_restart_tabs(self.device_index + 1)
            except Exception:
                pass
        finally:
            self.finished.emit()


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
            cb = QCheckBox(d.get("goip", "Unknown"))
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
    from PySide6.QtGui import QIcon

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


class RestartTab(QWidget):
    def __init__(self, devices_file=DEVICES_FILE, settings_file=RESTART_FILE, parent=None):
        super().__init__(parent)
        self.devices_file = devices_file
        self.settings_file = settings_file
        self.devices = self._load_devices()

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
            cb = QCheckBox(d.get("goip", "Unknown"))
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

    def _load_devices(self):
        if os.path.exists(self.devices_file):
            with open(self.devices_file, "r", encoding="utf-8") as f:
                try:
                    return json.load(f)
                except Exception:
                    return []
        return []

    def _refresh_devices(self):
        self.devices = self._load_devices()

        # --- Refresh main devices group checkboxes ---
        if hasattr(self, "main_device_checkboxes"):
            for cb in self.main_device_checkboxes:
                cb.setParent(None)  # remove from layout
            self.main_device_checkboxes.clear()

            for d in self.devices:
                cb = QCheckBox(d.get("goip", "Unknown"))
                self.main_device_checkboxes.append(cb)
                # Find the layout inside the scroll area and add the checkbox
                scroll_area = self.main_devices_group.findChild(QScrollArea)
                if scroll_area:
                    dev_container = scroll_area.widget()
                    if dev_container:
                        dev_layout = dev_container.layout()
                        dev_layout.addWidget(cb)

        # --- Refresh schedule block device checkboxes ---
        for i in range(self.blocks_container.count()):
            item = self.blocks_container.itemAt(i)
            block = item.widget()
            if block and hasattr(block, "device_checkboxes"):
                # Remove old checkboxes
                for cb in block.device_checkboxes:
                    cb.setParent(None)
                block.device_checkboxes.clear()

                # Add new checkboxes
                dev_scroll = block.findChild(QScrollArea)
                if dev_scroll:
                    dev_container = dev_scroll.widget()
                    if dev_container:
                        dev_layout = dev_container.layout()
                        for idx, d in enumerate(self.devices):
                            cb = QCheckBox(d.get("goip", "Unknown"))
                            cb.stateChanged.connect(lambda st, i=idx: block._device_toggled(i, st))
                            block.device_checkboxes.append(cb)
                            dev_layout.addWidget(cb)

        QMessageBox.information(self, "Devices Refreshed", "Devices have been refreshed in all blocks.")

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
            w = RestartWorker(n - 1)
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

    def _gather_next_for_block_hour(self, blk, hour_str, now):
        try:
            tz = pytz.timezone(self.tz_dropdown.currentText())
        except Exception:
            tz = pytz.UTC
        hh, mm = map(int, hour_str.split(":"))
        if blk.recurrence_mode == "daily":
            recurrence = "daily"
            selected_days = set(blk.daily_days)
            selected_weekdays = set()
        elif blk.recurrence_mode == "weekly":
            recurrence = "weekly"
            selected_weekdays = set(blk.weekly_days)
            selected_days = set()
        else:
            recurrence = "daily"
            selected_days = set()
            selected_weekdays = set()
        months = set(blk.months) if blk.months else set()
        years = set(blk.years) if blk.years else set()
        return _next_occurrence_search(now, hh, mm, recurrence, selected_days, selected_weekdays, months, years, tz)

    def _gather_all_next_entries(self):
        now = self._current_reference_datetime()
        # if custom_applied and custom_running -> make sure to not modify custom_now here
        out = []
        for i in range(self.blocks_container.count()):
            item = self.blocks_container.itemAt(i)
            blk = item.widget() if item else None
            if not blk:
                continue
            for hour in blk.hours:
                nxt = self._gather_next_for_block_hour(blk, hour, now)
                if nxt:
                    out.append((nxt, blk, hour))
        return out

    def _find_next_event(self):
        entries = self._gather_all_next_entries()
        if not entries:
            return None, None, None
        entries.sort(key=lambda t: t[0])
        return entries[0]

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
        after_delta = now - next_dt
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
                w = RestartWorker(di)
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
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            QMessageBox.information(self, "Saved", "Restart settings saved.")
        except Exception:
            QMessageBox.warning(self, "Save Failed", "Could not save restart settings.")

    def _load_settings(self):
        if not os.path.exists(self.settings_file):
            return
        try:
            with open(self.settings_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
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
def create_restart_tab():
    return RestartTab()

