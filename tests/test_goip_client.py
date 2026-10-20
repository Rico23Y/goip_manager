import unittest
from unittest.mock import MagicMock, patch

import requests

from app.goip.client import (
    get_auth_cookie_value,
    login_goip,
    md5_hex,
    parse_login_status,
)
from app.core.signals import signals
from app.models.goip_device import GoipDevice


class TestGoipClient(unittest.TestCase):
    def setUp(self):
        self.device = GoipDevice(
            goip="1",
            ip_address="192.168.0.101",
            username="admin",
            password="test-password",
        )

    def test_md5_hex(self):
        self.assertEqual(
            md5_hex("test"),
            "098f6bcd4621d373cade4e832627b4f6",
        )

    def test_get_auth_cookie_value(self):
        session = requests.Session()
        session.cookies.set("auth_nonce", "nonce-value")

        self.assertEqual(
            get_auth_cookie_value(session),
            "nonce-value",
        )

    def test_get_auth_cookie_value_when_missing(self):
        session = requests.Session()

        self.assertIsNone(get_auth_cookie_value(session))

    def test_parse_login_status(self):
        html = """
        <input id="ID_LoginStatus" value="0">
        <script>var login_remaining_count = 3;</script>
        """

        self.assertEqual(parse_login_status(html), ("0", 3))

    @patch("app.goip.client.requests.Session")
    def test_login_goip_success(self, session_class):
        session = session_class.return_value
        session.cookies = requests.cookies.RequestsCookieJar()
        session.cookies.set("auth_nonce", "nonce-value")

        response = MagicMock()
        response.text = '<input id="ID_LoginStatus" value="0">'
        response.url = "http://192.168.0.101/home.html"
        session.post.return_value = response

        result = login_goip(self.device)

        self.assertIs(result, session)
        session.get.assert_called_once_with(
            "http://192.168.0.101/login_en.html",
            timeout=5,
        )
        session.post.assert_called_once()

        posted_data = session.post.call_args.kwargs["data"]
        expected_digest = md5_hex("admin:test-password:nonce-value")
        self.assertEqual(
            posted_data["encoded"],
            f"admin:{expected_digest}",
        )
        self.assertEqual(posted_data["nonce"], "nonce-value")

    @patch("app.goip.client.requests.Session")
    def test_login_goip_missing_cookie(self, session_class):
        session = session_class.return_value
        session.cookies.clear()

        result = login_goip(self.device)

        self.assertIsNone(result)
        session.close.assert_called_once_with()
        session.post.assert_not_called()


    @patch("app.goip.client.requests.Session")
    def test_login_goip_connection_failure(self, session_class):
        session = session_class.return_value
        session.get.side_effect = requests.ConnectionError("connection failed")

        result = login_goip(self.device)

        self.assertIsNone(result)
        session.post.assert_not_called()
        session.close.assert_called_once_with()


    @patch("app.goip.client.requests.Session")
    def test_login_goip_post_failure_closes_session(self, session_class):
        session = session_class.return_value
        session.cookies = requests.cookies.RequestsCookieJar()
        session.cookies.set("auth_nonce", "nonce-value")
        session.post.side_effect = requests.ConnectionError("POST failed")

        result = login_goip(self.device)

        self.assertIsNone(result)
        session.get.assert_called_once()
        session.post.assert_called_once()
        session.close.assert_called_once_with()

    @patch("app.goip.client.requests.Session")
    def test_login_goip_wrong_password_emits_signal(self, session_class):
        session = session_class.return_value
        session.cookies = requests.cookies.RequestsCookieJar()
        session.cookies.set("auth_nonce", "nonce-value")

        response = MagicMock()
        response.text = (
            '<input id="ID_LoginStatus" value="1">'
            '<script>var login_remaining_count = 2;</script>'
        )
        response.url = "http://192.168.0.101/login_en.html"
        session.post.return_value = response

        received_devices = []

        def capture_device(device):
            received_devices.append(device)

        signals.wrongPassword.connect(capture_device)
        try:
            result = login_goip(self.device)
        finally:
            signals.wrongPassword.disconnect(capture_device)

        self.assertIsNone(result)
        session.close.assert_called_once_with()
        self.assertEqual(received_devices, [self.device])

if __name__ == "__main__":
    unittest.main()
