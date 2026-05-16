# login_tab.py
import os
from PySide6.QtGui import QRegularExpressionValidator, QIcon, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QLabel, QScrollArea, QSizePolicy, QFrame, QMessageBox
)
from PySide6.QtCore import (
    QRegularExpression, Qt, QTimer, QSize, QPoint, QEasingCurve, QPropertyAnimation,
    QParallelAnimationGroup, Signal
)
from utils import launch_home_tabs, reload_devices, resource_path

# Small, consistent button and icon sizes
_BTN_SIZE = QSize(28, 28)
_ICON_SIZE = QSize(18, 18)


class DeviceRow(QWidget):
    """
    A single device login row displayed as a 'card':
      - IP / Username / Password fields
      - Icon buttons for show/hide password, move up/down, and text 'Delete'
      - Red border validation when IP is filled but Username or Password is empty
      - Add / Delete height animations
      - Smooth swap animation (Up/Down) using overlay ghosts
    """
    def __init__(self, parent_layout, main_window):
        super().__init__()
        self.parent_layout = parent_layout
        self.main_window = main_window

        self._has_error = False   # tracks red-border state across updates
        self._swap_anim_group = None
        self._swap_ghosts = None
        self._swap_placeholders = None

        # ============ Root/container ============
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(4, 6, 4, 6)
        self.root_layout.setSpacing(0)

        self.card = QFrame()
        self.card.setObjectName("deviceCard")
        self.card.setFrameShape(QFrame.StyledPanel)
        self.root_layout.addWidget(self.card)

        # ============ Row contents ============
        self.row_layout = QHBoxLayout(self.card)
        self.row_layout.setContentsMargins(10, 8, 10, 8)
        self.row_layout.setSpacing(8)

        # Label (light grey, bold)
        self.label = QLabel("GOIP ?")
        self.label.setObjectName("goipLabel")
        self.label.setMinimumWidth(70)
        self.label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        font = self.label.font()
        font.setBold(True)
        self.label.setFont(font)

        # Validators
        ip_regex = QRegularExpression(r"[0-9.]+")
        ip_validator = QRegularExpressionValidator(ip_regex)

        # --- Input groups with persistent labels ---
        self.ip_label = QLabel("IP Address:")
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("IP Address")
        self.ip_input.setValidator(ip_validator)
        self.ip_input.setFixedWidth(150)

        self.username_label = QLabel("Username:")
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        self.username_input.setFixedWidth(140)

        self.password_label = QLabel("Password:")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setFixedWidth(140)

        # Buttons with icons (fixed sizes)
        self.toggle_password_btn = QPushButton()
        self._icon_show = QIcon(QPixmap(resource_path("icons", "hidden.png")))   # "Show"
        self._icon_hide = QIcon(QPixmap(resource_path("icons", "eye.png")))      # "Hide"
        self._prep_icon_button(self.toggle_password_btn, self._icon_show, "Show/Hide Password")
        self.toggle_password_btn.clicked.connect(self.toggle_password_visibility)

        self.move_up_btn = QPushButton()
        self._icon_up = QIcon(QPixmap(resource_path("icons", "arrow_up.png")))
        self._prep_icon_button(self.move_up_btn, self._icon_up, "Move Up")
        self.move_up_btn.clicked.connect(self.move_up)

        self.move_down_btn = QPushButton()
        self._icon_down = QIcon(QPixmap(resource_path("icons", "arrow_down.png")))
        self._prep_icon_button(self.move_down_btn, self._icon_down, "Move Down")
        self.move_down_btn.clicked.connect(self.move_down)

        self.delete_btn = QPushButton()
        self._icon_delete = QIcon(QPixmap(resource_path("icons", "delete.png")))
        self._prep_icon_button(self.delete_btn, self._icon_delete, "Delete")
        self.delete_btn.clicked.connect(self.delete_self)

        # NEW: Browser button
        self.browser_btn = QPushButton()
        self._icon_browser = QIcon(QPixmap(resource_path("icons", "browser.png")))
        self._prep_icon_button(self.browser_btn, self._icon_browser, "Open Home in Browser")
        self.browser_btn.clicked.connect(self.open_home_in_browser)

        # Assemble
        self.row_layout.addWidget(self.label)

        # Add label + input side by side
        for lbl, inp in [
            (self.ip_label, self.ip_input),
            (self.username_label, self.username_input),
            (self.password_label, self.password_input),
        ]:
            self.row_layout.addWidget(lbl)
            self.row_layout.addWidget(inp)

        # Add toggle password button
        self.row_layout.addWidget(self.toggle_password_btn)

        # Add stretch to push everything after it to the right
        self.row_layout.addStretch(1)

        # Right side (action buttons)
        for w in [self.move_up_btn, self.move_down_btn, self.browser_btn, self.delete_btn]:
            self.row_layout.addWidget(w)

        # Initial styling (includes label -> light grey)
        self._apply_style()

        # Validation
        self.ip_input.textChanged.connect(self._update_validation_state)
        self.username_input.textChanged.connect(self._update_validation_state)
        self.password_input.textChanged.connect(self._update_validation_state)

        QTimer.singleShot(0, self._animate_appear)

    def unsaved_message(self):
        # ✅ Only show the message box if there are unsaved changes
        if not self.parent_layout.has_unsaved_changes():
            return True  # no unsaved changes → continue directly

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Unsaved Changes")
        msg_box.setText("You have unsaved changes. Save before opening browser?")
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)

        # ✅ Apply light theme just for this dialog
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: #ffffff;
            }
            QMessageBox QLabel {
                color: black;
                font-size: 13px;
            }
            QMessageBox QPushButton {
                background-color: #f5f5f5;
                color: black;
                border: 1px solid #b5b3b3;
                border-radius: 6px;
                padding: 4px 10px;
                min-width: 70px;
            }
            QMessageBox QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)

        reply = msg_box.exec()

        if reply == QMessageBox.Yes:
            self.main_window.save_devices_to_file()
            return True  # continue
        elif reply == QMessageBox.No:
            return True  # continue without saving
        elif reply == QMessageBox.Cancel:
            return False  # stop

    def open_home_in_browser(self):
        goip_index = self.parent_layout.indexOf(self) + 1  # 1-based index
        if not self.unsaved_message():
            return  # Cancel clicked → stop here
        launch_home_tabs(goip_index)

    # ---------- Styling helpers ----------
    def _apply_style(self):
        """Apply stylesheet combining current error border state + label color."""
        base_bg = "#d9eafc"
        border_normal = "#bddafc"
        border_error = "#ff4d4f"
        label_grey = "#1f1f1f"  # light grey for GOIP label

        border_col = border_error if self._has_error else border_normal

        self.card.setStyleSheet(f"""
            QFrame#deviceCard {{
                background: {base_bg};
                border: 1px solid {border_col};
                border-radius: 10px;
            }}
            QLabel#goipLabel {{
                color: {label_grey};
            }}
            QLineEdit {{
                padding: 6px;
                background: #ffffff;
            }}
            QPushButton {{
                padding: 4px;   /* compact so icons don't look crowded */
            }}
            QPushButton:hover {{
                background: rgba(255,255,255,0.06);
            }}
            QPushButton:disabled {{
                opacity: 0.5;
            }}
            QToolTip {{
                background-color: #f5f5f5;  /* light background */
                color: black;               /* readable text */
                border: 1px solid #b5b3b3;
                padding: 4px;
                font-size: 12px;
            }}
        """)

    def _prep_icon_button(self, btn: QPushButton, icon: QIcon, tooltip: str):
        btn.setIcon(icon)
        btn.setIconSize(_ICON_SIZE)
        btn.setFixedSize(_BTN_SIZE)
        btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        btn.setFlat(True)
        btn.setToolTip(tooltip)
        btn.setFocusPolicy(Qt.TabFocus)

    # ---------- Data ----------
    def to_dict(self):
        return {
            "ip": self.ip_input.text(),
            "username": self.username_input.text(),
            "password": self.password_input.text()
        }

    # ---------- Validation (sets _has_error then re-applies style) ----------
    def _update_validation_state(self):
        ip = self.ip_input.text().strip()
        user_ok = bool(self.username_input.text().strip())
        pass_ok = bool(self.password_input.text().strip())
        self._has_error = bool(ip) and (not user_ok or not pass_ok)
        self._apply_style()

    # ---------- Password toggle ----------
    def toggle_password_visibility(self):
        if self.password_input.echoMode() == QLineEdit.Password:
            self.password_input.setEchoMode(QLineEdit.Normal)
            self.toggle_password_btn.setIcon(self._icon_hide)   # mapping requested
            self.toggle_password_btn.setIconSize(_ICON_SIZE)
        else:
            self.password_input.setEchoMode(QLineEdit.Password)
            self.toggle_password_btn.setIcon(self._icon_show)
            self.toggle_password_btn.setIconSize(_ICON_SIZE)

    # ---------- Add animation (height expand only) ----------
    def _animate_appear(self):
        self.setMaximumHeight(0)
        target = max(self.sizeHint().height(), 1)

        steps = 6
        duration_ms = 120
        step_ms = max(1, duration_ms // steps)
        delta = max(1, target // steps)

        def step(i=[0]):
            if i[0] >= steps:
                self.setMaximumHeight(16777215)
                self.updateGeometry()
                return
            self.setMaximumHeight(min(target, (i[0] + 1) * delta))
            i[0] += 1
            QTimer.singleShot(step_ms, step)

        QTimer.singleShot(0, step)

    # ---------- Smooth swap animation between self and neighbor ----------
    def _animate_swap_with(self, other_row):
        layout = self.parent_layout
        if getattr(layout, "animating", False):
            return
        layout.animating = True

        # The common container widget that both rows are parented to
        container = self.parentWidget()

        # Ensure geometry is up-to-date
        container.update()
        self.update()
        other_row.update()

        # Top-left positions in container coordinates
        start_a = self.mapTo(container, QPoint(0, 0))
        start_b = other_row.mapTo(container, QPoint(0, 0))
        size_a = self.size()
        size_b = other_row.size()

        # Overlay "ghosts"
        pix_a = self.grab()
        pix_b = other_row.grab()

        ghost_a = QLabel(container)
        ghost_a.setPixmap(pix_a)
        ghost_a.setGeometry(start_a.x(), start_a.y(), size_a.width(), size_a.height())
        ghost_a.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        ghost_a.raise_()
        ghost_a.show()

        ghost_b = QLabel(container)
        ghost_b.setPixmap(pix_b)
        ghost_b.setGeometry(start_b.x(), start_b.y(), size_b.width(), size_b.height())
        ghost_b.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        ghost_b.raise_()
        ghost_b.show()

        # Placeholders keep layout space stable
        ph_a = QWidget(container)
        ph_a.setFixedHeight(size_a.height())
        ph_a.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        ph_b = QWidget(container)
        ph_b.setFixedHeight(size_b.height())
        ph_b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Indices BEFORE removal
        idx_a = layout.indexOf(self)
        idx_b = layout.indexOf(other_row)

        # Remove higher index first to avoid shifting
        if idx_a > idx_b:
            first_w, first_idx, first_ph = self, idx_a, ph_a
            second_w, second_idx, second_ph = other_row, idx_b, ph_b
        else:
            first_w, first_idx, first_ph = other_row, idx_b, ph_b
            second_w, second_idx, second_ph = self, idx_a, ph_a

        # Guarded insertion of placeholders
        def bail_cleanup():
            # Ensure everything becomes interactive again on error
            for w in (self, other_row):
                w.show()
            for g in (ghost_a, ghost_b):
                g.deleteLater()
            for p in (ph_a, ph_b):
                if p is not None and p.parent() is not None:
                    try:
                        layout.removeWidget(p)
                    except Exception:
                        pass
                p.deleteLater()
            layout.animating = False

        try:
            layout.removeWidget(first_w)
            layout.insertWidget(first_idx, first_ph)
            layout.removeWidget(second_w)
            layout.insertWidget(second_idx, second_ph)
            # Hide real widgets during animation
            self.hide()
            other_row.hide()
        except Exception:
            bail_cleanup()
            return

        # Build animations (owned by a group so they don't get GC'ed)
        dur = 240
        easing = QEasingCurve.OutCubic

        anim_a = QPropertyAnimation(ghost_a, b"pos", container)
        anim_a.setDuration(dur)
        anim_a.setEasingCurve(easing)
        anim_a.setStartValue(start_a)
        anim_a.setEndValue(start_b)

        anim_b = QPropertyAnimation(ghost_b, b"pos", container)
        anim_b.setDuration(dur)
        anim_b.setEasingCurve(easing)
        anim_b.setStartValue(start_b)
        anim_b.setEndValue(start_a)

        group = QParallelAnimationGroup(container)
        group.addAnimation(anim_a)
        group.addAnimation(anim_b)

        # Keep references to prevent GC
        self._swap_anim_group = group
        self._swap_ghosts = (ghost_a, ghost_b)
        self._swap_placeholders = (ph_a, ph_b)

        def finish():
            # Placeholders' indices now indicate where to put swapped widgets
            idx_ph_a = layout.indexOf(ph_a)
            idx_ph_b = layout.indexOf(ph_b)

            layout.removeWidget(ph_a)
            layout.insertWidget(idx_ph_a, other_row)

            layout.removeWidget(ph_b)
            layout.insertWidget(idx_ph_b, self)

            # Clean overlays
            ghost_a.deleteLater()
            ghost_b.deleteLater()
            ph_a.deleteLater()
            ph_b.deleteLater()

            # Show real widgets again
            self.show()
            other_row.show()

            # Update labels, buttons, and save
            layout.update_goip_labels()
            layout.update_delete_buttons()
            layout.main_window.save_devices_to_file()

            # Clear refs & unlock
            self._swap_anim_group = None
            self._swap_ghosts = None
            self._swap_placeholders = None
            layout.animating = False

        group.finished.connect(finish)
        group.start()

    # ---------- Collapse & remove ----------
    def _animate_disappear_and_remove(self):
        curr_h = self.height() or self.sizeHint().height()
        self.setMaximumHeight(curr_h)

        steps = 6
        duration_ms = 140
        step_ms = max(1, duration_ms // steps)
        delta = max(1, curr_h // steps)

        def step(i=[0]):
            if i[0] >= steps:
                # finalize removal
                self.setParent(None)
                self.parent_layout.removeWidget(self)
                self.deleteLater()
                self.parent_layout.update_goip_labels()
                self.parent_layout.update_delete_buttons()
                self.parent_layout.main_window.save_devices_to_file()
                return
            self.setMaximumHeight(max(0, curr_h - (i[0] + 1) * delta))
            i[0] += 1
            QTimer.singleShot(step_ms, step)

        QTimer.singleShot(0, step)

    # ---------- Row actions ----------
    def delete_self(self):
        self._animate_disappear_and_remove()

    def move_up(self):
        layout = self.parent_layout
        if getattr(layout, "animating", False):
            return
        idx = layout.indexOf(self)
        if idx > 0:
            prev_row = layout.itemAt(idx - 1).widget()
            self._animate_swap_with(prev_row)

    def move_down(self):
        layout = self.parent_layout
        if getattr(layout, "animating", False):
            return
        idx = layout.indexOf(self)
        if idx < layout.count() - 1:
            next_row = layout.itemAt(idx + 1).widget()
            self._animate_swap_with(next_row)




class DeviceListLayout(QVBoxLayout):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setSpacing(6)
        self.setContentsMargins(8, 8, 8, 8)
        self.animating = False

    def has_unsaved_changes(self):
        current = []
        for i in range(self.count()):
            widget = self.itemAt(i).widget()
            if isinstance(widget, DeviceRow):
                current.append(widget.to_dict())

        saved = reload_devices()

        # compare only ip/username/password fields
        return current != [
            {k: v for k, v in d.items() if k in ("ip", "username", "password")}
            for d in saved
        ]

    def open_all_in_browser(self):
        # ✅ Only check once at the layout level
        if self.has_unsaved_changes():
            # just pick the first DeviceRow to show the dialog
            for i in range(self.count()):
                row = self.itemAt(i).widget()
                if isinstance(row, DeviceRow):
                    proceed = row.unsaved_message()
                    if not proceed:
                        return  # Cancel clicked → stop everything
                    break  # only show ONE dialog
        # ✅ Safe to launch now
        launch_home_tabs(0)

    def update_goip_labels(self):
        for i in range(self.count()):
            widget = self.itemAt(i).widget()
            if isinstance(widget, DeviceRow):
                widget.label.setText(f"GOIP {i + 1}")

    def update_delete_buttons(self):
        total = sum(
            1 for i in range(self.count())
            if isinstance(self.itemAt(i).widget(), DeviceRow)
        )
        for i in range(self.count()):
            widget = self.itemAt(i).widget()
            if isinstance(widget, DeviceRow):
                widget.delete_btn.setEnabled(total > 1)




import os, sys, winreg
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QScrollArea, QSizePolicy, QFrame, QCheckBox
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

def create_login_tab(main_window):
    # === CONFIG (rounded scrollable container) ===
    SCROLL_BG = "#f2f8ff"     # background color of the scrollable container
    RADIUS    = 12            # corner radius in px
    BORDER_COLOR = "#bddafc"  # thin border color
    # ============================================

    login_page = QWidget()
    login_layout = QVBoxLayout(login_page)
    login_layout.setContentsMargins(8, 8, 8, 8)
    login_layout.setSpacing(6)

    # Scroll area
    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setFrameShape(QFrame.NoFrame)
    scroll_area.setStyleSheet("QScrollArea { background: transparent; border: 0; }")
    scroll_area.viewport().setStyleSheet("background: transparent;")

    # Scroll content
    scroll_content = QWidget()
    scroll_content.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)

    scroll_layout = QVBoxLayout(scroll_content)
    scroll_layout.setAlignment(Qt.AlignTop)
    scroll_layout.setContentsMargins(0, 0, 0, 0)
    scroll_layout.setSpacing(0)

    devices_layout = DeviceListLayout(main_window)
    main_window.devices_layout = devices_layout  # accessible in MainApp
    scroll_layout.addLayout(devices_layout)

    scroll_area.setWidget(scroll_content)

    # ---- Rounded "card" wrapper for the scroll area ----
    card = QFrame()
    card.setObjectName("scrollCard")
    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(0, 0, 0, 0)
    card_layout.setSpacing(0)
    card_layout.addWidget(scroll_area)

    card.setStyleSheet(f"""
        QFrame#scrollCard {{
            background-color: {SCROLL_BG};
            border-radius: {RADIUS}px;
            border: 1px solid {BORDER_COLOR};
        }}
    """)

    login_layout.addWidget(card)

    # ---- Bottom buttons ----
    button_layout = QHBoxLayout()
    button_layout.setContentsMargins(0, 0, 0, 0)

    add_btn = QPushButton("Add Device")
    save_btn = QPushButton("Save Devices")
    browser_open_btn = QPushButton("Open all home page in browser")

    # ✅ Startup checkbox
    startup_checkbox = QCheckBox("Start with Windows startup")

    # Set icon on browser button
    browser_icon = QIcon(resource_path("icons", "browser.png"))
    browser_open_btn.setIcon(browser_icon)
    browser_open_btn.setIconSize(_ICON_SIZE)

    # Set icon on save button
    save_icon = QIcon(resource_path("icons", "diskette.png"))
    save_btn.setIcon(save_icon)
    save_btn.setIconSize(_ICON_SIZE)

    # Set icon on add button
    add_icon = QIcon(resource_path("icons", "plus.png"))
    add_btn.setIcon( add_icon)
    add_btn.setIconSize(_ICON_SIZE)

    # Wire actions
    add_btn.clicked.connect(main_window.add_device_row)
    save_btn.clicked.connect(main_window.save_devices_to_file)
    browser_open_btn.clicked.connect(devices_layout.open_all_in_browser)

    # --- Startup logic ---
    def get_exe_path():
        if getattr(sys, "frozen", False):
            return os.path.abspath(sys.executable)  # when packaged
        return os.path.abspath(sys.argv[0])

    def is_in_startup():
        key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(reg_key, "GoIP.Manager")
            winreg.CloseKey(reg_key)
            return value == get_exe_path()
        except FileNotFoundError:
            return False
        except OSError:
            return False

    def toggle_startup(state):
        key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        exe_path = get_exe_path()
        if state:  # Enable startup
            reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(reg_key, "GoIP.Manager", 0, winreg.REG_SZ, exe_path)
            winreg.CloseKey(reg_key)
        else:  # Disable startup
            try:
                reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE)
                winreg.DeleteValue(reg_key, "GoIP.Manager")
                winreg.CloseKey(reg_key)
            except FileNotFoundError:
                pass

    # Set initial checkbox state + connect
    startup_checkbox.setChecked(is_in_startup())
    startup_checkbox.stateChanged.connect(toggle_startup)

    # Add widgets in order
    button_layout.addWidget(startup_checkbox)
    button_layout.addStretch(1)  # push Save + Add to right
    button_layout.addWidget(browser_open_btn)
    button_layout.addWidget(save_btn)
    button_layout.addWidget(add_btn)

    login_layout.addLayout(button_layout)

    return login_page


