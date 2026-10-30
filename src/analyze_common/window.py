"""Windows-only setup of the consumer's pywebview window; both functions do nothing on other OSes."""

import sys


def set_app_user_model_id(app_id: str) -> None:
    """Set the process's AppUserModelID, by which the Windows taskbar groups windows and takes the icon embedded in
    the EXE (without it, the Python runtime's default ID is used and the taskbar shows no app icon)."""
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)


def block_external_drop(window) -> None:
    """Keep WebView2 from navigating to a file dropped on the window or on a swipe gesture: sets
    ``AllowExternalDrop = False`` and turns off swipe navigation on the window's ``shown`` and ``loaded`` events.
    The page's own drop handler (capture phase, ``stopImmediatePropagation``) takes the drop instead."""
    if sys.platform != "win32":
        return

    def disable():
        try:
            window.gui.webview.AllowExternalDrop = False
        except Exception:
            pass
        try:
            window.gui.webview.CoreWebView2.Settings.IsSwipeNavigationEnabled = False
        except Exception:
            pass

    window.events.shown += disable
    window.events.loaded += disable
