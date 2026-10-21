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
