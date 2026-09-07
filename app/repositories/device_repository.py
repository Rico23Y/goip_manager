import json
import os
from pathlib import Path

from app.models.goip_device import GoipDevice


class DeviceRepository:
    """Handles persistent storage of GOIP device configurations."""

    def __init__(self, config_file: str | Path | None = None) -> None:
        if config_file is None:
            appdata = os.getenv("APPDATA", os.path.expanduser("~"))
            config_file = Path(appdata) / "GoIP.Manager" / "devices.json"

        self.config_file = Path(config_file)
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

    def load_devices(self) -> list[GoipDevice]:
        """Load all GOIP devices from the configuration file."""

        if not self.config_file.exists():
            return []

        try:
            with self.config_file.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError:
            print(f"Invalid JSON in {self.config_file}")
            return []

        if not isinstance(data, list):
            return []

        return [
            GoipDevice.from_dict(device)
            for device in data
            if isinstance(device, dict)
        ]

    def save_devices(self, devices: list[GoipDevice]) -> None:
        """Save all GOIP devices to the configuration file."""

        data = []

        for index, device in enumerate(devices, start=1):
            device_data = device.to_dict()
            device_data["goip"] = f"GOIP {index}"
            data.append(device_data)

        with self.config_file.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)

            file.flush()
            os.fsync(file.fileno())