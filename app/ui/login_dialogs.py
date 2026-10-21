
import os

from plyer import notification
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMessageBox

from app.utils.paths import resource_path


def show_login_error_popup(message: str, parent=None) -> None:
    """Show a system notification and GUI popup for a GOIP login error."""

    def _show() -> None:
        notification.notify(
            title="GOIP Login Error",
            message=message,
            app_icon=(
                resource_path("icons", "notification.ico")
                if os.path.exists(
                    resource_path("icons", "notification.ico")
                )
                else None
            ),
            timeout=5,
        )

        msg = QMessageBox(parent)
        msg.setWindowTitle("GOIP Login Error")

        icon_path = resource_path("icons", "notification.png")
        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
            msg.setWindowIcon(icon)
            msg.setIconPixmap(icon.pixmap(48, 48))

        msg.setText(message)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.setDefaultButton(QMessageBox.StandardButton.Ok)
        msg.setWindowFlags(
            msg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )
        msg.exec()

    QTimer.singleShot(0, _show)
