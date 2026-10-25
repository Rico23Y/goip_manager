import json
import tempfile
import unittest
from pathlib import Path

from app.repositories.restart_settings_repository import (
    RestartSettingsRepository,
)


class TestRestartSettingsRepository(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.config_file = Path(self.temp_dir.name) / "restart_setting.json"
        self.repository = RestartSettingsRepository(self.config_file)

    def test_load_settings_when_file_does_not_exist(self):
        self.assertEqual(self.repository.load_settings(), {})

    def test_save_and_load_settings(self):
        settings = {
            "timezone": "Asia/Manila",
            "custom_date": False,
            "main_devices": [1, 2],
            "blocks": [],
            "auto_start": True,
        }

        self.repository.save_settings(settings)

        self.assertEqual(self.repository.load_settings(), settings)

    def test_load_settings_with_invalid_json(self):
        self.config_file.write_text("{invalid", encoding="utf-8")

        self.assertEqual(self.repository.load_settings(), {})

    def test_load_settings_with_non_dictionary_json(self):
        self.config_file.write_text(
            json.dumps(["unexpected", "list"]),
            encoding="utf-8",
        )

        self.assertEqual(self.repository.load_settings(), {})


if __name__ == "__main__":
    unittest.main()
