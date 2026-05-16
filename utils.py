from requests import RequestException
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException, \
    StaleElementReferenceException, UnexpectedAlertPresentException, NoAlertPresentException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
import os, time, json, csv, sys, re, math, socket, subprocess, threading, requests, hashlib, operator, platform
from subprocess import DEVNULL
from selenium import webdriver
from plyer import notification
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtWidgets import QMessageBox
from PySide6.QtGui import QIcon
import requests, re, hashlib, time
from PySide6.QtCore import QObject, Signal
from ping3 import ping

def get_appdata_path(filename):
    appdata = os.getenv("APPDATA", os.path.expanduser("~"))
    base_dir = os.path.join(appdata, "GoIP.Manager")
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, filename)

def resource_path(*relative_path: str) -> str:
    """
    Get absolute path to resource.
    Works for dev (PyCharm) and for PyInstaller frozen exe.
    """
    if getattr(sys, 'frozen', False):  # running as .exe
        base_path = sys._MEIPASS
    else:  # running in PyCharm / Python
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, *relative_path)

class GoipSignals(QObject):
    wrongPassword = Signal(dict)  # emits the device info when login fails

signals = GoipSignals()


__all__ = [
    # Selenium
    'webdriver', 'By', 'Options', 'Service',
    'WebDriverWait', 'EC',
    'TimeoutException', 'NoSuchElementException',
    'WebDriverException', 'StaleElementReferenceException',

    # Standard libraries
    'operator', 'notification', 'DEVNULL', 'socket',
    'math', 'time', 'csv', 'sys', 'os', 're', 'threading',
    'requests',

    # Functions
    'viewer_options', 'open_viewer_tabs', 'is_port_open',
    'login_to_device', 'login_goip', 'reload_devices',

    # Constants / Mappings
    'status_map', 'PAGE_LOAD_TIMEOUT', 'ELEMENT_WAIT_TIME',
    'KEEPALIVE_INTERVAL', 'signal_to_level',
    'NETWORK_LABEL'
]

# --- Config ---        # Previous value
PAGE_LOAD_TIMEOUT = 30  # 5
ELEMENT_WAIT_TIME = 30  # 0.6
KEEPALIVE_INTERVAL = 2  # 2

NETWORK_LABEL = ["NA", "", "2G", "3G", "4G", "5G"]

CONFIG_FILE = get_appdata_path("devices.json")
def reload_devices():
    try:
        with open(CONFIG_FILE, "r") as f:
            devices = json.load(f)
    except FileNotFoundError:
        devices = []
        print(f"❌ {CONFIG_FILE} not found. Please ensure it is in the same directory or set the full path.")
    return devices


# Status mapping
status_map = {
    0: "No Card Detected",
    1: "Card Detected",
    2: "Registering Card",
    3: "Register OK",
    4: "Calling",
    5: "No Balance",
    6: "Register Failed",
    7: "Locked",
    8: "Locked By Operator",
    9: "SIM Problem",
    10: "Locked",
    11: "Card Inserted",
    12: "Locked By User",
    13: "Inter-Calling",
    14: "Inter-Calling Holding",
    15: "Access Mobile Network",
    16: "Response Timeout",
    99: "Module Problem"
}

# For signal bar conversion
def signal_to_level(signal_str):
    if signal_str != '':
        signal = int(signal_str)
        if signal <= 4 or signal > 31:
            return 0
        elif signal <= 8:
            return 1
        elif signal <= 13:
            return 2
        elif signal <= 18:
            return 3
        elif signal <= 24:
            return 4
        else:
            return 5
    else:
        return -1



# Checks the Edge driver
try:
    service = Service(os.path.join(get_appdata_path(""), "msedgedriver.exe"), stdout=DEVNULL, stderr=DEVNULL)
except FileNotFoundError:
    print("❌ msedgedriver.exe not found. Please ensure it is in the same directory or set the full path.")
    exit()

# --- Edge Options ---
def viewer_options(windows_size = "--window-size=1500,1100", headless = False):
    options = Options()
    options.use_chromium = True
    if headless:
        options.add_argument("--headless")
    options.add_argument(windows_size)
    options.add_argument("--force-device-scale-factor=0.9")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-features=EdgeLLM")
    options.add_argument("--log-level=3")

    driver = webdriver.Edge(service=service, options=options)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    driver.get("about:blank")
    return driver, driver.current_window_handle

# Example
# viewer_driver, viewer_main_window = viewer_options()

