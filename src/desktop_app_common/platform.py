"""Platform detection and subprocess helpers."""

import subprocess
import sys

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")
IS_FROZEN = getattr(sys, "frozen", False)


def subprocess_kwargs() -> dict:
    """Return platform-specific kwargs to hide console windows on frozen builds.

    On frozen Windows builds (PyInstaller GUI app), child subprocesses would
    otherwise spawn a console window. STARTF_USESHOWWINDOW suppresses it.
    On other platforms this is a no-op.
    """
    if IS_WINDOWS and IS_FROZEN:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": si}
    return {}
