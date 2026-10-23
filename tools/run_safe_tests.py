
"""Run unit tests with Python-level network guards enabled.

Run from the repository root:
    python tools/run_safe_tests.py

This is defense in depth, not a replacement for an OS-level firewall.
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile
import unittest
from pathlib import Path

NETWORK_ATTEMPTS: list[str] = []

# Redirect common per-user configuration paths before importing project code.
TEST_ROOT = Path(tempfile.mkdtemp(prefix="goip-manager-tests-"))
for variable in ("APPDATA", "LOCALAPPDATA", "HOME", "USERPROFILE"):
    os.environ[variable] = str(TEST_ROOT / variable.lower())


def block_network(operation: str):
    def blocked(*args, **kwargs):
        NETWORK_ATTEMPTS.append(operation)
        raise RuntimeError(
            f"Blocked network operation during tests: {operation}. "
            "Mock device/network access in the test."
        )
    return blocked


# Block common Python socket entry points before importing tests.
socket.socket.connect = block_network("socket.socket.connect")
socket.socket.connect_ex = block_network("socket.socket.connect_ex")
socket.socket.sendto = block_network("socket.socket.sendto")
if hasattr(socket.socket, "sendmsg"):
    socket.socket.sendmsg = block_network("socket.socket.sendmsg")
socket.create_connection = block_network("socket.create_connection")


def install_http_guards() -> None:
    """Block requests HTTP calls and ping3 before test modules use them."""
    try:
        import requests
    except ImportError:
        requests = None

    if requests is not None:
        requests.sessions.Session.request = block_network(
            "requests.Session.request"
        )

    try:
        import ping3
    except ImportError:
        ping3 = None

    if ping3 is not None:
        ping3.ping = block_network("ping3.ping")


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    os.chdir(repo_root)

    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
        os.chdir(repo_root)

    install_http_guards()

    print(f"Repository: {repo_root}")
    print(f"Temporary configuration root: {TEST_ROOT}")
    print("Python socket, requests HTTP, and ping3 calls are guarded.\n")


    loader = unittest.TestLoader()
    suite = loader.discover(
        start_dir=str(repo_root / "tests"),
        pattern="test*.py",
    )

    result = unittest.TextTestRunner(verbosity=2).run(suite)

    if NETWORK_ATTEMPTS:
        print("\nSAFETY FAILURE: blocked network operations were attempted:")
        for operation in NETWORK_ATTEMPTS:
            print(f" - {operation}")
        return 2

    if not result.wasSuccessful():
        return 1

    print("\nPASS: tests passed without triggering the installed network guards.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
