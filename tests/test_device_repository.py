
import json
import tempfile
import unittest
from pathlib import Path

from app.models.goip_device import GoipDevice
from app.repositories.device_repository import DeviceRepository


class TestDeviceRepository(unittest.TestCase):

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.config_file = Path(self.temp_dir.name) / "devices.json"
        self.repository = DeviceRepository(self.config_file)

    def test_load_devices_when_file_does_not_exist(self) -> None:
        self.assertEqual(self.repository.load_devices(), [])

    def test_save_and_load_devices(self) -> None:
        devices = [
            GoipDevice(
                goip="Custom label",
                ip_address="192.168.0.101",
                username="admin",
                password="password1",
                enabled=True,
            ),
            GoipDevice(
                goip="Another label",
                ip_address="192.168.0.102",
                username="user",
                password="password2",
                enabled=False,
            ),
        ]

        self.repository.save_devices(devices)
        loaded_devices = self.repository.load_devices()

        self.assertEqual(len(loaded_devices), 2)

        self.assertEqual(loaded_devices[0].goip, "GOIP 1")
        self.assertEqual(
            loaded_devices[0].ip_address, "192.168.0.101"
        )
        self.assertEqual(loaded_devices[0].username, "admin")
        self.assertEqual(loaded_devices[0].password, "password1")
        self.assertIs(loaded_devices[0].enabled, True)

        self.assertEqual(loaded_devices[1].goip, "GOIP 2")
        self.assertEqual(
            loaded_devices[1].ip_address, "192.168.0.102"
        )
        self.assertEqual(loaded_devices[1].username, "user")
        self.assertEqual(loaded_devices[1].password, "password2")
        self.assertIs(loaded_devices[1].enabled, False)

    def test_load_devices_with_invalid_json(self) -> None:
        self.config_file.write_text("{invalid json", encoding="utf-8")

        self.assertEqual(self.repository.load_devices(), [])

    def test_load_devices_with_non_list_json(self) -> None:
        self.config_file.write_text(
            json.dumps({"ip": "192.168.0.101"}),
            encoding="utf-8",
        )

        self.assertEqual(self.repository.load_devices(), [])

    def test_load_devices_skips_non_dictionary_entries(self) -> None:
        self.config_file.write_text(
            json.dumps([
                {
                    "goip": "GOIP 1",
                    "ip": "192.168.0.101",
                    "username": "admin",
                    "password": "password1",
                    "enabled": True,
                },
                "invalid entry",
                123,
                None,
            ]),
            encoding="utf-8",
        )

        devices = self.repository.load_devices()

        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].ip_address, "192.168.0.101")


if __name__ == "__main__":
    unittest.main()
