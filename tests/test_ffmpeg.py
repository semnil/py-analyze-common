"""Tests for analyze_common.ffmpeg."""

import json
import os
import subprocess

import pytest

from analyze_common import ffmpeg


@pytest.fixture
def ffprobe_calls(monkeypatch):
    """Replaces subprocess.run in analyze_common.ffmpeg; collects the argv lists."""
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        out = json.dumps({"streams": [{"channels": 2}], "format": {"duration": "12.5"}})
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")

    monkeypatch.setattr(ffmpeg.subprocess, "run", fake_run)
    return calls


class TestProbeInfo:
    def test_runs_ffprobe_by_absolute_path(self, tmp_path, monkeypatch, make_program, ffprobe_calls):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        program = make_program(bin_dir, "ffprobe")
        monkeypatch.setenv("PATH", str(bin_dir))
        assert ffmpeg.probe_info("a.wav") == (2, 12.5)
        assert ffprobe_calls[0][0] == str(program)

    def test_ffprobe_in_current_directory_is_not_run(self, tmp_path, monkeypatch, make_program, ffprobe_calls):
        make_program(tmp_path, "ffprobe")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PATH", os.pathsep.join(["", "."]))
        with pytest.raises(FileNotFoundError, match="ffprobe"):
            ffmpeg.probe_info("a.wav")
        assert ffprobe_calls == []

    @pytest.mark.parametrize("streams, expected", [
        ([], 2), ([{}], 2), ([{"channels": "6"}], 6), ([{"channels": 0}], 1),
    ])
    def test_channel_defaults_and_clamp(self, monkeypatch, streams, expected):
        payload = {"streams": streams, "format": {"duration": "0.125"}}
        with mock_probe(monkeypatch, payload) as run:
            assert ffmpeg.probe_info("clip.wav") == (expected, 0.125)
        kwargs = run.call_args.kwargs
        assert kwargs["timeout"] == 30
        assert kwargs["env"]["LC_ALL"] == kwargs["env"]["LANG"] == "C"

    @pytest.mark.parametrize("duration", [None, "unknown", [], "nan", "inf", "-inf", "0", "-0.1"])
    def test_invalid_duration_is_reported(self, monkeypatch, duration):
        with mock_probe(monkeypatch, {"format": {"duration": duration}}):
            with pytest.raises(RuntimeError, match="duration"):
                ffmpeg.probe_info("clip.wav")

    def test_missing_format_is_reported(self, monkeypatch):
        with mock_probe(monkeypatch, {}):
            with pytest.raises(RuntimeError, match="could not determine duration"):
                ffmpeg.probe_info("clip.wav")

    @pytest.mark.parametrize("stdout", [None, "", " \n"])
    def test_empty_output_is_reported(self, monkeypatch, stdout):
        with mock_probe(monkeypatch, {}, stdout=stdout):
            with pytest.raises(RuntimeError, match="empty output"):
                ffmpeg.probe_info("clip.wav")

    def test_failed_process_reports_exit_and_bounded_stderr(self, monkeypatch):
        stderr = "private prefix" + "x" * 200
        with mock_probe(monkeypatch, {}, returncode=7, stderr=stderr):
            with pytest.raises(RuntimeError) as error:
                ffmpeg.probe_info("clip.wav")
        assert str(error.value) == "ffprobe failed (exit 7): " + "x" * 200

    def test_invalid_json_is_not_treated_as_audio(self, monkeypatch):
        with mock_probe(monkeypatch, {}, stdout="{broken"):
            with pytest.raises(json.JSONDecodeError):
                ffmpeg.probe_info("clip.wav")


def mock_probe(monkeypatch, payload, **overrides):
    from unittest.mock import patch

    monkeypatch.setattr(ffmpeg, "find_executable", lambda name: "/tools/ffprobe")
    fields = {"stdout": json.dumps(payload), "stderr": "", "returncode": 0, **overrides}
    result = subprocess.CompletedProcess(["ffprobe"], **fields)
    return patch.object(ffmpeg.subprocess, "run", return_value=result)
