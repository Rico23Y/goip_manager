import os, sys, re, json, shutil, zipfile, requests, subprocess, ctypes, psutil
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog, QCheckBox
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from packaging import version
from utils import get_appdata_path

WEBDRIVER_NAME = "msedgedriver.exe"

# Always store in AppData\GoIP.Manager


DRIVER_DIR = get_appdata_path("")
DRIVER_PATH = os.path.join(DRIVER_DIR, WEBDRIVER_NAME)
CONFIG_PATH = os.path.join(DRIVER_DIR, "webdriver_update_config.json")
ICON_PATH = os.path.join(DRIVER_DIR, "icons", "drivers.png")

EDGE_STORAGE_BASE = "https://msedgewebdriverstorage.blob.core.windows.net/edgewebdriver"
LATEST_RELEASE_URL = "https://msedgedriver.azureedge.net/LATEST_RELEASE_{major}"

def apply_icon(widget):
    """Apply custom window icon if available."""
    if os.path.exists(ICON_PATH):
        widget.setWindowIcon(QIcon(ICON_PATH))


# ---------------- Permissions & Process Check ---------------- #

def is_admin():
    """Check if running as Administrator."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def has_write_access(path):
    """Check if path is writable."""
    try:
        test_file = os.path.join(path, "test.tmp")
        with open(test_file, "w") as f:
            f.write("ok")
        os.remove(test_file)
        return True
    except Exception:
        return False


def kill_existing_driver():
    """Kill any running msedgedriver.exe process (to avoid WinError 5)."""
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] and "msedgedriver" in proc.info['name'].lower():
            try:
                proc.kill()
            except Exception:
                pass


# ---------------- Config ---------------- #

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return {"skip_optional_update": False}


def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=4)


# ---------------- Version Detection ---------------- #

def get_edge_version():
    """Detect Microsoft Edge version (registry or fallback to command)."""
    reg_paths = [
        r'HKCU\Software\Microsoft\Edge\BLBeacon',
        r'HKLM\Software\Microsoft\Edge\BLBeacon',
        r'HKLM\Software\WOW6432Node\Microsoft\Edge\BLBeacon'
    ]
    for path in reg_paths:
        try:
            output = subprocess.check_output(
                f'reg query "{path}" /v version', shell=True
            ).decode()
            match = re.search(r"(\d+\.\d+\.\d+\.\d+)", output)
            if match:
                return match.group(1)
        except Exception:
            pass

    # Fallback: run msedge directly
    try:
        output = subprocess.check_output(["msedge", "--version"]).decode()
        match = re.search(r"(\d+\.\d+\.\d+\.\d+)", output)
        if match:
            return match.group(1)
    except Exception:
        pass

    return None


def get_driver_version():
    """Get installed msedgedriver.exe version."""
    if not os.path.exists(DRIVER_PATH):
        return None
    try:
        output = subprocess.check_output([DRIVER_PATH, "--version"]).decode()
        match = re.search(r"(\d+\.\d+\.\d+\.\d+)", output)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None


def get_latest_driver_for_major(major_version):
    """Fetch latest driver version for a given major version."""
    try:
        resp = requests.get(LATEST_RELEASE_URL.format(major=major_version), timeout=5)
        if resp.ok:
            return resp.text.strip()
    except Exception:
        pass
    return None


def same_major_minor(ver1, ver2):
    """Compare only major.minor.build (ignore revision)."""
    return ".".join(ver1.split(".")[:3]) == ".".join(ver2.split(".")[:3])


# ---------------- Download / Install ---------------- #

def download_driver(edge_version, progress_callback=None):
    """Download and install Edge WebDriver safely with error handling."""

    # --- permission checks before download ---
    if not has_write_access(DRIVER_DIR):
        QMessageBox.critical(
            None, "Permission Error",
            f"You do not have write access to:\n{DRIVER_DIR}\n\n"
            "Please restart the application as Administrator."
        )
        return False

    if not is_admin():
        QMessageBox.warning(
            None, "Administrator Rights Required",
            "Updating WebDriver may require Administrator rights.\n"
            "If update fails, try restarting as Administrator."
        )

    # --- kill driver if running ---
    kill_existing_driver()

    url = f"{EDGE_STORAGE_BASE}/{edge_version}/edgedriver_win64.zip"
    zip_path = os.path.join(DRIVER_DIR, "edgedriver.zip")
    temp_extract_dir = os.path.join(DRIVER_DIR, "edgedriver_tmp")

    try:
        r = requests.get(url, stream=True, timeout=15)
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        QMessageBox.critical(None, "Download Failed", f"Could not download WebDriver:\n{e}")
        return False

    total_size = int(r.headers.get('content-length', 0))
    downloaded = 0

    try:
        with open(zip_path, 'wb') as f:
            for chunk in r.iter_content(1024 * 64):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_size > 0:
                        progress_callback(downloaded, total_size)

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_extract_dir)

        # Find driver exe
        driver_found = False
        for root, _, files in os.walk(temp_extract_dir):
            for file in files:
                if file.lower() == WEBDRIVER_NAME:  # match filename only
                    extracted_path = os.path.join(root, file)
                    if os.path.exists(DRIVER_PATH):
                        os.remove(DRIVER_PATH)
                    shutil.move(extracted_path, DRIVER_PATH)
                    driver_found = True
                    break

        if not driver_found:
            raise FileNotFoundError("msedgedriver.exe not found in archive.")

    except Exception as e:
        QMessageBox.critical(None, "Install Failed", f"Failed to install WebDriver:\n{e}")
        return False
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)
        if os.path.exists(temp_extract_dir):
            shutil.rmtree(temp_extract_dir, ignore_errors=True)

    return True


def download_with_progress(edge_version):
    progress = QProgressDialog("Downloading WebDriver...", "Cancel", 0, 100)
    progress.setWindowTitle("Updating WebDriver")
    progress.setWindowModality(Qt.ApplicationModal)  # ✅ fixed
    apply_icon(progress)

    def update_progress(downloaded, total):
        percent = int(downloaded / total * 100)
        progress.setValue(percent)
        QApplication.processEvents()

    if not download_driver(edge_version, update_progress):
        return False

    progress.setValue(100)
    QMessageBox.information(None, "Done", "WebDriver updated successfully.")
    return True



# ---------------- Main Check ---------------- #

def check_and_update_driver():
    app = QApplication.instance() or QApplication(sys.argv)
    config = load_config()

    edge_ver = get_edge_version()
    driver_ver = get_driver_version()

    if not edge_ver:
        QMessageBox.critical(None, "Error", "Cannot detect Microsoft Edge version.")
        return False

    # Get latest compatible driver
    major_version = edge_ver.split('.')[0]
    latest_driver_version = get_latest_driver_for_major(major_version) or edge_ver

    # If no driver installed
    if not driver_ver:
        msg = QMessageBox()
        apply_icon(msg)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Critical Update Required")
        msg.setText(f"No WebDriver found.\nMicrosoft Edge: {edge_ver}\nYou must download now.")
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Close)
        reply = msg.exec_()

        if reply == QMessageBox.Close:
            return False
        return download_with_progress(latest_driver_version)

    # If driver is incompatible
    if not same_major_minor(driver_ver, edge_ver):
        msg = QMessageBox()
        apply_icon(msg)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Critical Update Required")
        msg.setText(f"Your WebDriver ({driver_ver}) is incompatible with Edge ({edge_ver}).\nDownload now.")
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Close)
        reply = msg.exec_()

        if reply == QMessageBox.Close:
            return False
        return download_with_progress(latest_driver_version)

    # Optional update (revision mismatch)
    if version.parse(driver_ver) != version.parse(edge_ver):
        if not config.get("skip_optional_update", False):
            msg = QMessageBox()
            apply_icon(msg)
            msg.setWindowTitle("Update Available")
            msg.setText(f"Your WebDriver: {driver_ver}\nEdge: {edge_ver}\nUpdate now?")
            download_btn = msg.addButton("Download", QMessageBox.AcceptRole)
            cancel_btn = msg.addButton("Cancel", QMessageBox.RejectRole)
            dont_show_chk = QCheckBox("Don't show again")
            msg.setCheckBox(dont_show_chk)
            msg.exec_()

            if msg.clickedButton() == download_btn:
                return download_with_progress(latest_driver_version)
            if dont_show_chk.isChecked():
                config["skip_optional_update"] = True
                save_config(config)

    return True