import socket
from ping3 import ping

def is_port_online(ip, port, timeout=2):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        s.close()
        return True
    except:
        return False

def ping_ip(ip, timeout=2):
    """Pings an IP using native Python. Returns True if responsive."""
    try:
        # ping3 takes timeout in seconds. Returns delay in seconds or None/False.
        response = ping(ip, timeout=timeout)
        return response is not None and response is not False
    except Exception:
        return False

def is_port_open(ip):
    if not ip:
        return False
        
    # Reordered logic: Try fast socket checks first, fallback to ping last
    if is_port_online(ip, 5060):
        return True
    if is_port_online(ip, 80):
        return True
    if ping_ip(ip):
        return True
        
    return False


def login_to_device(destination_page, message_type, driver, device, post_login_action=None, parent=None):
    if not is_port_open(device["ip"]):
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🚫 {device['goip']} ({device['ip']}) is offline — skipping.")

        ip_sms = f" ({device['ip']})" if device['ip'] != "" else ""
        offline_sms = 'offline' if device['ip'] != "" else 'Empty IP address'
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🚫 {device['goip']}{ip_sms} is {offline_sms} — skipping.")
        return False

    wait = WebDriverWait(driver, ELEMENT_WAIT_TIME)

    try:
        # 1️⃣ Open login page
        driver.get(f"http://{device['ip']}")
        wait.until(EC.presence_of_element_located((By.ID, "ID_LoginForm")))

        # 2️⃣ Fill login form via JS
        driver.execute_script(f"""
            document.getElementById("accountID").value = {json.dumps(device["username"])};
            document.getElementById("passwordID").value = {json.dumps(device["password"])};
            submitData();
        """)

        # 3️⃣ Race: either login success or alert
        try:
            result, alert_text = wait_for_login_or_alert(driver, timeout=5)

            if result == "alert":
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ Alert detected: {alert_text}")
                driver.switch_to.alert.dismiss()
                show_login_error_popup(
                    f"[{device['ip']}] {alert_text}\n\n⚠️ Multiple failed attempts may result in device lockdown.\n\n"
                    f"Please log in manually in the browser to confirm the password.",
                    parent
                )
                return False

            elif result == "url":
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ✔️ {device['goip']} Login successful ({device['ip']})")

        except TimeoutException:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ⏳ {device['goip']} Timeout waiting for login or alert ({device['ip']})")
            return False

        # 4️⃣ Proceed to target page
        driver.get(f"http://{device['ip']}/{destination_page}")

        # Optional post-login action
        if post_login_action:
            post_login_action(driver, wait)

        # 5️⃣ Inject keep-alive script
        driver.execute_script(f"""
            document.title = '{device["goip"]}';
            if (!window.keepAliveInterval) {{
                window.keepAliveInterval = setInterval(function() {{
                    fetch('/left_bar.gif')
                        .then(r => console.log('Keep-alive ping: ' + r.status + ' at ' + new Date().toLocaleTimeString()))
                        .catch(e => console.error('Keep-alive failed'));
                }}, {KEEPALIVE_INTERVAL * 60000});
            }}
        """)

        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ✔️ {device['goip']} {message_type} Successfully ({device['ip']})")
        return True

    except TimeoutException:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ⏳ {device['goip']} Timeout loading ({device['ip']})")
        return False

    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ❌ {device['goip']} Unexpected error at ({device['ip']}): {e}")
        return False


def wait_for_login_or_alert(driver, timeout=5):
    """
    Waits for either a successful login (url contains main_en.html)
    or an alert popup (wrong login). Returns 'url' or 'alert'.
    """
    end_time = time.time() + timeout
    while True:
        try:
            # ✅ Check alert first
            alert = driver.switch_to.alert
            return "alert", alert.text
        except:
            pass

        try:
            # ✅ Check if login page loaded
            if "main_en.html" in driver.current_url:
                return "url", None
        except:
            pass

        if time.time() > end_time:
            raise TimeoutException("Neither login nor alert detected")

        time.sleep(0.1)  # small poll interval

