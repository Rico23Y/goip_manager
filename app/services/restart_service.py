"""Service functions for restarting GOIP devices."""

import time

import requests

from app.goip.client import login_goip
from app.models.goip_device import GoipDevice


def launch_restart_tabs(device_repository, goip_num: int) -> None:
    """Restart the GOIP device identified by its one-based number."""
    if goip_num <= 0:
        return

    session = None

    try:
        devices = device_repository.load_devices()

        if goip_num > len(devices):
            return

        device = devices[goip_num - 1]

        session = login_goip(device)
        if session is None:
            return

        restart_goip(device, session)

    except Exception as error:
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"GOIP {goip_num} restart error: {error}"
        )

    finally:
        if session is not None:
            try:
                session.close()
            except Exception as error:
                print(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                    f"GOIP {goip_num} session cleanup error: {error}"
                )


def restart_goip(
    device: GoipDevice,
    session: requests.Session,
) -> bool:
    """Send a reboot command to a GOIP device using an authenticated session."""
    ip = device.ip_address
    reboot_url = f"http://{ip}/save_reboot_en.html"

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": f"http://{ip}",
        "Referer": reboot_url,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/138.0.0.0 Safari/537.36"
        ),
    }
    payload = {"command": "reboot"}

    try:
        response = session.post(
            reboot_url,
            headers=headers,
            data=payload,
            timeout=10,
        )
    except requests.RequestException as error:
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"GOIP {device.goip} restart request error ({ip}): {error}"
        )
        return False

    if response.status_code == 200:
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"GOIP {device.goip} restart command sent ({ip})."
        )
        return True

    print(
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
        f"GOIP {device.goip} restart failed ({ip}) - "
        f"HTTP {response.status_code}"
    )
    return False
