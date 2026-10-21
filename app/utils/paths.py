import os
import sys


def resource_path(*relative_path: str) -> str:
    """Get an absolute resource path for development or PyInstaller."""
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        # app/utils/paths.py -> project root
        base_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )

    return os.path.join(base_path, *relative_path)
