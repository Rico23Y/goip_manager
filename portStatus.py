import json, threading
from utils import *
import copy
from collections import defaultdict
from utils import get_appdata_path, resource_path

NOTIFICATION_FILE = get_appdata_path("notification_setting.json")

pause_event = threading.Event()
pause_remaining = 0  # seconds left to resume

_last_sim_status = defaultdict(dict)       # goip -> port -> last sim_status
_last_network_count = defaultdict(lambda: None)  # goip -> last match count
_last_signal_alert = defaultdict(lambda: None)   # goip -> last signal alert (bar or custom)

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

def scrape_goip_data(device, session):
    ip = device["ip"]
    data_url = f"http://{ip}/get_parameter.html"

    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    payload = "type=updatePortStatusDetail"

    try:
        data_resp = session.post(data_url, headers=headers, data=payload, timeout=5)
        data_json = data_resp.json()
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ({ip}) Failed to retrieve or parse port data: {e}")
        return None

    result = []
    for row in data_json.get("data", []):
        try:
            signal = row[7]
            network = row[9]
            portChannel = row[2]
            simStatus = row[13]
            statusDuration = row[14]
            if signal == '':
                network = 0

            result.append([simStatus, signal, network, portChannel, statusDuration])
        except IndexError:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ({ip}) Skipped malformed row: {row}")
            continue

    #print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ✔️ {device["goip"]} Scrape successful ({device["ip"]}).")
    return result

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

def monitor_scraper_loop(device: dict, stop_event: threading.Event):
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
    ip = device["ip"]
    goip = device["goip"]
    session = None
    is_online = True

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


# --------------------------- Public API ----------------------------

def start_goip_monitoring(will_run: bool = True):
    """
    Start or stop the background monitoring system.

    - start_goip_monitoring(True):
        * opens scraper tabs (once)
        * starts one monitor thread per GOIP (parallel)
    - start_goip_monitoring(False):
        * signals all threads to stop and closes all scraper drivers
        * leaves _goip_state with isRunning=False and description 'Stopped by user'
    """
    global _RUNNING, devices

    with _INIT_LOCK:
        if will_run:
            if _RUNNING:
                # Already running; nothing to do
                return
            try:
                devices = reload_devices()
            except Exception as e:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] Failed to load devices.json:", e)
                return
            load_notification_settings()

            # Start per-GOIP monitor threads (parallel)
            for device in devices:
                goip = device["goip"]

                if not device.get("enabled", True):  # Optional: support disabling
                    continue

                if goip in _monitor_threads and _monitor_threads[goip].is_alive():
                    continue

                ev = threading.Event()
                _stop_events[goip] = ev
                t = threading.Thread(target=monitor_scraper_loop, args=(device, ev),
                                     daemon=True, name=f"mon-{goip}")

                _monitor_threads[goip] = t
                t.start()

            _RUNNING = True
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] GoIP monitoring started.")

        else:
            if not _RUNNING:
                # Already stopped
                return
            # Signal all threads to stop
            for ev in _stop_events.values():
                ev.set()

            # Join threads
            for goip, t in list(_monitor_threads.items()):
                try:
                    t.join(timeout=3.0)
                except Exception:
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Time out",Exception)
                    pass

            _monitor_threads.clear()
            _stop_events.clear()

            # Mark states as stopped
            for goip in list(_goip_state.keys()):
                _update_state(goip, is_running=False, description="Stopped by user")

            _RUNNING = False
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] GoIP monitoring stopped.")

def get_goip_status_data() -> dict:
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


def launch_view_tabs(goip_window = 0):
    """
    Optional function to open viewer-only tabs (non-scraping UI).
    Can run multiple or single window
    """
    viewer_driver, viewer_main_window = viewer_options()
    os.system('cls')

    if goip_window == 0 :
        try:
            open_viewer_tabs("port_status_en.html", "Port Status Opened",
                             viewer_driver, post_login_action=select_list_mode)

            viewer_driver.switch_to.window(viewer_main_window)
            viewer_driver.close()
        except Exception:
            pass

    if goip_window > 0:
        try:
            devices = reload_devices()
            login_to_device("port_status_en.html", "Port Status Opened",
                            viewer_driver, devices[goip_window - 1], post_login_action=select_list_mode)
        except Exception:
            pass

