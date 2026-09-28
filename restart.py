from utils import *
from app.models.goip_device import GoipDevice

def launch_restart_tabs(device_repository, goip_num):
    if goip_num <= 0:
        return

    devices = device_repository.load_devices()

    if goip_num > len(devices):
        return

    device = devices[goip_num - 1]

    try:
        session = login_goip(device)
        restart_goip(device, session)

    except Exception:
        pass

    print(
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
        f"restarted: GOIP {goip_num}"
    )

def restart_goip(device: GoipDevice, session):
    ip = device.ip_address
    reboot_url = f"http://{ip}/save_reboot_en.html"

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": f"http://{ip}",
        "Referer": f"http://{ip}/save_reboot_en.html",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/138.0.0.0 Safari/537.36",
    }

    payload = {
        "command": "reboot"
    }

    try:
        resp = session.post(
            reboot_url,
            headers=headers,
            data=payload,
            timeout=10
        )

        if resp.status_code == 200:
            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                f"✔️ {device.goip} Restart command sent ({ip})."
            )
            return True

        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"❌ {device.goip} Restart failed ({ip}) - "
            f"HTTP {resp.status_code}"
        )
        return False

    except requests.RequestException as e:
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"❌ {device.goip} Restart request error ({ip}): {e}"
        )
        return False

