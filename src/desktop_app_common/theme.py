"""Cross-platform dark mode detection."""

import subprocess

from desktop_app_common.platform import IS_LINUX, IS_MAC, IS_WINDOWS


def is_dark_mode() -> bool:
    """Return True if the OS is currently set to dark mode.

    Falls back to False on unsupported platforms or errors.
    """
    if IS_WINDOWS:
        return _is_dark_mode_windows()
    if IS_MAC:
        return _is_dark_mode_macos()
    if IS_LINUX:
        return _is_dark_mode_linux()
    return False


def _is_dark_mode_windows() -> bool:
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return not value
    except Exception:
        return False


def _is_dark_mode_macos() -> bool:
    try:
        r = subprocess.run(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            capture_output=True, text=True, timeout=2,
        )
        return r.returncode == 0 and "Dark" in r.stdout
    except Exception:
        return False


def _is_dark_mode_linux() -> bool:
    try:
        r = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            capture_output=True, text=True, timeout=2,
        )
        if r.returncode == 0 and "dark" in r.stdout.lower():
            return True
    except Exception:
        pass
    try:
        r = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"],
            capture_output=True, text=True, timeout=2,
        )
        return r.returncode == 0 and "dark" in r.stdout.lower()
    except Exception:
        return False
