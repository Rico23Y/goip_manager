from utils import *

def launch_restart_tabs(goip_num):
    devices = reload_devices()
    device = devices[goip_num - 1]
    if goip_num > 0:
        try:
            session = login_goip(device)
            restart_goip(device, session)

        except Exception:
            pass

        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] restarted: GOIP {goip_num}")

def restart_goip(device, session):
    ip = device["ip"]
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
        resp = session.post(reboot_url, headers=headers, data=payload, timeout=10)
        if resp.status_code == 200:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ✔️ {device['goip']} Restart command sent ({device['ip']}).")
            return True
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ❌ {device['goip']} Restart failed ({device['ip']}) - HTTP {resp.status_code}")
            return False
    except requests.RequestException as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ❌ {device['goip']} Restart request error ({device['ip']}): {e}")
        return False

