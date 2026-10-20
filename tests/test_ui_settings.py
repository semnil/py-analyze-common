"""Tests for analyze_common.ui_settings."""

import json
import re
import sys
from unittest import mock

import pytest

from analyze_common import COMMON_CSS, SETTINGS_JS, ui_settings
from analyze_common.settings import SettingsStore
from analyze_common.ui_settings import BG_DARK, BG_LIGHT, UiSettings


@pytest.fixture
def store(tmp_path):
    return SettingsStore(tmp_path / "app" / "settings.json")


def _write(store, data):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps(data), encoding="utf-8")


class TestRead:
    def test_missing_file_reads_as_auto_and_no_language(self, store):
        assert UiSettings(store).values() == {"theme": "auto", "lang": None}

    def test_stored_values_are_read(self, store):
        _write(store, {"theme": "dark", "lang": "ja"})
        assert UiSettings(store).values() == {"theme": "dark", "lang": "ja"}

    @pytest.mark.parametrize("theme", ["Dark", "", None, 1, ["dark"], {"dark": 1}])
    def test_unknown_theme_reads_as_auto(self, store, theme):
        _write(store, {"theme": theme})
        assert UiSettings(store).theme() == "auto"

    @pytest.mark.parametrize("lang", ["fr", "JA", "", None, True, ["ja"]])
    def test_unknown_language_reads_as_none(self, store, lang):
        _write(store, {"lang": lang})
        assert UiSettings(store).lang() is None


class TestUpdate:
    @pytest.mark.parametrize("changes", [{"theme": "light"}, {"theme": "dark"}, {"theme": "auto"},
                                         {"lang": "en"}, {"lang": "ja"}])
    def test_stores_one_setting_and_keeps_the_others(self, store, changes):
        _write(store, {"update_check_at_launch": False, "theme": "dark", "lang": "en"})
        values = UiSettings(store).update(changes)
        on_disk = json.loads(store.path.read_text(encoding="utf-8"))
        expected = {"theme": "dark", "lang": "en", **changes}
        assert values == expected
        assert on_disk == {"update_check_at_launch": False, **expected}

    @pytest.mark.parametrize("changes, message", [
        (None, "expected one of 'theme' or 'lang'"),
        ([], "expected one of 'theme' or 'lang'"),
        ("dark", "expected one of 'theme' or 'lang'"),
        ({}, "expected one of 'theme' or 'lang'"),
        ({"theme": "dark", "lang": "ja"}, "expected one of 'theme' or 'lang'"),
        ({"theme": "Dark"}, "'theme' must be one of light, dark, auto"),
        ({"theme": None}, "'theme' must be one of light, dark, auto"),
        ({"theme": ["dark"]}, "'theme' must be one of light, dark, auto"),
        ({"lang": "fr"}, "'lang' must be one of en, ja"),
        ({"lang": None}, "'lang' must be one of en, ja"),
        ({"update_check_at_launch": False}, "unknown setting 'update_check_at_launch'"),
        ({"color": "dark"}, "unknown setting 'color'"),
    ])
    def test_rejects_anything_else_without_writing(self, store, changes, message):
        _write(store, {"theme": "light"})
        before = store.path.read_bytes()
        with pytest.raises(ValueError) as caught:
            UiSettings(store).update(changes)
        assert str(caught.value) == message
        assert store.path.read_bytes() == before

    def test_write_failure_raises_os_error(self, store):
        with mock.patch.object(store, "set", side_effect=OSError("read-only")):
            with pytest.raises(OSError):
                UiSettings(store).update({"theme": "dark"})


class TestBackgroundColor:
    @pytest.mark.parametrize("dark_os", [True, False])
    def test_fixed_themes_ignore_the_os(self, store, dark_os):
        with mock.patch.object(ui_settings, "is_dark_mode", return_value=dark_os):
            _write(store, {"theme": "dark"})
            assert UiSettings(store).background_color() == BG_DARK
            _write(store, {"theme": "light"})
            assert UiSettings(store).background_color() == BG_LIGHT

    @pytest.mark.parametrize("dark_os, color", [(True, BG_DARK), (False, BG_LIGHT)])
    def test_auto_follows_the_os(self, store, dark_os, color):
        with mock.patch.object(ui_settings, "is_dark_mode", return_value=dark_os):
            assert UiSettings(store).background_color() == color

    def test_colors_match_the_page_background(self):
        css = COMMON_CSS.read_text(encoding="utf-8")
        root = re.search(r":root\s*\{([^}]*)\}", css).group(1)
        dark = re.search(r'\[data-theme="dark"\]\s*\{([^}]*)\}', css).group(1)
        bg = lambda body: re.search(r"--bg\s*:\s*([^;]+);", body).group(1).strip()
        assert bg(root) == BG_LIGHT
        assert bg(dark) == BG_DARK


class TestScript:
    def test_stored_values_come_ahead_of_settings_js(self, store):
        _write(store, {"theme": "light", "lang": "ja"})
        first, rest = UiSettings(store).script().split(b"\n", 1)
        assert first == b'window.analyzeSettingsStored = {"theme": "light", "lang": "ja"};'
        assert rest == SETTINGS_JS.read_bytes()

    def test_unknown_values_are_not_passed_to_the_page(self, store):
        _write(store, {"theme": "</script>", "lang": "<b>"})
        first = UiSettings(store).script().split(b"\n", 1)[0]
        assert first == b'window.analyzeSettingsStored = {"theme": "auto", "lang": null};'


class _Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


class _Window:
    def __init__(self, uid):
        self.uid = uid
        self.events = mock.Mock(before_show=_Event())


class _WebView:
    def __init__(self):
        self.values = {}

    def setValue_forKey_(self, value, key):
        self.values[key] = value


@pytest.fixture
def cocoa(monkeypatch):
    """A stand-in for webview.platforms.cocoa holding BrowserView.instances."""
    import types

    module = types.ModuleType("webview.platforms.cocoa")
    module.BrowserView = types.SimpleNamespace(instances={})
    monkeypatch.setitem(sys.modules, "webview.platforms.cocoa", module)
    return module.BrowserView


class TestShowWindowColorUntilPaint:
    def test_other_systems_register_nothing(self):
        window = _Window("main")
        with mock.patch.object(ui_settings, "IS_MAC", False):
            ui_settings.show_window_color_until_paint(window)
        assert window.events.before_show.handlers == []

    def test_mac_clears_the_webview_background_before_show(self, cocoa):
        window, other = _Window("main"), _Window("other")
        cocoa.instances = {"other": mock.Mock(webview=_WebView()), "main": mock.Mock(webview=_WebView())}
        with mock.patch.object(ui_settings, "IS_MAC", True):
            ui_settings.show_window_color_until_paint(window)
        assert len(window.events.before_show.handlers) == 1
        assert cocoa.instances["main"].webview.values == {}
        window.events.before_show.handlers[0]()
        assert cocoa.instances["main"].webview.values == {"drawsBackground": False}
        assert cocoa.instances["other"].webview.values == {}

    def test_mac_failure_is_reported_and_not_raised(self, cocoa, capsys):
        window = _Window("main")
        with mock.patch.object(ui_settings, "IS_MAC", True):
            ui_settings.show_window_color_until_paint(window)
        window.events.before_show.handlers[0]()
        assert "Could not clear the webview background" in capsys.readouterr().err
