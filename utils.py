from requests import RequestException
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException, \
    StaleElementReferenceException, UnexpectedAlertPresentException, NoAlertPresentException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
import os, time, json, csv, sys, re, math, subprocess, threading, requests, operator, platform
from subprocess import DEVNULL
from selenium import webdriver
from plyer import notification
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtWidgets import QMessageBox
from PySide6.QtGui import QIcon
import requests, re, time

from app.models.goip_device import GoipDevice
from app.core.config import get_appdata_path
from app.utils.paths import resource_path
from app.goip.connection import is_port_online, ping_ip, is_port_open
from app.goip.client import (
    md5_hex,
    get_auth_cookie_value,
    parse_login_status,
    login_goip,
)
from app.core.signals import GoipSignals, signals
from app.ui.login_dialogs import show_login_error_popup
from app.goip.browser import (
    viewer_options,
    login_to_device,
    wait_for_login_or_alert,
    open_viewer_tabs,
    launch_home_tabs,
    PAGE_LOAD_TIMEOUT,
    ELEMENT_WAIT_TIME,
    KEEPALIVE_INTERVAL,
)

__all__ = [
    # Selenium
    'webdriver', 'By', 'Options', 'Service',
    'WebDriverWait', 'EC',
    'TimeoutException', 'NoSuchElementException',
    'WebDriverException', 'StaleElementReferenceException',

    # Standard libraries
    'operator', 'notification', 'DEVNULL',
    'math', 'time', 'csv', 'sys', 'os', 're', 'threading',
    'requests',

    # Functions
    'viewer_options', 'open_viewer_tabs', 'is_port_open',
    'login_to_device', 'login_goip',

    # Constants / Mappings
    'status_map', 'PAGE_LOAD_TIMEOUT', 'ELEMENT_WAIT_TIME',
    'KEEPALIVE_INTERVAL', 'signal_to_level',
    'NETWORK_LABEL'
]

# --- Config ---        # Previous value
PAGE_LOAD_TIMEOUT = 30  # 5
ELEMENT_WAIT_TIME = 30  # 0.6
KEEPALIVE_INTERVAL = 2  # 2

NETWORK_LABEL = ["NA", "", "2G", "3G", "4G", "5G"]

# Status mapping
status_map = {
    0: "No Card Detected",
    1: "Card Detected",
    2: "Registering Card",
    3: "Register OK",
    4: "Calling",
    5: "No Balance",
    6: "Register Failed",
    7: "Locked",
    8: "Locked By Operator",
    9: "SIM Problem",
    10: "Locked",
    11: "Card Inserted",
    12: "Locked By User",
    13: "Inter-Calling",
    14: "Inter-Calling Holding",
    15: "Access Mobile Network",
    16: "Response Timeout",
    99: "Module Problem"
}

# For signal bar conversion
def signal_to_level(signal_str):
    if signal_str != '':
        signal = int(signal_str)
        if signal <= 4 or signal > 31:
            return 0
        elif signal <= 8:
            return 1
        elif signal <= 13:
            return 2
        elif signal <= 18:
            return 3
        elif signal <= 24:
            return 4
        else:
            return 5
    else:
        return -1
