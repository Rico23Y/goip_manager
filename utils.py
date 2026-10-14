from requests import RequestException
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException, \
    StaleElementReferenceException, UnexpectedAlertPresentException, NoAlertPresentException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
import os, time, json, csv, sys, re, math, subprocess, threading, requests, operator, platform
from subprocess import DEVNULL
from selenium import webdriver
from plyer import notification
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtWidgets import QMessageBox
from PySide6.QtGui import QIcon
import requests, re, time

from app.models.goip_device import GoipDevice
from app.core.config import get_appdata_path
from app.utils.paths import resource_path
from app.goip.connection import is_port_online, ping_ip, is_port_open
from app.goip.client import (
    md5_hex,
    get_auth_cookie_value,
    parse_login_status,
    login_goip,
)
from app.core.signals import GoipSignals, signals

__all__ = [
    # Selenium
    'webdriver', 'By', 'Options', 'Service',
    'WebDriverWait', 'EC',
    'TimeoutException', 'NoSuchElementException',
    'WebDriverException', 'StaleElementReferenceException',

    # Standard libraries
    'operator', 'notification', 'DEVNULL',
    'math', 'time', 'csv', 'sys', 'os', 're', 'threading',
    'requests',

    # Functions
    'viewer_options', 'open_viewer_tabs', 'is_port_open',
    'login_to_device', 'login_goip',

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

def login_to_device(
    destination_page,
    message_type,
    driver,
    device: GoipDevice,
    post_login_action=None,
    parent=None
) -> bool:

    if not is_port_open(device.ip_address):
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"🚫 {device.goip} ({device.ip_address}) is offline — skipping."
        )
        return False

    wait = WebDriverWait(driver, ELEMENT_WAIT_TIME)

    try:
        # 1️⃣ Open login page
        driver.get(f"http://{device.ip_address}")
        wait.until(EC.presence_of_element_located((By.ID, "ID_LoginForm")))

        # 2️⃣ Fill login form via JS
        driver.execute_script(f"""
            document.getElementById("accountID").value = {json.dumps(device.username)};
            document.getElementById("passwordID").value = {json.dumps(device.password)};
            submitData();
        """)

        # 3️⃣ Race: either login success or alert
        try:
            result, alert_text = wait_for_login_or_alert(driver, timeout=5)

            if result == "alert":
                print(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                    f"⚠️ Alert detected: {alert_text}"
                )
                driver.switch_to.alert.dismiss()

                show_login_error_popup(
                    f"[{device.ip_address}] {alert_text}\n\n"
                    f"⚠️ Multiple failed attempts may result in device lockdown.\n\n"
                    f"Please log in manually in the browser to confirm the password.",
                    parent
                )
                return False

            elif result == "url":
                print(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                    f"✔️ {device.goip} Login successful ({device.ip_address})"
                )

        except TimeoutException:
            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                f"⏳ {device.goip} Timeout waiting for login or alert "
                f"({device.ip_address})"
            )
            return False

        # 4️⃣ Proceed to target page
        driver.get(f"http://{device.ip_address}/{destination_page}")

        # Optional post-login action
        if post_login_action:
            post_login_action(driver, wait)

        # 5️⃣ Inject keep-alive script
        driver.execute_script(f"""
            document.title = '{device.goip}';
            if (!window.keepAliveInterval) {{
                window.keepAliveInterval = setInterval(function() {{
                    fetch('/left_bar.gif')
                        .then(r => console.log('Keep-alive ping: ' + r.status + ' at ' + new Date().toLocaleTimeString()))
                        .catch(e => console.error('Keep-alive failed'));
                }}, {KEEPALIVE_INTERVAL * 60000});
            }}
        """)

        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"✔️ {device.goip} {message_type} Successfully "
            f"({device.ip_address})"
        )
        return True

    except TimeoutException:
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"⏳ {device.goip} Timeout loading "
            f"({device.ip_address})"
        )
        return False

    except Exception as e:
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"❌ {device.goip} Unexpected error at "
            f"({device.ip_address}): {e}"
        )
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

def open_viewer_tabs(
    destination_page,
    message_type,
    viewer_driver,
    device_repository,
    post_login_action=None
):
    devices = device_repository.load_devices()

    for device in devices:
        try:
            viewer_driver.execute_script(
                "window.open('about:blank', '_blank');"
            )
            viewer_driver.switch_to.window(
                viewer_driver.window_handles[-1]
            )
            time.sleep(0.1)

            success = login_to_device(
                destination_page,
                message_type,
                viewer_driver,
                device,
                post_login_action=post_login_action
            )

            if not success:
                viewer_driver.close()
                viewer_driver.switch_to.window(
                    viewer_driver.window_handles[0]
                )

        except Exception as e:
            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                f"❌ {device.goip} Error with ({device.ip_address}): {e}"
            )

def launch_home_tabs(device_repository, goip_window=0):
    """
    Optional function to open viewer-only tabs (non-scraping UI).
    Can run multiple or single window.
    """
    devices = device_repository.load_devices()
    viewer_driver, viewer_main_window = viewer_options()

    if goip_window == 0:
        try:
            open_viewer_tabs(
                "main_en.html",
                "Home Page Opened",
                viewer_driver,
                device_repository
            )

            viewer_driver.switch_to.window(viewer_main_window)
            viewer_driver.close()

        except Exception as e:
            print(f"Error opening home tabs: {e}")

    elif goip_window > 0:
        try:
            success = login_to_device(
                "main_en.html",
                "Home Page Opened",
                viewer_driver,
                devices[goip_window - 1]
            )

            if not success:
                return

        except Exception as e:
            print(f"Error opening home page: {e}")



