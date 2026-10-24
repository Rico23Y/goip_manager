from __future__ import annotations

import time

from plyer import notification

from app.core.config import get_appdata_path
from app.repositories.device_repository import DeviceRepository
from app.repositories.notification_settings_repository import (
    NotificationSettingsRepository,
)
from app.services.monitoring_service import MonitoringService
from app.services.notification_service import NotificationService
from app.utils.paths import resource_path


NOTIFICATION_FILE = get_appdata_path("notification_setting.json")

notification_settings_repository = NotificationSettingsRepository(
    NOTIFICATION_FILE
)

icon_path = resource_path("icons", "notification.ico")


def notify_user(message: str, goip: str, port_index: int) -> None:
    """Print a monitoring alert and show a desktop notification."""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}")
    notification.notify(
        title=f"GOIP Alert - {goip}",
        message=message,
        app_icon=icon_path,
        timeout=5,
    )


notification_service = NotificationService(notify_user)

monitoring_service = MonitoringService(
    check_notifications=notification_service.check_for_notifications,
)


def load_notification_settings() -> None:
    """Load notification settings and update the shared notification service."""
    try:
        settings = notification_settings_repository.load_settings()
        notification_service.update_settings(settings)

        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            "[INFO] Notification settings reloaded."
        )
    except Exception as error:
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"[ERROR] Failed to load notification settings: {error}"
        )
        notification_service.update_settings({})


def start_goip_monitoring(
    device_repository: DeviceRepository,
    will_run: bool = True,
) -> None:
    """Start or stop GOIP monitoring through the monitoring service."""
    monitoring_service.start(
        device_repository=device_repository,
        will_run=will_run,
        load_settings=load_notification_settings,
    )


def get_goip_status_data(
    device_repository: DeviceRepository,
) -> dict:
    """Return the current GOIP monitoring state."""
    return monitoring_service.get_status_data(device_repository)


def check_for_notifications(goip: str, data: list) -> None:
    """Check one GOIP device's data against the notification settings."""
    notification_service.check_for_notifications(goip, data)


def update_notification_settings_from_ui() -> None:
    """Reload settings after they have been saved by the UI."""
    load_notification_settings()
