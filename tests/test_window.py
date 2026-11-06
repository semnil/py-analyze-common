import ctypes
import os
import subprocess
import sys
import types

import pytest

from analyze_common import window


def test_sets_the_app_user_model_id_on_windows_only(monkeypatch):
    ids = []
    shell32 = types.SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=ids.append)
    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(shell32=shell32), raising=False)
    monkeypatch.setattr(window.sys, "platform", "darwin")
    window.set_app_user_model_id("com.example.app")
    monkeypatch.setattr(window.sys, "platform", "win32")
    window.set_app_user_model_id("com.example.app")
    assert ids == ["com.example.app"]


def _fake_cocoa(monkeypatch, add_observer):
    center = types.SimpleNamespace(addObserverForName_object_queue_usingBlock_=add_observer)
    foundation = types.SimpleNamespace(NSNotificationCenter=types.SimpleNamespace(defaultCenter=lambda: center))
    appkit = types.SimpleNamespace(NSApplicationWillTerminateNotification="will-terminate")
    monkeypatch.setitem(sys.modules, "Foundation", foundation)
    monkeypatch.setitem(sys.modules, "AppKit", appkit)


def test_quit_watch_is_macos_only(monkeypatch):
    watched = []
    _fake_cocoa(monkeypatch, lambda *args: watched.append(args))
    for platform in ("win32", "linux"):
        monkeypatch.setattr(window.sys, "platform", platform)
        window.run_atexit_on_app_quit()
    assert watched == []


def test_will_terminate_arms_the_limit_and_runs_the_atexit_functions(monkeypatch):
    watched = []
    ran = []
    _fake_cocoa(monkeypatch, lambda *args: watched.append(args))
    monkeypatch.setattr(window.atexit, "_run_exitfuncs", lambda: ran.append("atexit"))
    monkeypatch.setattr(window.faulthandler, "dump_traceback_later",
                        lambda seconds, **kwargs: ran.append(("limit", seconds, kwargs)))
    monkeypatch.setattr(window.sys, "platform", "darwin")
    window.run_atexit_on_app_quit()
    assert [args[:3] for args in watched] == [("will-terminate", None, None)]
    assert ran == []
    watched[0][3](object())
    assert ran == [("limit", window._QUIT_LIMIT_SEC, {"file": 2, "exit": True}), "atexit"]


def test_failure_to_watch_for_quit_is_reported_and_does_not_raise(monkeypatch, capsys):
    def refuse(*_args):
        raise RuntimeError("no notification center")

    _fake_cocoa(monkeypatch, refuse)
    monkeypatch.setattr(window.sys, "platform", "darwin")
    window.run_atexit_on_app_quit()
    assert "no notification center" in capsys.readouterr().err


QUIT_SCRIPT = """
import atexit
import sys
import tempfile
from pathlib import Path

import AppKit

from analyze_common.window import run_atexit_on_app_quit

out = Path(sys.argv[1])
in_use = tempfile.TemporaryDirectory(prefix="in_use_", dir=out)
atexit.register(lambda: (out / "atexit_ran").write_text("yes"))
if sys.argv[2] == "watch":
    run_atexit_on_app_quit()
AppKit.NSApplication.sharedApplication().terminate_(None)
"""


@pytest.mark.skipif(sys.platform != "darwin", reason="NSApplication is macOS only")
@pytest.mark.parametrize("mode, left", [("watch", "atexit_ran"), ("plain", "in_use_")])
def test_terminate_runs_atexit_only_when_watched(mode, left, tmp_path):
    pytest.importorskip("AppKit")
    result = subprocess.run([sys.executable, "-c", QUIT_SCRIPT, str(tmp_path), mode], capture_output=True, text=True,
                            timeout=60, env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)})
    assert result.returncode == 0, result.stderr
    names = [path.name for path in tmp_path.iterdir()]
    assert len(names) == 1 and names[0].startswith(left)


STALLED_QUIT_SCRIPT = """
import atexit
import ctypes
import sys
import threading

import AppKit

from analyze_common import window

window._QUIT_LIMIT_SEC = 1
stall = sys.argv[1]
if stall == "atexit":
    atexit.register(lambda: threading.Event().wait())
elif stall == "holding the GIL":
    atexit.register(ctypes.PyDLL(None).pause)
else:
    libc = ctypes.CDLL(None)
    libc.atexit(ctypes.cast(libc.pause, ctypes.c_void_p))
window.run_atexit_on_app_quit()
AppKit.NSApplication.sharedApplication().terminate_(None)
"""


@pytest.mark.skipif(sys.platform != "darwin", reason="NSApplication is macOS only")
@pytest.mark.parametrize("stall", ["atexit", "holding the GIL", "C exit"])
def test_a_stalled_quit_ends_at_the_limit_and_writes_the_stacks(stall):
    pytest.importorskip("AppKit")
    result = subprocess.run([sys.executable, "-c", STALLED_QUIT_SCRIPT, stall], capture_output=True, text=True,
                            timeout=30, env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)})
    assert result.returncode == 1, result.stderr
    assert "Timeout" in result.stderr
