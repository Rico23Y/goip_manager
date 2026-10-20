import unittest
from unittest.mock import Mock

from app.services.notification_service import NotificationService


class TestNotificationService(unittest.TestCase):
    def setUp(self):
        self.notify_user = Mock()
        self.service = NotificationService(self.notify_user)

    def test_disabled_notifications_do_not_send_alerts(self):
        self.service.update_settings({"enabled": False})

        self.service.check_for_notifications("GOIP-1", [])

        self.notify_user.assert_not_called()

    def test_sim_status_alert_is_sent_once_until_status_changes(self):
        self.service.update_settings({
            "enabled": True,
            "sim_status": {
                "enabled": True,
                "values": [3],
            },
        })
        data = [[3, "15", 4, " (port 1)", "00:10:00"]]

        self.service.check_for_notifications("GOIP-1", data)
        self.service.check_for_notifications("GOIP-1", data)

        self.assertEqual(self.notify_user.call_count, 1)
        self.assertIn("Register OK", self.notify_user.call_args.args[0])

        self.service.check_for_notifications("GOIP-1", data)

        self.assertEqual(self.notify_user.call_count, 1)

    def test_network_alert_is_sent_when_threshold_is_exceeded(self):
        self.service.update_settings({
            "enabled": True,
            "network_type": {
                "enabled": True,
                "values": ["4G"],
                "operator": ">",
                "count": 0,
            },
        })
        data = [[3, "15", 4, " (port 1)", "00:10:00"]]

        self.service.check_for_notifications("GOIP-1", data)

        self.notify_user.assert_called_once()
        self.assertIn("network", self.notify_user.call_args.args[0])

    def test_custom_signal_alert_is_sent_when_threshold_is_exceeded(self):
        self.service.update_settings({
            "enabled": True,
            "signal": {
                "enabled": True,
                "bar": {"enabled": False, "values": []},
                "custom": {
                    "enabled": True,
                    "min": 10,
                    "max": 20,
                    "operator": ">",
                    "count": 0,
                },
            },
        })
        data = [
            [3, "15", 4, " (port 1)", "00:10:00"],
            [3, "25", 4, " (port 2)", "00:10:00"],
        ]

        self.service.check_for_notifications("GOIP-1", data)

        self.notify_user.assert_called_once()
        self.assertIn("Signal 10-20", self.notify_user.call_args.args[0])


if __name__ == "__main__":
    unittest.main()