
import json
import os
import time
from subprocess import DEVNULL
from typing import Callable

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app.core.config import get_appdata_path
from app.goip.connection import is_port_open
from app.models.goip_device import GoipDevice
from app.ui.login_dialogs import show_login_error_popup


PAGE_LOAD_TIMEOUT = 30
ELEMENT_WAIT_TIME = 30
KEEPALIVE_INTERVAL = 2

try:
    service = Service(
        os.path.join(get_appdata_path(""), "msedgedriver.exe"),
        stdout=DEVNULL,
        stderr=DEVNULL,
    )
except FileNotFoundError:
    print(
        "❌ msedgedriver.exe not found. Please ensure it is in the "
        "same directory or set the full path."
    )
    raise


def viewer_options(
    windows_size: str = "--window-size=1500,1100",
    headless: bool = False,
):
    """Create an Edge browser for viewing GOIP devices."""
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


def wait_for_login_or_alert(driver, timeout: float = 5):
    """Wait for successful login navigation or a browser alert."""
    end_time = time.time() + timeout

    while True:
        try:
            alert = driver.switch_to.alert
            return "alert", alert.text
        except Exception:
            pass

        try:
            if "main_en.html" in driver.current_url:
                return "url", None
        except Exception:
            pass

        if time.time() > end_time:
            raise TimeoutException("Neither login nor alert detected")

        time.sleep(0.1)


def login_to_device(
    destination_page,
    message_type: str,
    driver,
    device: GoipDevice,
    post_login_action: Callable | None = None,
    parent=None,
) -> bool:
    """Log in through the GOIP web interface and open the requested page."""
    if not is_port_open(device.ip_address):
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"🚫 {device.goip} ({device.ip_address}) is offline — skipping."
        )
        return False

    wait = WebDriverWait(driver, ELEMENT_WAIT_TIME)

    try:
        driver.get(f"http://{device.ip_address}")
        wait.until(EC.presence_of_element_located((By.ID, "ID_LoginForm")))

        driver.execute_script(
            f"""
            document.getElementById("accountID").value =
                {json.dumps(device.username)};
            document.getElementById("passwordID").value =
                {json.dumps(device.password)};
            submitData();
            """
        )

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
                    "⚠️ Multiple failed attempts may result in device "
                    "lockdown.\n\n"
                    "Please log in manually in the browser to confirm "
                    "the password.",
                    parent,
                )
                return False

            if result == "url":
                print(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                    f"✔️ {device.goip} Login successful "
                    f"({device.ip_address})"
                )

        except TimeoutException:
            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                f"⏳ {device.goip} Timeout waiting for login or alert "
                f"({device.ip_address})"
            )
            return False

        driver.get(f"http://{device.ip_address}/{destination_page}")

        if post_login_action:
            post_login_action(driver, wait)

        driver.execute_script(
            f"""
            document.title = {json.dumps(device.goip)};
            if (!window.keepAliveInterval) {{
                window.keepAliveInterval = setInterval(function() {{
                    fetch('/left_bar.gif')
                        .then(r => console.log(
                            'Keep-alive ping: ' + r.status + ' at ' +
                            new Date().toLocaleTimeString()
                        ))
                        .catch(e => console.error('Keep-alive failed'));
                }}, {KEEPALIVE_INTERVAL * 60000});
            }}
            """
        )

        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"✔️ {device.goip} {message_type} Successfully "
            f"({device.ip_address})"
        )
        return True

    except TimeoutException:
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"⏳ {device.goip} Timeout loading ({device.ip_address})"
        )
        return False

    except Exception as error:
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"❌ {device.goip} Unexpected error at "
            f"({device.ip_address}): {error}"
        )
        return False


def open_viewer_tabs(
    destination_page,
    message_type: str,
    viewer_driver,
    device_repository,
    post_login_action: Callable | None = None,
) -> None:
    """Open a browser tab for each configured GOIP device."""
    devices = device_repository.load_devices()

    for device in devices:
        try:
            viewer_driver.execute_script(
                "window.open('about:blank', '_blank');"
            )
            viewer_driver.switch_to.window(viewer_driver.window_handles[-1])
            time.sleep(0.1)

            success = login_to_device(
                destination_page,
                message_type,
                viewer_driver,
                device,
                post_login_action=post_login_action,
            )

            if not success:
                viewer_driver.close()
                viewer_driver.switch_to.window(viewer_driver.window_handles[0])

        except Exception as error:
            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                f"❌ {device.goip} Error with ({device.ip_address}): {error}"
            )


def launch_home_tabs(device_repository, goip_window: int = 0) -> None:
    """Open home pages for all devices or one selected device."""
    devices = device_repository.load_devices()
    viewer_driver, viewer_main_window = viewer_options()

    if goip_window == 0:
        try:
            open_viewer_tabs(
                "main_en.html",
                "Home Page Opened",
                viewer_driver,
                device_repository,
            )
            viewer_driver.switch_to.window(viewer_main_window)
            viewer_driver.close()

        except Exception as error:
            print(f"Error opening home tabs: {error}")

    elif goip_window > 0:
        try:
            success = login_to_device(
                "main_en.html",
                "Home Page Opened",
                viewer_driver,
                devices[goip_window - 1],
            )

            if not success:
                return

        except Exception as error:
            print(f"Error opening home page: {error}")
