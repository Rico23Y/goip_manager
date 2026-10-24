import os
import sys
import time

from plyer import notification
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

from app.core.config import get_appdata_path
from app.utils.paths import resource_path
from app.goip.browser import (
    login_to_device,
    open_viewer_tabs,
    viewer_options,
)
from app.repositories.device_repository import DeviceRepository
from app.repositories.notification_settings_repository import (
    NotificationSettingsRepository,
)
from app.services.notification_service import NotificationService
from app.services.monitoring_service import MonitoringService

NOTIFICATION_FILE = get_appdata_path("notification_setting.json")

notification_settings_repository = NotificationSettingsRepository(
    NOTIFICATION_FILE
)

# ------------------------- internal helpers -------------------------
# Get the correct base path (works both in Python and frozen exe)
if getattr(sys, 'frozen', False):  # Running as EXE
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(__file__)

icon_path = resource_path(base_path, "icons", "notification.ico")

def notify_user(message: str, goip: str, port_index: int):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}")
    # Show notification
    notification.notify(
        title=f"GOIP Alert - {goip}",
        message=message,
        app_icon=icon_path,
        timeout=5
    )
    # You can add signal to switch tab or highlight the port here

# --------------------------- Public API ----------------------------

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


def select_list_mode(driver, wait):
    wait.until(EC.presence_of_element_located((By.ID, "listModeBtn")))
    checkbox = driver.find_element(By.ID, "listModeBtn")

    if not checkbox.is_selected():
        checkbox.click()

    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")


def launch_view_tabs(device_repository, goip_window=0):
    """
    Optional function to open viewer-only tabs (non-scraping UI).
    Can run multiple or single window.
    """
    viewer_driver, viewer_main_window = viewer_options()
    os.system('cls')

    if goip_window == 0:
        try:
            open_viewer_tabs(
                "port_status_en.html",
                "Port Status Opened",
                viewer_driver,
                post_login_action=select_list_mode,
                device_repository=device_repository
            )

            viewer_driver.switch_to.window(viewer_main_window)
            viewer_driver.close()
        except Exception:
            pass

    if goip_window > 0:
        try:
            devices = device_repository.load_devices()

            login_to_device(
                "port_status_en.html",
                "Port Status Opened",
                viewer_driver,
                devices[goip_window - 1],
                post_login_action=select_list_mode
            )
        except Exception:
            pass

notification_service = NotificationService(notify_user)

monitoring_service = MonitoringService(
    check_notifications=notification_service.check_for_notifications,
)


def check_for_notifications(goip: str, data: list):
    notification_service.check_for_notifications(goip, data)


def load_notification_settings():
    try:
        settings = notification_settings_repository.load_settings()
        notification_service.update_settings(settings)

        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            "[INFO] Notification settings reloaded."
        )
    except Exception as e:
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"[ERROR] Failed to load notification settings: {e}"
        )
        notification_service.update_settings({})


def update_notification_settings_from_ui():
    # Call this after saving settings in the UI
    load_notification_settings()
