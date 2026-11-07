"""Tests for analyze_common.web module."""

import re

from analyze_common import COMMON_CSS
from analyze_common.web import WEB_DIR


def _specificity(selector):
    """(ids, classes, types) of one compound-and-combinator CSS selector:
    :where() counts nothing and :not() counts its argument."""
    s = re.sub(r":where\([^)]*\)", "", selector)
    s = re.sub(r":not\(([^)]*)\)", r"\1", s)
    ids = len(re.findall(r"#[\w-]+", s))
    classes = len(re.findall(r"\.[\w-]+|\[[^\]]*\]|(?<!:):[\w-]+", s))
    rest = re.sub(r"#[\w-]+|\.[\w-]+|\[[^\]]*\]|::?[\w-]+", "", s)
    types = len(re.findall(r"[a-zA-Z][\w-]*", rest))
    return ids, classes, types


class TestCommonCss:
    def test_specificity_counts_the_selector_parts(self):
        assert _specificity(".input-bar button:hover") == (0, 2, 1)
        assert _specificity(".input-bar button:hover:not(:disabled)") == (0, 3, 1)
        assert _specificity(":where(.input-bar) button:hover:not(:disabled)") == (0, 2, 1)
        assert _specificity("#clear-btn:hover:not(:disabled)") == (1, 2, 0)

    def test_hover_faces_yield_to_a_consumer_that_has_not_adopted_them(self):
        """A consumer whose style.css, loaded after this file, still has its
        own `.input-bar button:hover` keeps that hover face: the shared hover
        rules rank no higher than that selector."""
        css = re.sub(r"/\*.*?\*/", "", COMMON_CSS.read_text(encoding="utf-8"), flags=re.S)
        rule = re.search(r"([^{}]+)\{\s*background:\s*var\(--btn-bg-hover\);\s*\}", css)
        selectors = [s.strip() for s in rule.group(1).split(",")]
        assert any(".input-bar" in s for s in selectors)
        assert any(".compare-bar" in s for s in selectors)
        assert any(".save-btn" in s for s in selectors)
        for selector in selectors:
            consumer = ".save-btn:hover" if ".save-btn" in selector else ".input-bar button:hover"
            assert _specificity(selector) <= _specificity(consumer), selector

    def test_copy_hover_yields_to_a_consumer_that_has_not_adopted_it(self):
        css = re.sub(r"/\*.*?\*/", "", COMMON_CSS.read_text(encoding="utf-8"), flags=re.S)
        rule = re.search(r"([^{}]+)\{\s*background:\s*var\(--copy-bg-hover\);\s*\}", css)
        selector = rule.group(1).strip()
        assert ".copy-btn" in selector
        assert _specificity(selector) <= _specificity(".copy-btn:hover")

    def test_input_bar_wraps_at_900px_over_a_consumer_field_flex(self):
        """At 900 px and narrower the bar wraps and the field takes its own
        row, outranking the field's flex in a consumer's style.css."""
        css = re.sub(r"/\*.*?\*/", "", COMMON_CSS.read_text(encoding="utf-8"), flags=re.S)
        block = re.search(r"@media \(max-width: 900px\)\s*\{(.*?)\n\}", css, re.S).group(1)
        rules = dict((s.strip(), b.strip()) for s, b in re.findall(r"([^{}]+)\{([^{}]*)\}", block))
        assert rules[".input-bar"] == "flex-wrap: wrap;"
        field = next(s for s in rules if "url-input" in s)
        assert rules[field] == "flex: 1 1 100%;"
        for consumer in (".input-bar #url-input", ".input-bar input"):
            assert _specificity(field) > _specificity(consumer), consumer

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

    def test_controls_take_the_page_font(self):
        css = re.sub(r"/\*.*?\*/", "", COMMON_CSS.read_text(encoding="utf-8"), flags=re.S)
        rule = re.search(r"([^{}]+)\{\s*font-family:\s*inherit;\s*\}", css)
        assert [s.strip() for s in rule.group(1).split(",")] == ["button", "input", "select", "textarea"]
        assert len(re.findall(r"font-family:", css)) == 2

    def test_status_rule_comes_before_its_states(self):
        css = COMMON_CSS.read_text(encoding="utf-8")
        assert 0 <= css.index("#status {") < css.index("#status.loading") < css.index("#status.error")
        assert "min-height: 20px;" in re.search(r"#status \{([^}]*)\}", css).group(1)

    def test_input_bar_and_queue_rules_are_in_common_css(self):
        css = COMMON_CSS.read_text(encoding="utf-8")
        for selector in ("#submit-btn", "#load-btn", "#add-btn", "#browse-btn", "#clear-btn",
                         ".compare-bar button", ".track-item", ".track-tag", ".track-btn"):
            assert selector in css
        root = re.search(r":root\s*\{([^}]*)\}", css).group(1)
        for name in ("--add-bg", "--add-bg-hover", "--add-fg",
                     "--neutral-bg", "--neutral-bg-hover", "--neutral-fg"):
            assert name + ":" in root


    def test_result_title_and_button_rules_are_in_common_css(self):
        css = COMMON_CSS.read_text(encoding="utf-8")
        for selector in (".title-row", ".result-title", ".meta-info", ".save-btn", ".copy-btn"):
            assert selector + " {" in css or selector + ",\n" in css, selector
        root = re.search(r":root\s*\{([^}]*)\}", css).group(1)
        for name in ("--error-bg", "--copy-bg", "--copy-bg-hover", "--copy-border", "--copy-fg"):
            assert name + ":" in root


class TestMaxTracks:
    def test_ui_js_mirrors_the_python_value_as_a_global_of_the_page(self):
        from analyze_common import MAX_TRACKS, UI_JS
        found = re.search(r"^window\.MAX_TRACKS = (\d+);$", UI_JS.read_text(encoding="utf-8"), re.MULTILINE)
        assert found and int(found.group(1)) == MAX_TRACKS

    def test_ui_js_leaves_a_consumer_free_to_declare_the_name(self):
        from analyze_common import UI_JS
        assert not re.search(r"^(const|let|var|function) MAX_TRACKS\b", UI_JS.read_text(encoding="utf-8"), re.MULTILINE)


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
