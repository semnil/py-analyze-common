"""Windows-only setup of the consumer's process; does nothing on other OSes."""

import sys


def set_app_user_model_id(app_id: str) -> None:
    """Set the process's AppUserModelID, by which the Windows taskbar groups windows and takes the icon embedded in
    the EXE (without it, the Python runtime's default ID is used and the taskbar shows no app icon)."""
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
