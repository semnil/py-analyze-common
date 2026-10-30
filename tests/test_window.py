import ctypes
import types

from analyze_common import window


class _Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


def _window(webview):
    return types.SimpleNamespace(gui=types.SimpleNamespace(webview=webview),
                                 events=types.SimpleNamespace(shown=_Event(), loaded=_Event()))


def test_sets_the_app_user_model_id_on_windows_only(monkeypatch):
    ids = []
    shell32 = types.SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=ids.append)
    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(shell32=shell32), raising=False)
    monkeypatch.setattr(window.sys, "platform", "darwin")
    window.set_app_user_model_id("com.example.app")
    monkeypatch.setattr(window.sys, "platform", "win32")
    window.set_app_user_model_id("com.example.app")
    assert ids == ["com.example.app"]


def test_blocks_external_drop_and_swipe_on_windows(monkeypatch):
    monkeypatch.setattr(window.sys, "platform", "win32")
    settings = types.SimpleNamespace(IsSwipeNavigationEnabled=True)
    webview = types.SimpleNamespace(AllowExternalDrop=True, CoreWebView2=types.SimpleNamespace(Settings=settings))
    win = _window(webview)
    window.block_external_drop(win)
    assert len(win.events.shown.handlers) == len(win.events.loaded.handlers) == 1
    win.events.shown.handlers[0]()
    assert (webview.AllowExternalDrop, settings.IsSwipeNavigationEnabled) == (False, False)


def test_a_webview_without_those_properties_is_left_alone(monkeypatch):
    monkeypatch.setattr(window.sys, "platform", "win32")
    win = _window(types.SimpleNamespace())
    window.block_external_drop(win)
    win.events.loaded.handlers[0]()


def test_registers_nothing_elsewhere(monkeypatch):
    monkeypatch.setattr(window.sys, "platform", "darwin")
    win = _window(types.SimpleNamespace(AllowExternalDrop=True))
    window.block_external_drop(win)
    assert win.events.shown.handlers == win.events.loaded.handlers == []
