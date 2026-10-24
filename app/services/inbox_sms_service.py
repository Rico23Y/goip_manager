"""Service functions for opening GOIP SMS inbox pages."""

from app.goip.browser import (
    login_to_device,
    open_viewer_tabs,
    viewer_options,
)
from app.repositories.device_repository import DeviceRepository


def launch_inbox_sms_tabs(
    device_repository: DeviceRepository,
    goip_window: int = 0,
) -> None:
    """Open all GOIP SMS inboxes or a single selected GOIP inbox."""
    if goip_window < 0:
        return

    devices = device_repository.load_devices() if goip_window > 0 else None

    if devices is not None and goip_window > len(devices):
        print(
            f"Invalid GOIP number: {goip_window}. "
            f"Only {len(devices)} devices available."
        )
        return

    viewer_driver, viewer_main_window = viewer_options(
        "--window-size=800,1200"
    )

    try:
        if goip_window == 0:
            open_viewer_tabs(
                "goip_sms_inbox_en.html",
                "Inbox SMS Opened",
                viewer_driver,
                device_repository,
            )
        else:
            success = login_to_device(
                "goip_sms_inbox_en.html",
                "Inbox SMS Opened",
                viewer_driver,
                devices[goip_window - 1],
            )

            if not success:
                viewer_driver.close()
                viewer_driver.switch_to.window(viewer_main_window)
    except Exception as error:
        print(f"Error opening inbox page: {error}")
    finally:
        # Preserve the legacy behavior of closing the temporary main window
        # after opening all inboxes.
        if goip_window == 0:
            try:
                viewer_driver.switch_to.window(viewer_main_window)
                viewer_driver.close()
            except Exception as error:
                print(f"Error closing browser window: {error}")
