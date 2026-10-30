"""Tests for analyze_common.web module."""

import re

from analyze_common import COMMON_CSS
from analyze_common.web import WEB_DIR


class TestCommonCss:
    def test_file_ships_next_to_module(self):
        assert COMMON_CSS.parent == WEB_DIR
        assert COMMON_CSS.is_file()

    def test_braces_balanced(self):
        css = COMMON_CSS.read_text(encoding="utf-8")
        assert css.count("{") == css.count("}")

    def test_defines_shared_variables_for_both_themes(self):
        css = COMMON_CSS.read_text(encoding="utf-8")
        root = re.search(r":root\s*\{([^}]*)\}", css).group(1)
        dark = re.search(r'\[data-theme="dark"\]\s*\{([^}]*)\}', css).group(1)
        names = lambda body: sorted(re.findall(r"(--[\w-]+)\s*:", body))
        assert names(root) == names(dark)
        assert "--text" in names(root)


class TestSettingsJs:
    def test_file_ships_next_to_module(self):
        from analyze_common import SETTINGS_JS
        assert SETTINGS_JS.parent == WEB_DIR
        assert SETTINGS_JS.is_file()


class TestUpdateJs:
    def test_file_ships_next_to_module(self):
        from analyze_common import UPDATE_JS
        assert UPDATE_JS.parent == WEB_DIR
        assert UPDATE_JS.is_file()

    def test_both_languages_have_the_same_strings(self):
        from analyze_common import UPDATE_JS
        js = UPDATE_JS.read_text(encoding="utf-8")
        en = re.search(r"\ben: \{(.*?)\n    \},", js, re.S).group(1)
        ja = re.search(r"\bja: \{(.*?)\n    \},", js, re.S).group(1)
        keys = lambda body: sorted(re.findall(r'^\s*"([\w.]+)":', body, re.M))
        assert keys(en) == keys(ja)
        assert "confirm" in keys(en)

    def test_dialog_rules_are_in_common_css(self):
        css = COMMON_CSS.read_text(encoding="utf-8")
        for selector in (".settings-toggle", ".settings-scrim", ".settings-box", ".settings-btn"):
            assert selector in css


class TestSharedScripts:
    def test_files_ship_next_to_module(self):
        from analyze_common import BOOT_JS, I18N_JS, UI_JS
        for path in (BOOT_JS, I18N_JS, UI_JS):
            assert path.parent == WEB_DIR
            assert path.is_file()
