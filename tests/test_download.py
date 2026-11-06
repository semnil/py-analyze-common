"""Tests for analyze_common.download module."""

import os
import subprocess
import sys
from unittest import mock

import pytest

from analyze_common import download
from analyze_common.download import sanitize_filename, compute_middle, download_audio


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


class TestDownloadAudio:
    @pytest.fixture
    def youtube_dl(self, tmp_path):
        """Replaces YoutubeDL; the download leaves one file in ``tmp_path / "work"``."""
        work = tmp_path / "work"
        work.mkdir()
        ydl = mock.MagicMock()
        ydl.__enter__.return_value = ydl

        def extract_info(url, download):
            (work / "abc.opus").write_text("audio")
            return {"title": "Title"}

        ydl.extract_info.side_effect = extract_info
        with mock.patch("analyze_common.download.YoutubeDL", return_value=ydl) as cls:
            cls.work = str(work)
            yield cls

    def test_passes_absolute_tool_paths(self, tmp_path, monkeypatch, make_program, youtube_dl):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        ffmpeg = make_program(bin_dir, "ffmpeg")
        deno = make_program(bin_dir, "deno")
        monkeypatch.setenv("PATH", str(bin_dir))
        path, title = download_audio("https://example.com/watch?v=X", youtube_dl.work)
        assert (os.path.basename(path), title) == ("abc.opus", "Title")
        opts = youtube_dl.call_args[0][0]
        assert opts["ffmpeg_location"] == str(ffmpeg)
        assert opts["js_runtimes"] == {"deno": {"path": str(deno)}}

    def test_no_deno_on_path_disables_js_runtimes(self, tmp_path, monkeypatch, make_program, youtube_dl):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        make_program(bin_dir, "ffmpeg")
        make_program(tmp_path, "deno")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PATH", os.pathsep.join([".", str(bin_dir)]))
        download_audio("https://example.com/watch?v=X", youtube_dl.work)
        assert youtube_dl.call_args[0][0]["js_runtimes"] == {}

    def test_ffmpeg_in_current_directory_is_not_used(self, tmp_path, monkeypatch, make_program, youtube_dl):
        make_program(tmp_path, "ffmpeg")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PATH", os.pathsep.join(["", "."]))
        with pytest.raises(FileNotFoundError, match="ffmpeg"):
            download_audio("https://example.com/watch?v=X", youtube_dl.work)
        youtube_dl.assert_not_called()

    def test_download_failure_preserves_cause(self, monkeypatch, youtube_dl):
        monkeypatch.setattr("analyze_common.download.find_executable", lambda name: "/tools/" + name)
        failure = OSError("download interrupted")
        youtube_dl.return_value.extract_info.side_effect = failure
        with pytest.raises(RuntimeError, match="yt-dlp failed: download interrupted") as error:
            download_audio("https://example.com/audio", youtube_dl.work)
        assert error.value.__cause__ is failure
        youtube_dl.return_value.__exit__.assert_called_once()

    @pytest.mark.parametrize("info", [None, {}, {"title": ""}])
    def test_missing_title_uses_fallback(self, monkeypatch, youtube_dl, info):
        from pathlib import Path

        monkeypatch.setattr("analyze_common.download.find_executable", lambda name: "/tools/" + name)
        Path(youtube_dl.work, "audio.opus").write_bytes(b"audio")
        youtube_dl.return_value.extract_info.side_effect = None
        youtube_dl.return_value.extract_info.return_value = info
        path, title = download_audio("https://example.com/audio", youtube_dl.work)
        assert (Path(path).name, title) == ("audio.opus", "Untitled")

    def test_no_downloaded_file_is_reported(self, monkeypatch, youtube_dl):
        monkeypatch.setattr("analyze_common.download.find_executable", lambda name: "/tools/" + name)
        youtube_dl.return_value.extract_info.side_effect = None
        youtube_dl.return_value.extract_info.return_value = {"title": "Clip"}
        with pytest.raises(FileNotFoundError, match="produced no audio file"):
            download_audio("https://example.com/audio", youtube_dl.work)

    def test_selects_newest_file_and_ignores_directories(self, monkeypatch, youtube_dl):
        from pathlib import Path

        monkeypatch.setattr("analyze_common.download.find_executable", lambda name: "/tools/" + name)
        work = Path(youtube_dl.work)
        old, new = work / "old.opus", work / "new.opus"
        old.write_bytes(b"old")
        new.write_bytes(b"new")
        os.utime(old, (100, 100))
        os.utime(new, (200, 200))
        (work / "directory").mkdir()
        youtube_dl.return_value.extract_info.side_effect = None
        youtube_dl.return_value.extract_info.return_value = {"title": "Clip"}
        assert download_audio("https://example.com/audio", str(work)) == (str(new), "Clip")


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


class TestYtDlpPrograms:
    def test_a_program_yt_dlp_started_ends_with_this_process(self, heartbeat):
        script = (
            "import sys, threading, time\n"
            "from yt_dlp.utils import Popen\n"
            "from analyze_common.download import _stop_yt_dlp_programs_at_exit\n"
            "_stop_yt_dlp_programs_at_exit()\n"
            "threading.Thread(target=Popen.run, args=(sys.argv[1:],), daemon=True).start()\n"
            "time.sleep(2)\n"
        )
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
        subprocess.run([sys.executable, "-c", script, *heartbeat.args], env=env, check=True, timeout=30)
        assert heartbeat.file.exists()
        assert heartbeat.stopped()

    def test_watching_twice_wraps_the_start_once(self):
        download._stop_yt_dlp_programs_at_exit()
        start = download.YtDlpPopen.__init__
        download._stop_yt_dlp_programs_at_exit()
        assert download.YtDlpPopen.__init__ is start

    def test_download_audio_watches_before_it_starts_yt_dlp(self, monkeypatch, tmp_path):
        order = []
        monkeypatch.setattr(download, "_stop_yt_dlp_programs_at_exit", lambda: order.append("watch"))
        monkeypatch.setattr(download, "find_executable", lambda name: order.append("find") or None)
        with pytest.raises(FileNotFoundError):
            download_audio("https://example.com/a", str(tmp_path))
        assert order[:2] == ["watch", "find"]
