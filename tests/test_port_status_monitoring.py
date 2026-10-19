import unittest
from unittest.mock import MagicMock, patch

import portStatus


class TestStopGoipMonitoring(unittest.TestCase):
    def setUp(self):
        # Save the original global state so tests do not affect one another.
        self.original_threads = portStatus._monitor_threads.copy()
        self.original_events = portStatus._stop_events.copy()
        self.original_running = portStatus._RUNNING

        portStatus._monitor_threads.clear()
        portStatus._stop_events.clear()
        portStatus._RUNNING = False

    def tearDown(self):
        portStatus._monitor_threads.clear()
        portStatus._monitor_threads.update(self.original_threads)

        portStatus._stop_events.clear()
        portStatus._stop_events.update(self.original_events)

        portStatus._RUNNING = self.original_running

    def test_stop_signals_events_and_marks_monitoring_stopped(self):
        thread = MagicMock()
        thread.name = "mon-1"
        thread.is_alive.return_value = False

        stop_event = MagicMock()

        portStatus._monitor_threads["1"] = thread
        portStatus._stop_events["1"] = stop_event
        portStatus._RUNNING = True

        portStatus.start_goip_monitoring(
            device_repository=MagicMock(),
            will_run=False,
        )

        stop_event.set.assert_called_once_with()
        thread.join.assert_called_once()
        self.assertFalse(portStatus._RUNNING)

    def test_stop_keeps_running_flag_when_thread_is_alive(self):
        thread = MagicMock()
        thread.name = "mon-1"
        thread.is_alive.return_value = True

        stop_event = MagicMock()

        portStatus._monitor_threads["1"] = thread
        portStatus._stop_events["1"] = stop_event
        portStatus._RUNNING = True

        portStatus.start_goip_monitoring(
            device_repository=MagicMock(),
            will_run=False,
        )

        stop_event.set.assert_called_once_with()
        self.assertTrue(portStatus._RUNNING)

    def test_stop_uses_shared_five_second_deadline(self):
        threads = []

        for index in range(3):
            thread = MagicMock()
            thread.name = f"mon-{index}"
            thread.is_alive.return_value = False
            threads.append(thread)
            portStatus._monitor_threads[str(index)] = thread
            portStatus._stop_events[str(index)] = MagicMock()

        portStatus._RUNNING = True

        with patch.object(
            portStatus.time,
            "monotonic",
            side_effect=[100.0, 100.0, 101.0, 102.0],
        ):
            portStatus.start_goip_monitoring(
                device_repository=MagicMock(),
                will_run=False,
            )

        self.assertEqual(threads[0].join.call_args.args, ())
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


if __name__ == "__main__":
    unittest.main()
