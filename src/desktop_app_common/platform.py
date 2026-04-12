"""Platform detection and subprocess helpers."""

import os
import subprocess
import sys

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")
IS_FROZEN = getattr(sys, "frozen", False)

_DYLD_VARS = ("DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH", "DYLD_INSERT_LIBRARIES")


def subprocess_kwargs() -> dict:
    """Return platform-specific kwargs for spawning child processes from frozen apps.

    Windows frozen: suppress console window with STARTF_USESHOWWINDOW.
    macOS frozen: restore PyInstaller's saved DYLD_* env so that child
    PyInstaller onefile binaries (e.g. yt-dlp_macos) do not load our own
    Python.framework, which would fail with a Team ID code-signature mismatch.
    """
    if IS_WINDOWS and IS_FROZEN:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": si}
    if IS_MAC and IS_FROZEN:
        env = os.environ.copy()
        for var in _DYLD_VARS:
            orig = env.pop(f"{var}_ORIG", None)
            if orig is not None:
                env[var] = orig
            else:
                env.pop(var, None)
        return {"env": env}
    return {}
