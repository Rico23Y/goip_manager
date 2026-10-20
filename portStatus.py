import threading
from utils import *
import copy
from collections import defaultdict
from utils import get_appdata_path, resource_path
from app.models.goip_device import GoipDevice
from app.repositories.device_repository import DeviceRepository
from app.repositories.notification_settings_repository import (
    NotificationSettingsRepository,
)
from app.services.port_status_service import scrape_goip_data
from app.services.notification_service import NotificationService

NOTIFICATION_FILE = get_appdata_path("notification_setting.json")

notification_settings_repository = NotificationSettingsRepository(
    NOTIFICATION_FILE
)

pause_event = threading.Event()
pause_remaining = 0  # seconds left to resume

_goip_state = {}
# Prevent multiple concurrent start/stop sequences
_INIT_LOCK = threading.Lock()

# Internal: thread management and run flag
_monitor_threads = {}         # goip -> Thread
_stop_events = {}             # goip -> Event
_RUNNING = False              # True while monitoring is active

# Backoff delays for relaunch (seconds)
RETRY_DELAYS = [60, 240, 600]  # 1 min, 4 mins, 10 mins

# For retries attempt label mapping
attempt_minutes = ['', ': 2 minutes left', ': 5 minutes left (last try)']

_notification_settings = {}

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

def _update_state(ip: str, *, status=None, is_running=None, description=None):
    """
    Lightweight state update for a single GOIP identified by IP.
    One thread writes its own key (ip), so it's safe without a lock.
    """
    entry = _goip_state.get(ip, {"status": [], "isRunning": False, "description": "Not started"})
    if status is not None:
        entry["status"] = status
    if is_running is not None:
        entry["isRunning"] = bool(is_running)
    if description is not None:
        entry["description"] = str(description)
    _goip_state[ip] = entry


# ------------------------- monitor logic ---------------------------

def monitor_scraper_loop(
    device: GoipDevice,
    stop_event: threading.Event
):
    """
    Per-device monitor loop:
    - Logs in once to reuse session
    - Calls scrape_goip_data(device, session)
    - Retries on failure with increasing delay
    - Cancels retry immediately if stop_event is set
    """
    retry_delays = [60, 300, 600]
    max_attempts = len(retry_delays)
    attempt = 0

    ip = device.ip_address
    goip = device.goip

    session = None
    is_online = True

    try:
        while not stop_event.is_set():
            try:
                if session is None:
                    if not is_port_open(ip):
                        _update_state(goip, is_running=False, description="Offline")

                        if is_online:
                            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}]Is ONLINE")
                            ip_sms = f" ({ip})" if ip != "" else ""
                            offline_sms = 'offline' if ip != "" else 'Empty IP address'
                            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🚫 {goip}{ip_sms} is {offline_sms} — skipping.")

                        is_online = False
                        # Small wait to avoid busy-loop if port remains closed
                        if stop_event.wait(10):
                            return
                        continue

                    is_online = True
                    session = login_goip(device)
                    if session is None:
                        _update_state(goip, is_running=False, description="Initial login failed")
                        raise Exception("Initial login failed")

                data = scrape_goip_data(device, session)

                if data is None:

                    raise Exception("scrape_goip_data() returned None")

                # ✅ Success: reset attempts and update state
                check_for_notifications(goip, data)
                _update_state(goip, status=data, is_running=True, description="Running")
                attempt = 0

                # Wait 1 sec before next scrape, but cancel instantly if stopped
                if stop_event.wait(1):
                    return

            except Exception as e:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ({ip}) Error: {e}")
                attempt += 1

                if session is not None:
                    session.close()
                    session = None  # Force re-login next loop

                if attempt >= max_attempts:
                    failed_msg = f"({ip}) ❌ Marked as failed after {attempt} attempts."
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {failed_msg}")
                    _update_state(goip, is_running=False, description=failed_msg)
                    return

                delay = retry_delays[min(attempt - 1, max_attempts - 1)]
                message = f"({ip}) Retrying in {delay} sec... (Attempt {attempt}/{max_attempts})"
                _update_state(goip, is_running=False, description=message)
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}")

                # ⏳ Replace time.sleep with stop_event-aware countdown
                for _ in range(delay):
                    if stop_event.is_set():
                        return  # Exit immediately
                    time.sleep(1)  # Small step to check stop_event frequently

    finally:
        if session is not None:
            try:
                session.close()
            except Exception as error:
                print(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                    f"({ip}) Failed to close session: {error}"
                )
# --------------------------- Public API ----------------------------

def start_goip_monitoring(
    device_repository: DeviceRepository,
    will_run: bool = True
):
    global _RUNNING

    if will_run:
        with _INIT_LOCK:
            if _RUNNING:
                return

            try:
                devices = device_repository.load_devices()
            except Exception as e:
                print(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                    f"[ERROR] Failed to load devices:",
                    e
                )
                return

            load_notification_settings()

            for device in devices:
                goip = device.goip

                if not device.enabled:
                    continue

                if goip in _monitor_threads and _monitor_threads[goip].is_alive():
                    continue

                ev = threading.Event()
                _stop_events[goip] = ev

                t = threading.Thread(
                    target=monitor_scraper_loop,
                    args=(device, ev),
                    daemon=True,
                    name=f"mon-{goip}"
                )

                _monitor_threads[goip] = t
                t.start()

            _RUNNING = True
            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                f"[INFO] GoIP monitoring started."
            )
        return

    # Request all active scraper threads to stop.
    with _INIT_LOCK:
        threads = list(_monitor_threads.values())

        for stop_event in _stop_events.values():
            stop_event.set()

    # Wait outside the lock, with a shared 5-second deadline.
    # This prevents the wait from reaching 5 seconds per device.
    deadline = time.monotonic() + 5

    for thread in threads:
        if thread is not threading.current_thread():
            remaining = max(0, deadline - time.monotonic())
            thread.join(timeout=remaining)

    with _INIT_LOCK:
        still_running = [
            thread.name
            for thread in _monitor_threads.values()
            if thread.is_alive()
        ]

        _RUNNING = bool(still_running)

    if still_running:
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"[WARNING] Some GOIP monitoring threads are still stopping: "
            f"{', '.join(still_running)}"
        )
    else:
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"[INFO] GoIP monitoring stopped."
        )

def get_goip_status_data(device_repository: DeviceRepository) -> dict:
    devices = device_repository.load_devices()

    timeout = 10
    start_time = time.time()

    while time.time() - start_time < timeout:
        if len(_goip_state) == len(devices):
            break
        time.sleep(0.05)

    return copy.deepcopy(_goip_state)


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


def check_for_notifications(goip: str, data: list):
    notification_service.check_for_notifications(goip, data)


def load_notification_settings():
    global _notification_settings

    try:
        _notification_settings = (
            notification_settings_repository.load_settings()
        )
        notification_service.update_settings(_notification_settings)

        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            "[INFO] Notification settings reloaded."
        )
    except Exception as e:
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"[ERROR] Failed to load notification settings: {e}"
        )
        _notification_settings = {}
        notification_service.update_settings({})

def update_notification_settings_from_ui():
    # Call this after saving settings in the UI
    load_notification_settings()
