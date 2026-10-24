import unittest
from unittest.mock import patch

from app.services import port_status_orchestrator as portStatus


class TestNotificationSettingsIntegration(unittest.TestCase):
    def test_successful_load_updates_notification_service(self):
        settings = {
            "sim": {"enabled": True},
            "network": {"enabled": False},
        }

        with (
            patch.object(
                portStatus.notification_settings_repository,
                "load_settings",
                return_value=settings,
            ),
            patch.object(
                portStatus.notification_service,
                "update_settings",
            ) as update_settings,
        ):
            portStatus.load_notification_settings()

        update_settings.assert_called_once_with(settings)

    def test_failed_load_resets_notification_settings(self):
        with (
            patch.object(
                portStatus.notification_settings_repository,
                "load_settings",
                side_effect=OSError("Test read failure"),
            ),
            patch.object(
                portStatus.notification_service,
                "update_settings",
            ) as update_settings,
        ):
            portStatus.load_notification_settings()

        update_settings.assert_called_once_with({})

    def test_ui_wrapper_reloads_notification_settings(self):
        with patch.object(
            portStatus,
            "load_notification_settings",
        ) as load_settings:
            portStatus.update_notification_settings_from_ui()

        load_settings.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()