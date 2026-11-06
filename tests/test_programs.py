"""Tests for analyze_common.programs: a program against the end of this process."""

import os
import subprocess
import sys
import tempfile
import types
import weakref

import pytest

from analyze_common import programs

STARTS = ["run_ffmpeg", "yt-dlp"]
ENDS = ["exit", "terminate"]

_START = """
def start(how, args):
    from analyze_common.download import _stop_yt_dlp_programs_at_exit
    from analyze_common.ffmpeg import run_ffmpeg
    from yt_dlp.utils import Popen
    _stop_yt_dlp_programs_at_exit()
    (run_ffmpeg if how == "run_ffmpeg" else Popen.run)(args)
"""

_END = """
def end(how):
    if how == "terminate":
        import AppKit
        from analyze_common.window import run_atexit_on_app_quit
        run_atexit_on_app_quit()
        AppKit.NSApplication.sharedApplication().terminate_(None)
"""

STARTING = _START + _END + """
import subprocess, sys, threading, time
real_start = subprocess.Popen.__init__
started = threading.Event()
def start_then_hold(self, *args, **kwargs):
    real_start(self, *args, **kwargs)
    started.set()
    time.sleep(1)
subprocess.Popen.__init__ = start_then_hold
threading.Thread(target=start, args=(sys.argv[1], sys.argv[3:]), daemon=True).start()
started.wait(10)
end(sys.argv[2])
"""

STARTING_IN_ATEXIT = _START + _END + """
import atexit, os, sys, threading, time
go = threading.Event()
def worker():
    go.wait()
    start(sys.argv[1], sys.argv[3:])
threading.Thread(target=worker, daemon=True).start()
import analyze_common.programs
def start_and_wait_for_the_first_beat():
    go.set()
    for _ in range(200):
        if os.path.exists(sys.argv[-1]):
            break
        time.sleep(0.05)
atexit.register(start_and_wait_for_the_first_beat)
end(sys.argv[2])
"""

AFTER_THE_KILL = _START + _END + """
import atexit, sys
def start_after_the_kill():
    try:
        start(sys.argv[1], sys.argv[3:])
    except RuntimeError as err:
        print("refused:", err, flush=True)
atexit.register(start_after_the_kill)
import analyze_common.programs
end(sys.argv[2])
"""

BEFORE_THE_FIRST_START = """
import atexit, subprocess, sys
import analyze_common.programs as programs
def report():
    try:
        process.wait(5)
        print("killed", flush=True)
    except subprocess.TimeoutExpired:
        print("still running", flush=True)
atexit.register(report)
process = programs.start_program(lambda: subprocess.Popen(sys.argv[1:]))
"""


def _run(script, *args):
    """Run the script with its output in files: a pipe would make this wait for a program the script leaves running."""
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    with tempfile.TemporaryFile("w+", encoding="utf-8") as out, tempfile.TemporaryFile("w+", encoding="utf-8") as err:
        code = subprocess.run([sys.executable, "-c", script, *args], env=env, stdout=out, stderr=err, timeout=60).returncode
        out.seek(0)
        err.seek(0)
        return types.SimpleNamespace(returncode=code, stdout=out.read(), stderr=err.read())


def _needs_the_end(end):
    if end == "terminate":
        pytest.importorskip("AppKit")


@pytest.mark.parametrize("end", ENDS)
@pytest.mark.parametrize("start", STARTS)
def test_a_program_being_started_as_the_process_ends_is_killed(start, end, heartbeat):
    _needs_the_end(end)
    result = _run(STARTING, start, end, *heartbeat.args)
    assert result.returncode == 0, result.stderr
    assert heartbeat.file.exists()
    assert heartbeat.stopped()


@pytest.mark.parametrize("end", ENDS)
@pytest.mark.parametrize("start", STARTS)
def test_a_first_program_started_while_the_atexit_functions_run_is_killed(start, end, heartbeat):
    _needs_the_end(end)
    result = _run(STARTING_IN_ATEXIT, start, end, *heartbeat.args)
    assert result.returncode == 0, result.stderr
    assert heartbeat.file.exists()
    assert heartbeat.stopped()


@pytest.mark.parametrize("end", ENDS)
@pytest.mark.parametrize("start", STARTS)
def test_a_program_is_not_started_after_the_kill(start, end, heartbeat):
    _needs_the_end(end)
    result = _run(AFTER_THE_KILL, start, end, *heartbeat.args)
    assert "refused: Not starting a program" in result.stdout, result.stderr
    assert result.returncode == 0, result.stderr
    assert not heartbeat.file.exists()


def test_the_kill_runs_before_what_was_registered_before_the_first_start(heartbeat):
    result = _run(BEFORE_THE_FIRST_START, *heartbeat.args)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "killed"


def test_a_start_that_fails_leaves_the_next_start_free():
    def fail():
        raise FileNotFoundError("no such program")

    for _ in range(2):
        with pytest.raises(FileNotFoundError):
            programs.start_program(fail)


def test_returns_what_start_returns():
    process = programs.start_program(lambda: subprocess.Popen([sys.executable, "-c", "pass"]))
    assert process.wait(30) == 0


def test_the_kill_stops_a_running_program_and_refuses_the_next_start(monkeypatch, heartbeat):
    monkeypatch.setattr(programs, "_ending", False)
    monkeypatch.setattr(programs, "_programs", weakref.WeakSet())
    process = programs.start_program(lambda: subprocess.Popen(heartbeat.args))
    assert process.poll() is None
    programs._kill_programs()
    assert process.wait(30) != 0
    with pytest.raises(RuntimeError, match="Not starting a program"):
        programs.start_program(lambda: pytest.fail("started after the kill"))
