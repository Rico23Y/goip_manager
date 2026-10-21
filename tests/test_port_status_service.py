
import unittest
from unittest.mock import MagicMock, patch

from app.models.goip_device import GoipDevice
from app.services.port_status_service import scrape_goip_data


class TestScrapeGoipData(unittest.TestCase):
    def setUp(self):
        self.device = GoipDevice(
            goip="1",
            ip_address="192.168.0.101",
            username="admin",
            password="test-password",
        )
        self.session = MagicMock()

    def test_successful_response_parses_port_data(self):
        row = [None] * 15
        row[2] = "Channel 1"
        row[7] = "3"
        row[9] = "4G"
        row[13] = "Ready"
        row[14] = "00:10:00"

        response = MagicMock()
        response.json.return_value = {"data": [row]}
        self.session.post.return_value = response

        result = scrape_goip_data(self.device, self.session)

        self.session.post.assert_called_once_with(
            "http://192.168.0.101/get_parameter.html",
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data="type=updatePortStatusDetail",
            timeout=5,
        )
        self.assertEqual(
            result,
            [["Ready", "3", "4G", "Channel 1", "00:10:00"]],
        )

    def test_empty_signal_sets_network_to_zero(self):
        row = [None] * 15
        row[2] = "Channel 1"
        row[7] = ""
        row[9] = "4G"
        row[13] = "No SIM"
        row[14] = "00:00:00"

        response = MagicMock()
        response.json.return_value = {"data": [row]}
        self.session.post.return_value = response

        result = scrape_goip_data(self.device, self.session)

        self.assertEqual(result[0][2], 0)

    def test_malformed_row_is_skipped(self):
        response = MagicMock()
        response.json.return_value = {"data": [[1, 2, 3]]}
        self.session.post.return_value = response

        with patch("app.services.port_status_service.time.strftime",
                   return_value="test-time"):
            result = scrape_goip_data(self.device, self.session)

        self.assertEqual(result, [])

    def test_request_failure_returns_none(self):
        self.session.post.side_effect = Exception("connection failed")

        with patch("app.services.port_status_service.time.strftime",
                   return_value="test-time"):
            result = scrape_goip_data(self.device, self.session)

        self.assertIsNone(result)

    def test_invalid_json_response_returns_none(self):
        response = MagicMock()
        response.json.side_effect = ValueError("invalid JSON")
        self.session.post.return_value = response

        with patch("app.services.port_status_service.time.strftime",
                   return_value="test-time"):
            result = scrape_goip_data(self.device, self.session)

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
