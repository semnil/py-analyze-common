"""Cross-platform dark mode detection."""

import os
import subprocess

from desktop_app_common.platform import IS_LINUX, IS_MAC, IS_WINDOWS


def _c_locale_env() -> dict:
    """Return environment dict with LC_ALL=C / LANG=C forced.

    Prevents localized command output (e.g. translated theme names) from
    breaking substring matches like "dark".
    """
    return {**os.environ, "LC_ALL": "C", "LANG": "C"}


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
    except (OSError, FileNotFoundError, ImportError):
        return False


def _is_dark_mode_macos() -> bool:
    try:
        r = subprocess.run(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            capture_output=True, text=True, timeout=2,
            env=_c_locale_env(),
        )
        return r.returncode == 0 and "Dark" in r.stdout
    except Exception:
        return False


def _is_dark_mode_linux() -> bool:
    try:
        r = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            capture_output=True, text=True, timeout=2,
            env=_c_locale_env(),
        )
        if r.returncode == 0 and "dark" in r.stdout.lower():
            return True
    except Exception:
        pass
    try:
        r = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"],
            capture_output=True, text=True, timeout=2,
            env=_c_locale_env(),
        )
        if r.returncode == 0 and "dark" in r.stdout.lower():
            return True
    except Exception:
        pass
    try:
        r = subprocess.run(
            ["kreadconfig5", "--group", "General", "--key", "ColorScheme"],
            capture_output=True, text=True, timeout=2,
            env=_c_locale_env(),
        )
        return r.returncode == 0 and "dark" in r.stdout.lower()
    except Exception:
        return False
