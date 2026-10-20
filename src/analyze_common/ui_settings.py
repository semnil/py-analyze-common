"""The theme and the language the user picked in an analyze-* GUI.

They live in the app's SettingsStore, next to the update settings, because the
webview's own storage does not survive a restart (see settings.py).  The page
reads them from /common/settings.js, which the app serves with ``script()``,
and writes them through the app's /settings endpoint, which calls ``update()``.
"""

import json
import sys
import threading

from analyze_common.platform import IS_MAC
from analyze_common.settings import SettingsStore
from analyze_common.theme import is_dark_mode
from analyze_common.web import SETTINGS_JS

THEME_KEY = "theme"
LANG_KEY = "lang"
THEMES = ("light", "dark", "auto")
LANGS = ("en", "ja")

# The window's color before the page paints: --bg of web/common.css per theme.
BG_LIGHT = "#fafafa"
BG_DARK = "#1a1a2e"

_CHOICES = {THEME_KEY: THEMES, LANG_KEY: LANGS}


class UiSettings:
    """Reads and writes the theme and the language in ``settings``.

    A missing or unknown stored theme reads as "auto".  A missing or unknown
    stored language reads as None, and the page then follows the OS language.
    """

    def __init__(self, settings: SettingsStore):
        self.settings = settings

    def theme(self) -> str:
        value = self.settings.get(THEME_KEY, None)
        return value if value in THEMES else "auto"

    def lang(self) -> str | None:
        value = self.settings.get(LANG_KEY, None)
        return value if value in LANGS else None

    def values(self) -> dict:
        return {THEME_KEY: self.theme(), LANG_KEY: self.lang()}

    def update(self, changes) -> dict:
        """Store the one setting in ``changes`` ({"theme": ...} or {"lang": ...})
        and return ``values()``.

        Raises ValueError, without writing, when ``changes`` holds anything
        else, and OSError when the file cannot be written.
        """
        if not isinstance(changes, dict) or len(changes) != 1:
            raise ValueError(f"expected one of '{THEME_KEY}' or '{LANG_KEY}'")
        ((name, value),) = changes.items()
        choices = _CHOICES.get(name)
        if choices is None:
            raise ValueError(f"unknown setting {name!r}")
        if value not in choices:
            raise ValueError(f"{name!r} must be one of {', '.join(choices)}")
        self.settings.set(name, value)
        return self.values()

    def background_color(self) -> str:
        """The window color for the stored theme.  "auto" follows the OS."""
        theme = self.theme()
        dark = is_dark_mode() if theme == "auto" else theme == "dark"
        return BG_DARK if dark else BG_LIGHT

    def script(self) -> bytes:
        """web/settings.js with the stored values set ahead of it.

        Raises OSError when settings.js cannot be read.
        """
        stored = json.dumps(self.values())
        return f"window.analyzeSettingsStored = {stored};\n".encode("utf-8") + SETTINGS_JS.read_bytes()


def show_window_color_until_paint(window) -> None:
    """Keep a pywebview window's background_color on screen until the page paints.

    On macOS, pywebview attaches the WKWebView to the window when the first
    navigation finishes, and the WKWebView draws white until its first frame.
    This turns the WKWebView's own background off before the window shows, so
    the window color stays visible instead.  WebView2 on Windows paints
    background_color itself, so other systems are left as they are.

    The WKWebView is changed only from a before_show handler that runs on the
    main thread (pywebview 5.4 and later).  Without a before_show event
    (pywebview before 5.3), with the handler on another thread (pywebview 5.3)
    or on any other failure, the cause is reported on stderr and the window
    opens as before.
    """
    if not IS_MAC:
        return
    if not hasattr(window.events, "before_show"):
        print("Could not clear the webview background: this pywebview has no before_show event", file=sys.stderr)
        return

    def _clear_webview_background():
        if threading.current_thread() is not threading.main_thread():
            print("Could not clear the webview background: before_show ran outside the main thread",
                  file=sys.stderr)
            return
        try:
            from webview.platforms.cocoa import BrowserView

            BrowserView.instances[window.uid].webview.setValue_forKey_(False, "drawsBackground")
        except Exception as err:
            print(f"Could not clear the webview background: {err!r}", file=sys.stderr)

    window.events.before_show += _clear_webview_background
