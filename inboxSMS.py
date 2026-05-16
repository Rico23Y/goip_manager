from utils import *

def launch_inboxSMS_tabs(goip_window=0):
    # --- Edge options ---
    viewer_driver, viewer_main_window = viewer_options("--window-size=800,1200")
    os.system('cls')
    if goip_window == 0:
        try:
            open_viewer_tabs("goip_sms_inbox_en.html", "Port Status Opened",
                             viewer_driver)

            viewer_driver.switch_to.window(viewer_main_window)
            viewer_driver.close()
        except Exception:
            pass

    if goip_window > 0:
        try:
            devices = reload_devices()
            login_to_device("goip_sms_inbox_en.html", "Port Status Opened",
                            viewer_driver, devices[goip_window - 1])
        except Exception:
            pass





