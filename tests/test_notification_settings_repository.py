
import json
import tempfile
import unittest
from pathlib import Path

from app.repositories.notification_settings_repository import (
    NotificationSettingsRepository,
)


class TestNotificationSettingsRepository(unittest.TestCase):

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.config_file = (
            Path(self.temp_dir.name) / "notification_setting.json"
        )
        self.repository = NotificationSettingsRepository(
            self.config_file
        )

    def test_load_settings_when_file_does_not_exist(self) -> None:
        self.assertEqual(self.repository.load_settings(), {})

    def test_save_and_load_settings(self) -> None:
        settings = {
            "enabled": True,
            "sim_status": {
                "enabled": True,
                "values": ["Ready", "Busy"],
            },
            "network_type": {
                "enabled": False,
                "values": [],
                "operator": ">",
                "count": 2,
            },
        }

        self.repository.save_settings(settings)

        self.assertEqual(self.repository.load_settings(), settings)

    def test_load_settings_with_invalid_json(self) -> None:
        self.config_file.write_text(
            "{invalid json",
            encoding="utf-8",
        )

        self.assertEqual(self.repository.load_settings(), {})

    def test_load_settings_with_non_dictionary_json(self) -> None:
        self.config_file.write_text(
            json.dumps(["invalid", "structure"]),
            encoding="utf-8",
        )

        self.assertEqual(self.repository.load_settings(), {})


if __name__ == "__main__":
    unittest.main()
