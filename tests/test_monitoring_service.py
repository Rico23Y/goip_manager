import unittest
from unittest.mock import MagicMock, patch

from app.models.goip_device import GoipDevice
from app.services.monitoring_service import MonitoringService


class TestMonitoringService(unittest.TestCase):
    def setUp(self):
        self.service = MonitoringService(check_notifications=MagicMock())

    def test_stop_signals_events_and_marks_monitoring_stopped(self):
        thread = MagicMock()
        thread.name = "mon-1"
        thread.is_alive.return_value = False
        stop_event = MagicMock()

        self.service._monitor_threads["1"] = thread
        self.service._stop_events["1"] = stop_event
        self.service._running = True

        self.service.start(MagicMock(), will_run=False)

        stop_event.set.assert_called_once_with()
        thread.join.assert_called_once()
        self.assertFalse(self.service.running)

    def test_stop_keeps_running_flag_when_thread_is_alive(self):
        thread = MagicMock()
        thread.name = "mon-1"
        thread.is_alive.return_value = True
        stop_event = MagicMock()

        self.service._monitor_threads["1"] = thread
        self.service._stop_events["1"] = stop_event
        self.service._running = True

        self.service.start(MagicMock(), will_run=False)

        stop_event.set.assert_called_once_with()
        self.assertTrue(self.service.running)

    def test_stop_uses_shared_five_second_deadline(self):
        threads = []

        for index in range(3):
            thread = MagicMock()
            thread.name = f"mon-{index}"
            thread.is_alive.return_value = False
            threads.append(thread)
            self.service._monitor_threads[str(index)] = thread
            self.service._stop_events[str(index)] = MagicMock()

        self.service._running = True

        with patch(
            "app.services.monitoring_service.time.monotonic",
            side_effect=[100.0, 100.0, 101.0, 102.0],
        ):
            self.service.start(MagicMock(), will_run=False)

        self.assertEqual(
            threads[0].join.call_args.kwargs["timeout"],
            5,
        )
        self.assertEqual(
            threads[1].join.call_args.kwargs["timeout"],
            4,
        )
        self.assertEqual(
            threads[2].join.call_args.kwargs["timeout"],
            3,
        )

    @patch("app.services.monitoring_service.time.sleep")
    @patch("app.services.monitoring_service.is_port_open", return_value=True)
    @patch(
        "app.services.monitoring_service.scrape_goip_data",
        side_effect=Exception("scrape failed"),
    )
    @patch("app.services.monitoring_service.login_goip")
    def test_closes_session_after_scrape_failure(
        self,
        login_goip,
        scrape_goip_data,
        is_port_open,
        sleep,
    ):
        device = GoipDevice(
            goip="1",
            ip_address="192.168.0.101",
            username="admin",
            password="test-password",
        )
        session = MagicMock()
        login_goip.return_value = session

        stop_event = MagicMock()
        stop_event.is_set.side_effect = [False, False, True]
        stop_event.wait.return_value = False

        with patch.object(self.service, "update_state"):
            self.service.monitor_scraper_loop(device, stop_event)

        session.close.assert_called_once_with()

    @patch("app.services.monitoring_service.is_port_open", return_value=True)
    @patch(
        "app.services.monitoring_service.scrape_goip_data",
        return_value=[["ok"]],
    )
    @patch("app.services.monitoring_service.login_goip")
    def test_closes_session_when_monitoring_stops(
        self,
        login_goip,
        scrape_goip_data,
        is_port_open,
    ):
        device = GoipDevice(
            goip="1",
            ip_address="192.168.0.101",
            username="admin",
            password="test-password",
        )
        session = MagicMock()
        login_goip.return_value = session

        stop_event = MagicMock()
        stop_event.is_set.return_value = False
        stop_event.wait.return_value = True

        with patch.object(self.service, "update_state"):
            self.service.monitor_scraper_loop(device, stop_event)

        session.close.assert_called_once_with()

    def test_get_status_data_returns_a_copy(self):
        self.service._goip_state["1"] = {
            "status": [["ok"]],
            "isRunning": True,
            "description": "Running",
        }
        repository = MagicMock()
        repository.load_devices.return_value = [MagicMock()]

        result = self.service.get_status_data(repository)

        result["1"]["description"] = "Changed"
        self.assertEqual(
            self.service._goip_state["1"]["description"],
            "Running",
        )


if __name__ == "__main__":
    unittest.main()
