import socket

from ping3 import ping


def is_port_online(ip: str, port: int, timeout: float = 2) -> bool:
    """Return whether a TCP connection to the specified port succeeds."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
            connection.settimeout(timeout)
            connection.connect((ip, port))
        return True
    except (OSError, ValueError):
        return False


def ping_ip(ip: str, timeout: float = 2) -> bool:
    """Return whether the host responds to a ping request."""
    try:
        response = ping(ip, timeout=timeout)
        return response is not None and response is not False
    except Exception:
        return False


def is_port_open(ip: str) -> bool:
    """Check the usual GOIP service ports, then fall back to ping."""
    if not ip:
        return False

    if is_port_online(ip, 5060):
        return True

    if is_port_online(ip, 80):
        return True

    if ping_ip(ip):
        return True

    return False
