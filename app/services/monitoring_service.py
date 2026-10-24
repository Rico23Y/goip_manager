"""Manage background monitoring of GOIP devices."""

import copy
import threading
import time
from collections.abc import Callable
from typing import Any

from app.goip.client import login_goip
from app.goip.connection import is_port_open
from app.models.goip_device import GoipDevice
from app.repositories.device_repository import DeviceRepository
from app.services.port_status_service import scrape_goip_data


class MonitoringService:
    """Manage GOIP monitoring threads and their reported state."""

    def __init__(
        self,
        check_notifications: Callable[[str, list], None],
    ) -> None:
        self._check_notifications = check_notifications
        self._goip_state: dict[str, dict[str, Any]] = {}
        self._monitor_threads: dict[str, threading.Thread] = {}
        self._stop_events: dict[str, threading.Event] = {}
        self._init_lock = threading.Lock()
        self._running = False

    @property
    def running(self) -> bool:
        """Return whether any monitoring thread is still running."""
        return self._running

    def update_state(
        self,
        goip: str,
        *,
        status: Any = None,
        is_running: bool | None = None,
        description: str | None = None,
    ) -> None:
        """Update the latest state reported for a GOIP device."""
        entry = self._goip_state.get(
            goip,
            {
                "status": [],
                "isRunning": False,
                "description": "Not started",
            },
        )

        if status is not None:
            entry["status"] = status
        if is_running is not None:
            entry["isRunning"] = bool(is_running)
        if description is not None:
            entry["description"] = str(description)

        self._goip_state[goip] = entry

    def monitor_scraper_loop(
        self,
        device: GoipDevice,
        stop_event: threading.Event,
    ) -> None:
        """Monitor one device, reconnecting after failures."""
        retry_delays = [60, 300, 600]
        max_attempts = len(retry_delays)
        attempt = 0

        ip = device.ip_address
        goip = device.goip
        session = None
        is_online = True

        try:
            while not stop_event.is_set():
                try:
                    if session is None:
                        if not is_port_open(ip):
                            self.update_state(
                                goip,
                                is_running=False,
                                description="Offline",
                            )

                            if is_online:
                                print(
                                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}]"
                                    " Is ONLINE"
                                )
                                ip_sms = f" ({ip})" if ip else ""
                                offline_sms = (
                                    "offline" if ip else "Empty IP address"
                                )
                                print(
                                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                                    f"🚫 {goip}{ip_sms} is {offline_sms} — "
                                    "skipping."
                                )

                            is_online = False
                            if stop_event.wait(10):
                                return
                            continue

                        is_online = True
                        session = login_goip(device)

                        if session is None:
                            self.update_state(
                                goip,
                                is_running=False,
                                description="Initial login failed",
                            )
                            raise Exception("Initial login failed")

                    data = scrape_goip_data(device, session)

                    if data is None:
                        raise Exception("scrape_goip_data() returned None")

                    self._check_notifications(goip, data)
                    self.update_state(
                        goip,
                        status=data,
                        is_running=True,
                        description="Running",
                    )
                    attempt = 0

                    if stop_event.wait(1):
                        return

                except Exception as error:
                    print(
                        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                        f"({ip}) Error: {error}"
                    )
                    attempt += 1

                    if session is not None:
                        try:
                            session.close()
                        except Exception as close_error:
                            print(
                                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                                f"({ip}) Failed to close session after error: {close_error}"
                            )
                        finally:
                            session = None

                    if attempt >= max_attempts:
                        failed_message = (
                            f"({ip}) ❌ Marked as failed after "
                            f"{attempt} attempts."
                        )
                        print(
                            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                            f"{failed_message}"
                        )
                        self.update_state(
                            goip,
                            is_running=False,
                            description=failed_message,
                        )
                        return

                    delay = retry_delays[
                        min(attempt - 1, max_attempts - 1)
                    ]
                    message = (
                        f"({ip}) Retrying in {delay} sec... "
                        f"(Attempt {attempt}/{max_attempts})"
                    )
                    self.update_state(
                        goip,
                        is_running=False,
                        description=message,
                    )
                    print(
                        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
                    )

                    for _ in range(delay):
                        if stop_event.is_set():
                            return
                        time.sleep(1)

        finally:
            if session is not None:
                try:
                    session.close()
                except Exception as error:
                    print(
                        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                        f"({ip}) Failed to close session: {error}"
                    )

    def start(
        self,
        device_repository: DeviceRepository,
        will_run: bool = True,
        load_settings: Callable[[], None] | None = None,
    ) -> None:
        """Start enabled device monitors or request active monitors to stop."""
        if will_run:
            with self._init_lock:
                if self._running:
                    return

                try:
                    devices = device_repository.load_devices()
                except Exception as error:
                    print(
                        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                        "[ERROR] Failed to load devices:",
                        error,
                    )
                    return

                if load_settings is not None:
                    load_settings()

                for device in devices:
                    goip = device.goip

                    if not device.enabled:
                        continue

                    existing = self._monitor_threads.get(goip)
                    if existing is not None and existing.is_alive():
                        continue

                    stop_event = threading.Event()
                    self._stop_events[goip] = stop_event

                    thread = threading.Thread(
                        target=self.monitor_scraper_loop,
                        args=(device, stop_event),
                        daemon=True,
                        name=f"mon-{goip}",
                    )
                    self._monitor_threads[goip] = thread
                    thread.start()

                self._running = True
                print(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                    "[INFO] GoIP monitoring started."
                )
            return

        with self._init_lock:
            threads = list(self._monitor_threads.values())

            for stop_event in self._stop_events.values():
                stop_event.set()

        deadline = time.monotonic() + 5

        for thread in threads:
            if thread is not threading.current_thread():
                remaining = max(0, deadline - time.monotonic())
                thread.join(timeout=remaining)

        with self._init_lock:
            still_running = [
                thread.name
                for thread in self._monitor_threads.values()
                if thread.is_alive()
            ]
            self._running = bool(still_running)

        if still_running:
            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                "[WARNING] Some GOIP monitoring threads are still stopping: "
                f"{', '.join(still_running)}"
            )
        else:
            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                "[INFO] GoIP monitoring stopped."
            )

    def get_status_data(
        self,
        device_repository: DeviceRepository,
    ) -> dict[str, dict[str, Any]]:
        """Return a copy of the current monitoring state."""
        devices = device_repository.load_devices()
        start_time = time.time()

        while time.time() - start_time < 10:
            if len(self._goip_state) == len(devices):
                break
            time.sleep(0.05)

        return copy.deepcopy(self._goip_state)