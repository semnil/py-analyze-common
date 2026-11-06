"""The consumer's canvas text takes its font family from CHART_FONT_FAMILY in web/ui.js.

The consumer's tests/test_chart_font.py runs these on its repository (analyze_common.testing).
"""
from analyze_common import testing


def _frontend_scripts():
    root, _ = testing.app()
    return [path for path in sorted((root / "frontend").rglob("*.js")) if "vendor" not in path.parts]


def test_no_script_names_a_font_of_its_own():
    written = [path.name for path in _frontend_scripts() if "Segoe UI" in path.read_text(encoding="utf-8")]
    assert written == []


def test_the_scripts_use_the_shared_font_family():
    assert any("CHART_FONT_FAMILY" in path.read_text(encoding="utf-8") for path in _frontend_scripts())
