"""The theme and the language the user picked in an analyze-* GUI.

They live in the app's SettingsStore, next to the update settings, because the
webview's own storage does not survive a restart (see settings.py).  The page
reads them from /common/settings.js, which the app serves with ``script()``,
and writes them through the app's /settings endpoint, which calls ``update()``.
"""

import json

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
