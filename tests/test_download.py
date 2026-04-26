"""Tests for analyze_common.download module."""

import pytest

from analyze_common.download import sanitize_filename, compute_middle


class TestSanitizeFilename:
    def test_basic(self):
        assert sanitize_filename("hello") == "hello"

    def test_replaces_unsafe_chars_with_underscore(self):
        assert sanitize_filename("a:b") == "a_b"

    def test_removes_all_unsafe_chars(self):
        result = sanitize_filename('a/b\\c:d*e?"f<g>h|i')
        for ch in ':/\\*?"<>|':
            assert ch not in result

    def test_strips_leading_trailing_dots_and_spaces(self):
        assert sanitize_filename("  .hello. ") == "hello"

    def test_empty_string_returns_untitled(self):
        assert sanitize_filename("") == "untitled"

    def test_only_dots_returns_untitled(self):
        assert sanitize_filename("...") == "untitled"

    def test_truncates_long_name(self):
        name = "a" * 300
        assert len(sanitize_filename(name)) == 200

    def test_japanese_title_preserved(self):
        title = "【ポケモン】メタモンと始める街づくり"
        result = sanitize_filename(title)
        assert "ポケモン" in result

    def test_null_byte_removed(self):
        assert "\x00" not in sanitize_filename("evil\x00name.wav")

    def test_control_chars_removed(self):
        result = sanitize_filename("a\x01b\x1fc")
        assert "\x01" not in result
        assert "\x1f" not in result

    def test_path_traversal_unix(self):
        result = sanitize_filename("../../etc/passwd")
        assert "/" not in result
        assert "\\" not in result

    def test_path_traversal_windows(self):
        result = sanitize_filename("..\\..\\Windows\\system32\\cmd.exe")
        assert "\\" not in result
        assert "/" not in result

    @pytest.mark.parametrize("name", ["CON", "PRN", "AUX", "NUL",
                                       "COM1", "COM9", "LPT1", "LPT9"])
    def test_windows_reserved_name_prefixed(self, name):
        result = sanitize_filename(name)
        assert result.startswith("_")
        assert name in result

    def test_windows_reserved_case_insensitive(self):
        result = sanitize_filename("con")
        assert result.startswith("_")

    def test_windows_reserved_with_extension(self):
        result = sanitize_filename("CON.txt")
        assert result.startswith("_")

    def test_non_reserved_unchanged(self):
        result = sanitize_filename("CONE")
        assert not result.startswith("_")


class TestComputeMiddle:
    def test_short_source_uses_full(self):
        ss, dur, msg = compute_middle(300.0, 10.0)
        assert ss == 0.0
        assert dur == 300.0
        assert "full duration" in msg

    def test_long_source_extracts_middle(self):
        ss, dur, msg = compute_middle(3600.0, 10.0)
        expected_dur = 600.0
        expected_ss = (3600.0 - 600.0) / 2
        assert dur == expected_dur
        assert ss == expected_ss
        assert "extracting" in msg

    def test_exact_match_uses_full(self):
        ss, dur, msg = compute_middle(600.0, 10.0)
        assert ss == 0.0
        assert dur == 600.0

    def test_returns_three_values(self):
        result = compute_middle(1000.0, 5.0)
        assert len(result) == 3
        assert isinstance(result[2], str)

    def test_zero_total_sec_raises(self):
        with pytest.raises(ValueError, match="positive"):
            compute_middle(0, 10.0)

    def test_negative_total_sec_raises(self):
        with pytest.raises(ValueError, match="positive"):
            compute_middle(-100.0, 10.0)

    def test_zero_duration_min_raises(self):
        with pytest.raises(ValueError, match="positive"):
            compute_middle(600.0, 0)

    def test_negative_duration_min_raises(self):
        with pytest.raises(ValueError, match="positive"):
            compute_middle(600.0, -5.0)

    def test_very_small_duration(self):
        ss, dur, msg = compute_middle(600.0, 0.001)
        assert dur == pytest.approx(0.06)
        assert ss > 0

    def test_very_large_total(self):
        ss, dur, msg = compute_middle(1e7, 10.0)
        assert dur == 600.0
        assert ss == pytest.approx((1e7 - 600.0) / 2)

    def test_barely_shorter_uses_full(self):
        ss, dur, msg = compute_middle(599.9, 10.0)
        assert ss == 0.0
        assert dur == 599.9
        assert "full duration" in msg
