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
