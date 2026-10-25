import json
import os
from pathlib import Path
from typing import Any


class RestartSettingsRepository:
    """Handles persistent storage of restart scheduler settings."""

    def __init__(
        self,
        config_file: str | Path,
    ) -> None:
        self.config_file = Path(config_file)
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

    def load_settings(self) -> dict[str, Any]:
        """Load restart settings, returning an empty dictionary if invalid."""
        if not self.config_file.exists():
            return {}

        try:
            with self.config_file.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (json.JSONDecodeError, OSError):
            return {}

        if not isinstance(data, dict):
            return {}

        return data

    def save_settings(self, settings: dict[str, Any]) -> None:
        """Save restart settings to the configuration file."""
        with self.config_file.open("w", encoding="utf-8") as file:
            json.dump(settings, file, indent=4)
            file.flush()
            os.fsync(file.fileno())
