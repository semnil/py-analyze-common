"""Tests for analyze_common.ffmpeg."""

import json
import os
import subprocess
import sys
import time

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


class TestRunFfmpeg:
    def test_answers_as_subprocess_run_does(self):
        code = "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"
        result = ffmpeg.run_ffmpeg([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8")
        assert (result.returncode, result.stdout.strip(), result.stderr.strip()) == (3, "out", "err")

    def test_check_raises_with_what_the_program_wrote(self):
        code = "import sys; print('err', file=sys.stderr); sys.exit(3)"
        with pytest.raises(subprocess.CalledProcessError) as caught:
            ffmpeg.run_ffmpeg([sys.executable, "-c", code], check=True, capture_output=True)
        assert caught.value.returncode == 3
        assert caught.value.stderr.strip() == b"err"

    def test_timeout_kills_the_program(self, heartbeat):
        started = time.monotonic()
        with pytest.raises(subprocess.TimeoutExpired):
            ffmpeg.run_ffmpeg(heartbeat.args, capture_output=True, timeout=1)
        assert time.monotonic() - started < 15
        assert heartbeat.stopped()

    def test_a_program_that_ended_is_not_killed_at_exit(self):
        script = (
            "import atexit, subprocess, sys\n"
            "from analyze_common.ffmpeg import run_ffmpeg\n"
            "kills = []\n"
            "real_kill = subprocess.Popen.kill\n"
            "subprocess.Popen.kill = lambda self: (kills.append(1), real_kill(self))\n"
            "atexit.register(lambda: print('kills', len(kills)))\n"
            "run_ffmpeg([sys.executable, '-c', 'pass'])\n"
            "try:\n"
            "    run_ffmpeg([sys.executable, '-c', 'raise SystemExit(1)'], check=True)\n"
            "except subprocess.CalledProcessError:\n"
            "    pass\n"
        )
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
        result = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "kills 0"

    def test_program_ends_with_this_process(self, heartbeat):
        script = (
            "import sys, threading, time\n"
            "from analyze_common.ffmpeg import run_ffmpeg\n"
            "threading.Thread(target=run_ffmpeg, args=(sys.argv[1:],), daemon=True).start()\n"
            "time.sleep(2)\n"
        )
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
        subprocess.run([sys.executable, "-c", script, *heartbeat.args], env=env, check=True, timeout=30)
        assert heartbeat.file.exists()
        assert heartbeat.stopped()
