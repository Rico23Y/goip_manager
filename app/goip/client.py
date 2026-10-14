import hashlib
import re
import time

import requests

from app.models.goip_device import GoipDevice
from app.core.signals import signals


def md5_hex(value: str) -> str:
    """Return the MD5 hexadecimal digest of a string."""
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def get_auth_cookie_value(session: requests.Session) -> str | None:
    """Return the value of the first authentication cookie, if present."""
    for cookie in session.cookies:
        if cookie.name.startswith("auth_"):
            return cookie.value
    return None


def parse_login_status(html: str) -> tuple[str | None, int | None]:
    """Parse the login status and remaining login attempts from HTML."""
    status_match = re.search(
        r'id=["\']ID_LoginStatus["\'][^>]*value=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    status = status_match.group(1) if status_match else None

    remaining_match = re.search(
        r'login_remaining_count\s*=\s*["\']?(-?\d+)["\']?',
        html,
        re.IGNORECASE,
    )
    remaining = int(remaining_match.group(1)) if remaining_match else None

    return status, remaining


def login_goip(device: GoipDevice) -> requests.Session | None:
    """Log in to a GOIP device and return its session on success."""
    ip = device.ip_address
    username = device.username
    password = device.password
    base_url = f"http://{ip}"

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    try:
        session.get(f"{base_url}/login_en.html", timeout=5)
    except requests.RequestException as error:
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"[{ip}] Cannot reach device: {error}"
        )
        return None

    nonce = get_auth_cookie_value(session)
    if not nonce:
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"[{ip}] No auth_* cookie found."
        )
        return None

    digest = md5_hex(f"{username}:{password}:{nonce}")
    payload = {
        "encoded": f"{username}:{digest}",
        "nonce": nonce,
    }
    headers = {
        "Origin": base_url,
        "Referer": f"{base_url}/login_en.html",
    }

    try:
        response = session.post(
            f"{base_url}/login_en.html",
            data=payload,
            headers=headers,
            timeout=5,
        )
        html = response.text or ""
    except requests.RequestException as error:
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"[{ip}] POST failed: {error}"
        )
        return None

    status, remaining = parse_login_status(html)

    if status == "0":
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"GOIP {device.goip} ({ip}) Login successful."
        )
        return session


    text_lower = html.lower()

    if (
        "account or password is wrong" in text_lower
        or (remaining is not None and remaining >= 0)
        or "login" in response.url.lower()
    ):
        message = f"Wrong credentials for {ip}"
        if remaining is not None:
            message += f" (remaining attempts {remaining})"

        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"❌ {message}"
        )
        signals.wrongPassword.emit(device)
        return None

    print(
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
        f"[{ip}] ⚠ Ambiguous login response"
    )
    return None