def check_for_notifications(goip: str, data: list):
    settings = _notification_settings
    if not settings.get("enabled", False):
        return

    # === SIM STATUS ===
    sim_config = settings.get("sim_status", {})
    if sim_config.get("enabled", False):
        sim_alerts = sim_config.get("values", [])
        for idx, row in enumerate(data):
            sim_status = row[0]
            if sim_status in sim_alerts and sim_status != _last_sim_status[goip].get(idx):
                sim_text = status_map.get(sim_status, f"Code {sim_status}")
                notify_user(f"{goip} port {idx + 1}{row[3]} - {sim_text}", goip, idx)
                _last_sim_status[goip][idx] = sim_status

    # === NETWORK TYPE ===
    net_config = settings.get("network_type", {})
    if net_config.get("enabled", False):
        values = net_config.get("values", [])
        operator = net_config.get("operator", ">")
        count_threshold = net_config.get("count", 0)
        match_count = sum(1 for row in data if NETWORK_LABEL[row[2]] in values)

        if match_count != _last_network_count[goip]:
            if operator == ">" and match_count > count_threshold:
                notify_user(f"{goip} network {values} is greater than {count_threshold}: {match_count}/{len(data)}", goip, -1)
            elif operator == "<" and match_count < count_threshold:
                notify_user(f"{goip} network {values} is less than {count_threshold}: {match_count}/{len(data)}", goip, -1)
            _last_network_count[goip] = match_count

    # === SIGNAL ===
    signal_config = settings.get("signal", {})
    if signal_config.get("enabled", False):
        bar_conf = signal_config.get("bar", {})
        custom_conf = signal_config.get("custom", {})
        total_ports = len(data)

        # Bar mode
        if bar_conf.get("enabled", False):
            bar_values = bar_conf.get("values", [])
            for bar in bar_values:
                count = sum(1 for row in data if signal_to_level(str(row[1])) == bar)
                op = custom_conf.get("operator", ">")
                count_thresh = custom_conf.get("count", 0)
                key = ("bar", bar, count)

                if key != _last_signal_alert[goip]:
                    if op == ">" and count > count_thresh:
                        notify_user(f"{goip} bar {bar} signal > {count_thresh}: {count}/{total_ports}", goip, -1)
                        _last_signal_alert[goip] = key
                    elif op == "<" and count < count_thresh:
                        notify_user(f"{goip} bar {bar} signal < {count_thresh}: {count}/{total_ports}", goip, -1)
                        _last_signal_alert[goip] = key

        # Custom signal mode
        if custom_conf.get("enabled", False):
            min_val = custom_conf.get("min", 0)
            max_val = custom_conf.get("max", 0)
            op = custom_conf.get("operator", ">")
            count_thresh = custom_conf.get("count", 0)
            match_count = 0
            for row in data:
                try:
                    strength = int(row[1])
                    if min_val <= strength <= max_val:
                        match_count += 1
                except:
                    continue
            key = ("custom", min_val, max_val, match_count)
            if key != _last_signal_alert[goip]:
                if op == ">" and match_count > count_thresh:
                    notify_user(f"{goip} Signal {min_val}-{max_val} > {count_thresh}: {match_count}/{total_ports}", goip, -1)
                    _last_signal_alert[goip] = key
                elif op == "<" and match_count < count_thresh:
                    notify_user(f"{goip} Signal {min_val}-{max_val} < {count_thresh}: {match_count}/{total_ports}", goip, -1)
                    _last_signal_alert[goip] = key

def load_notification_settings():
    global _notification_settings
    try:
        with open(NOTIFICATION_FILE, "r") as f:
            _notification_settings = json.load(f)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Notification settings reloaded.")
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] Failed to load notification settings: {e}")
        _notification_settings = {}

def update_notification_settings_from_ui():
    # Call this after saving settings in the UI
    load_notification_settings()
