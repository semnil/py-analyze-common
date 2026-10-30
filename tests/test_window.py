import ctypes
import types

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

