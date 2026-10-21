
import unittest

from app.models.goip_device import GoipDevice


class TestGoipDevice(unittest.TestCase):

    def setUp(self) -> None:
        self.device = GoipDevice(
            goip="GOIP 1",
            ip_address="192.168.0.101",
            username="admin",
            password="test-password",
            enabled=True,
        )

    def test_to_dict(self) -> None:
        data = self.device.to_dict()

        self.assertEqual(data["goip"], "GOIP 1")
        self.assertEqual(data["ip"], "192.168.0.101")
        self.assertEqual(data["username"], "admin")
        self.assertEqual(data["password"], "test-password")
        self.assertIs(data["enabled"], True)

    def test_from_dict(self) -> None:
        data = {
            "goip": "GOIP 2",
            "ip": "192.168.0.102",
            "username": "admin",
            "password": "another-password",
            "enabled": False,
        }

        device = GoipDevice.from_dict(data)

        self.assertEqual(device.goip, "GOIP 2")
        self.assertEqual(device.ip_address, "192.168.0.102")
        self.assertEqual(device.username, "admin")
        self.assertEqual(device.password, "another-password")
        self.assertIs(device.enabled, False)

    def test_from_dict_uses_defaults_for_missing_fields(self) -> None:
        device = GoipDevice.from_dict({})

        self.assertEqual(device.goip, "")
        self.assertEqual(device.ip_address, "")
        self.assertEqual(device.username, "")
        self.assertEqual(device.password, "")
        self.assertIs(device.enabled, True)


if __name__ == "__main__":
    unittest.main()
