import os
from pathlib import Path


def get_appdata_path(filename: str) -> str:
    """Return the path to a file in the application's data directory."""
    appdata = os.getenv("APPDATA", os.path.expanduser("~"))
    base_dir = Path(appdata) / "GoIP.Manager"
    base_dir.mkdir(parents=True, exist_ok=True)

    return str(base_dir / filename)
