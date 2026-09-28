from utils import *
from app.repositories.device_repository import DeviceRepository

def launch_inboxSMS_tabs(
    device_repository: DeviceRepository,
    goip_window: int = 0
) -> None:
    # --- Edge options ---
    viewer_driver, viewer_main_window = viewer_options("--window-size=800,1200")
    os.system('cls')
    if goip_window == 0:
        try:
            open_viewer_tabs(
                "goip_sms_inbox_en.html",
                "Inbox SMS Opened",
                viewer_driver,
                device_repository
            )

            viewer_driver.switch_to.window(viewer_main_window)
            viewer_driver.close()

        except Exception as e:
            print(f"Error opening inbox tabs: {e}")

    if goip_window > 0:
        try:
            devices = device_repository.load_devices()

            if goip_window > len(devices):
                print(
                    f"Invalid GOIP number: {goip_window}. "
                    f"Only {len(devices)} devices available."
                )
                return

            success = login_to_device(
                "goip_sms_inbox_en.html",
                "Inbox SMS Opened",
                viewer_driver,
                devices[goip_window - 1]
            )

            if not success:
                viewer_driver.close()
                viewer_driver.switch_to.window(viewer_main_window)

        except Exception as e:
            print(f"Error opening inbox page: {e}")