def show_login_error_popup(message, parent=None):
    def _show():
        # 🔔 System tray notification
        notification.notify(
            title="GOIP Login Error",
            message=message,
            app_icon=resource_path("icons", "notification.ico") if os.path.exists(
                resource_path("icons", "notification.ico")) else None,
            timeout=5
        )

        # ⚠️ GUI popup with custom icon
        msg = QMessageBox(parent)
        msg.setWindowTitle("GOIP Login Error")

        # set both window icon (title bar) and content icon
        icon_path = resource_path("icons", "notification.png")
        if os.path.exists(icon_path):
            msg.setWindowIcon(QIcon(icon_path))  # 👈 title bar icon
            msg.setIconPixmap(QIcon(icon_path).pixmap(48, 48))  # 👈 content icon

        msg.setText(message)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.setDefaultButton(QMessageBox.Ok)
        msg.setWindowFlags(msg.windowFlags() | Qt.WindowStaysOnTopHint)
        msg.exec()

    QTimer.singleShot(0, _show)

def md5_hex(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()

def get_auth_cookie_value(session: requests.Session):
    for c in session.cookies:
        if c.name.startswith("auth_"):
            return c.value
    return None

def parse_login_status(html: str):
    """Returns (status, remaining)"""
    m = re.search(r'id=["\']ID_LoginStatus["\'][^>]*value=["\']([^"\']+)["\']', html, re.I)
    status = m.group(1) if m else None

    r = re.search(r'login_remaining_count\s*=\s*["\']?(-?\d+)["\']?', html, re.I)
    remaining = int(r.group(1)) if r else None

    return status, remaining

def login_goip(device):
    """
    Attempts login and returns session or None.
    On wrong password: emits signals.wrongPassword and returns None.
    """
    ip = device["ip"]
    user = device["username"]
    pwd = device["password"]
    base = f"http://{ip}"

    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})

    try:
        s.get(f"{base}/login_en.html", timeout=5)
    except requests.RequestException as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{ip}] 🚫 Cannot reach device: {e}")
        return None

    nonce = get_auth_cookie_value(s)
    if not nonce:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{ip}] ⚠️ No auth_* cookie found.")
        return None

    digest = md5_hex(f"{user}:{pwd}:{nonce}")
    encoded = f"{user}:{digest}"
    payload = {"encoded": encoded, "nonce": nonce}
    headers = {"Origin": base, "Referer": f"{base}/login_en.html"}

    try:
        r2 = s.post(f"{base}/login_en.html", data=payload, headers=headers, timeout=5)
        html = r2.text or ""
    except requests.RequestException as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{ip}] 🚫 POST failed: {e}")
        return None

    status, remaining = parse_login_status(html)

    if status == "0":
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ✅ GOIP {device.get('goip','?')} ({ip}) Login successful.")
        return s

    # Wrong credentials detection
    text_lower = html.lower()
    if ("account or password is wrong" in text_lower) or (remaining is not None and remaining >= 0) or "login" in r2.url.lower():
        msg = f"Wrong credentials for {ip}"
        if remaining is not None:
            msg += f" (remaining attempts {remaining})"
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ❌ {msg}")
        signals.wrongPassword.emit(device)
        return None

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{ip}] ⚠️ Ambiguous login response")
    return None


def open_viewer_tabs(destination_page, message_type, viewer_driver, post_login_action=None):
    devices = reload_devices()
    for device in devices:
        try:
            # Always open new tab
            viewer_driver.execute_script("window.open('about:blank', '_blank');")
            viewer_driver.switch_to.window(viewer_driver.window_handles[-1])
            time.sleep(0.1)

            # Let login_to_device decide if it should skip
            success = login_to_device(destination_page, message_type, viewer_driver, device, post_login_action=post_login_action)
            if not success:
                viewer_driver.close()  # optional: close tab if login failed
                viewer_driver.switch_to.window(viewer_driver.window_handles[0])
        except Exception as e:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ❌ {device['goip']} Error with ({device['ip']}): {e}")

def launch_home_tabs(goip_window=0):
    """
    Optional function to open viewer-only tabs (non-scraping UI).
    Can run multiple or single window
    """
    devices = reload_devices()
    viewer_driver, viewer_main_window = viewer_options()

    if goip_window == 0:
        try:
            open_viewer_tabs("main_en.html", "Port Status Opened",
                             viewer_driver)

            viewer_driver.switch_to.window(viewer_main_window)
            viewer_driver.close()
        except Exception:
            pass

    if goip_window > 0:
        try:

            success = login_to_device("main_en.html", "Home Page Opened",
                            viewer_driver, devices[goip_window - 1])
            if not success:
                viewer_driver.close()  # optional: close tab if login failed
                viewer_driver.switch_to.window(viewer_driver.window_handles[0])

        except Exception:
            pass




