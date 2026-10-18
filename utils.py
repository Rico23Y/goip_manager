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
from app.core.goip_status import (
    NETWORK_LABEL,
    status_map,
    signal_to_level,
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