import base64
import http.client
import json
import socket
import sys
import threading
import types
from http.server import ThreadingHTTPServer

import pytest

from analyze_common import server
from analyze_common.update import Handoff, UpdateError


class FakeUpdater:
    def __init__(self):
        self.launch = True
        self.checked = "1.2.3"
        self.handoff = Handoff("close")
        self.error = None

    def status(self):
        return {"current": "1.0.0", "supported": True, "launch_check": self.launch}

    def launch_check(self):
        return self.launch

    def set_launch_check(self, on):
        if self.error:
            raise self.error
        self.launch = on

    def check(self):
        if self.error:
            raise self.error
        return self.checked

    def install(self, version):
        if self.error:
            raise self.error
        self.installed = version
        return self.handoff


class FakeUiSettings:
    def script(self):
        return b"window.analyzeSettingsStored = {};"

    def update(self, changes):
        if not isinstance(changes, dict) or len(changes) != 1:
            raise ValueError("expected one setting")
        return {"theme": "dark", "lang": None}


class FakeWindow:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def create_file_dialog(self, kind, **kwargs):
        self.calls.append((kind, kwargs))
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def app(tmp_path, monkeypatch):
    """A consumer handler on a local server, with fake state, and a client for it."""
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "webview", types.SimpleNamespace(OPEN_DIALOG="open", SAVE_DIALOG="save"))
    state = types.SimpleNamespace(updater=FakeUpdater(), ui=FakeUiSettings(), window=FakeWindow(),
                                  lock=threading.Lock(), exits=[], closed=threading.Semaphore(0))

    class Handler(server.GuiHandler):
        frontend_dir = tmp_path
        save_image_name = "app_result.png"
        _AUDIO_TYPES = ("Audio Files (*.wav)",)
        _MAX_BODY = 64

        def updater(self):
            return state.updater

        def ui_settings(self):
            return state.ui

        def window(self):
            return state.window

        def dialog_lock(self):
            return state.lock

        def exit_for_update(self, exit_mode):
            state.exits.append(exit_mode)

        def do_POST(self):
            if not self._check_host() or not self._check_content_type():
                return
            self._shared_handlers()[self.path]()

    class Server(ThreadingHTTPServer):
        def shutdown_request(self, request):
            super().shutdown_request(request)
            state.closed.release()

    httpd = Server(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    state.port = httpd.server_address[1]

    def request(method, path, body=None, content_type="application/json", host=None):
        """Send one request and return once the server has closed it, past what the handler does after answering."""
        connection = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=10)
        data = body if isinstance(body, bytes) or body is None else json.dumps(body).encode()
        headers = {"Content-Type": content_type}
        if host:
            headers["Host"] = host
        connection.request(method, path, body=data, headers=headers)
        response = connection.getresponse()
        payload = response.read()
        connection.close()
        assert state.closed.acquire(timeout=10)
        return response, payload

    state.request = request
    yield state
    httpd.shutdown()
    httpd.server_close()


def _json(payload):
    return json.loads(payload)


def test_refuses_a_host_that_is_not_loopback(app):
    response, _ = app.request("GET", "/index.html", host="evil.example:8080")
    assert response.status == 403


@pytest.mark.parametrize("path, name, content_type", [
    ("/common/common.css", "common.css", "text/css; charset=utf-8"),
    ("/common/update.js", "update.js", "text/javascript; charset=utf-8"),
    ("/common/i18n.js", "i18n.js", "text/javascript; charset=utf-8"),
    ("/common/boot.js", "boot.js", "text/javascript; charset=utf-8"),
    ("/common/ui.js", "ui.js", "text/javascript; charset=utf-8"),
])
def test_serves_the_shared_assets(app, path, name, content_type):
    from analyze_common.web import WEB_DIR
    response, payload = app.request("GET", path)
    assert response.status == 200
    assert response.getheader("Content-Type") == content_type
    assert payload == (WEB_DIR / name).read_bytes()


def test_serves_the_stored_settings_uncached_and_the_frontend(app):
    response, payload = app.request("GET", "/common/settings.js?v=1")
    assert (response.status, response.getheader("Cache-Control"), payload) == \
        (200, "no-store", b"window.analyzeSettingsStored = {};")
    response, payload = app.request("GET", "/index.html")
    assert (response.status, payload) == (200, b"<html></html>")


def _post_head(path, length):
    return (f"POST {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n"
            f"Content-Length: {length}\r\n\r\n").encode()


def _read_until_closed(client):
    received = b""
    while chunk := client.recv(4096):
        received += chunk
    return received


def test_a_body_sent_after_the_answer_leaves_the_response_to_the_client(app):
    with socket.create_connection(("127.0.0.1", app.port), timeout=10) as client:
        client.sendall(_post_head("/update/status", 2))
        # A server that does not wait for the client closes within this time.
        app.closed.acquire(timeout=0.2)
        client.sendall(b"{}")
        assert _read_until_closed(client).startswith(b"HTTP/1.0 200")
    assert app.closed.acquire(timeout=10)


def test_a_client_that_stays_connected_does_not_hold_the_handler(app, monkeypatch):
    monkeypatch.setattr(server.GuiHandler, "_LINGER_SEC", 0.05)
    with socket.create_connection(("127.0.0.1", app.port), timeout=10) as client:
        client.sendall(_post_head("/update/status", 0))
        assert _read_until_closed(client).startswith(b"HTTP/1.0 200")
        assert app.closed.acquire(timeout=10)


def test_refuses_another_content_type(app):
    response, payload = app.request("POST", "/settings", {"theme": "dark"}, content_type="text/plain")
    assert response.status == 415
    assert _json(payload) == {"error": "Content-Type must be application/json"}


def test_settings(app):
    response, payload = app.request("POST", "/settings", {"theme": "dark"})
    assert (response.status, _json(payload)) == (200, {"theme": "dark", "lang": None})
    response, payload = app.request("POST", "/settings", b"{broken")
    assert response.status == 400


@pytest.mark.parametrize("body", [b"{broken", b"[1]", json.dumps({"launch_check": "yes"}).encode(), b"x" * 100])
def test_launch_check_needs_a_boolean(app, body):
    response, payload = app.request("POST", "/update/settings", body)
    assert (response.status, _json(payload)) == (400, {"error": "'launch_check' must be true or false"})


def test_launch_check_is_stored(app):
    response, payload = app.request("POST", "/update/settings", {"launch_check": False})
    assert (response.status, _json(payload), app.updater.launch) == (200, {"launch_check": False}, False)
    app.updater.error = UpdateError("disk full")
    response, payload = app.request("POST", "/update/settings", {"launch_check": True})
    assert (response.status, _json(payload)) == (500, {"error": "disk full"})


def test_update_status_and_check(app):
    response, payload = app.request("POST", "/update/status", {})
    assert _json(payload) == {"current": "1.0.0", "supported": True, "launch_check": True}
    response, payload = app.request("POST", "/update/check", {})
    assert (response.status, _json(payload)) == (200, {"available": True, "version": "1.2.3"})
    app.updater.checked = None
    response, payload = app.request("POST", "/update/check", {})
    assert _json(payload) == {"available": False}
    app.updater.error = UpdateError("offline")
    response, payload = app.request("POST", "/update/check", {})
    assert (response.status, _json(payload)) == (502, {"error": "offline"})


@pytest.mark.parametrize("handoff, expected, exits", [
    (Handoff("close"), {"restarting": True}, ["close"]),
    (Handoff("immediate"), {"restarting": True}, ["immediate"]),
    (Handoff(None, restart_error="could not open"), {"installed": True, "restart_error": "could not open"}, []),
])
def test_update_install_hands_the_exit_to_the_app(app, handoff, expected, exits):
    app.updater.handoff = handoff
    response, payload = app.request("POST", "/update/install", {"version": "1.2.3"})
    assert (response.status, _json(payload), app.exits, app.updater.installed) == (200, expected, exits, "1.2.3")


@pytest.mark.parametrize("body", [{}, {"version": ""}, {"version": 3}, b"{broken"])
def test_update_install_needs_a_version(app, body):
    response, payload = app.request("POST", "/update/install", body)
    assert (response.status, _json(payload), app.exits) == (400, {"error": "Missing or invalid 'version' field"}, [])


def test_update_install_failure_keeps_the_app(app):
    app.updater.error = UpdateError("bad signature")
    response, payload = app.request("POST", "/update/install", {"version": "1.2.3"})
    assert (response.status, _json(payload), app.exits) == (500, {"error": "bad signature"}, [])


def test_browse_returns_the_chosen_file(app):
    app.window.result = ("/music/a.wav",)
    response, payload = app.request("POST", "/browse", {})
    assert _json(payload) == {"selected": True, "path": "/music/a.wav"}
    assert app.window.calls == [("open", {"file_types": ("Audio Files (*.wav)",)})]
    app.window.result = None
    response, payload = app.request("POST", "/browse", {})
    assert _json(payload) == {"selected": False}


def test_one_dialog_at_a_time(app):
    app.lock.acquire()
    try:
        response, payload = app.request("POST", "/browse", {})
    finally:
        app.lock.release()
    assert (response.status, _json(payload), app.window.calls) == (409, {"error": "A dialog is already open"}, [])


def test_a_dialog_error_is_reported_and_releases_the_lock(app):
    app.window.error = RuntimeError("no display")
    response, payload = app.request("POST", "/browse", {})
    assert (response.status, _json(payload)) == (500, {"error": "File dialog error: no display"})
    assert app.lock.acquire(blocking=False)
    app.lock.release()


def test_save_image_writes_the_png(app, tmp_path):
    target = tmp_path / "out.png"
    app.window.result = str(target)
    data = base64.b64encode(b"\x89PNG fake").decode()
    response, payload = app.request("POST", "/save-image", {"dataUrl": "data:image/png;base64," + data})
    assert _json(payload) == {"saved": True, "path": str(target)}
    assert target.read_bytes() == b"\x89PNG fake"
    assert app.window.calls == [("save", {"save_filename": "app_result.png", "file_types": ("PNG Images (*.png)",)})]


@pytest.mark.parametrize("body, error", [
    (b"{broken", "Invalid JSON body"),
    ({"dataUrl": "data:image/jpeg;base64,AAAA"}, "Missing or invalid 'dataUrl' field"),
])
def test_save_image_refuses_a_bad_body(app, body, error):
    response, payload = app.request("POST", "/save-image", body)
    assert (response.status, _json(payload), app.window.calls) == (400, {"error": error}, [])


def test_save_image_has_its_own_size_limit(app, tmp_path):
    app.window.result = str(tmp_path / "big.png")
    data = base64.b64encode(b"x" * 300).decode()
    response, payload = app.request("POST", "/save-image", {"dataUrl": "data:image/png;base64," + data})
    assert (response.status, _json(payload)["saved"]) == (200, True)


def test_save_image_cancel_does_not_create_a_file(app, tmp_path):
    response, payload = app.request("POST", "/save-image", {"dataUrl": "data:image/png;base64,AAAA"})
    assert (response.status, _json(payload)) == (200, {"saved": False})
    assert list(tmp_path.iterdir()) == [tmp_path / "index.html"]
    assert not app.lock.locked()


def test_save_image_busy_does_not_open_a_dialog(app):
    app.lock.acquire()
    try:
        response, payload = app.request("POST", "/save-image", {"dataUrl": "data:image/png;base64,AAAA"})
    finally:
        app.lock.release()
    assert (response.status, _json(payload), app.window.calls) == (409, {"error": "A dialog is already open"}, [])


def test_save_image_dialog_failure_releases_lock_and_allows_retry(app, tmp_path):
    app.window.error = RuntimeError("dialog failed")
    body = {"dataUrl": "data:image/png;base64," + base64.b64encode(b"image").decode()}
    response, payload = app.request("POST", "/save-image", body)
    assert (response.status, _json(payload)) == (500, {"error": "File dialog error: dialog failed"})
    assert not app.lock.locked()
    app.window.error = None
    target = tmp_path / "retry.png"
    app.window.result = str(target)
    response, payload = app.request("POST", "/save-image", body)
    assert (response.status, _json(payload)["saved"], target.read_bytes()) == (200, True, b"image")


@pytest.mark.parametrize("data, target_name", [("a", "invalid.png"), ("AAAA", "missing/out.png")])
def test_save_image_decode_and_write_failure_are_reported(app, tmp_path, data, target_name):
    target = tmp_path / target_name
    app.window.result = str(target)
    response, payload = app.request("POST", "/save-image", {"dataUrl": "data:image/png;base64," + data})
    assert response.status == 500
    assert payload and _json(payload)["error"].startswith("Failed to write image:")
    assert not target.exists()
    assert not app.lock.locked()


def test_settings_write_failure_is_reported(app):
    def fail(changes):
        raise OSError("settings disk full")

    app.ui.update = fail
    response, payload = app.request("POST", "/settings", {"theme": "dark"})
    assert (response.status, _json(payload)) == (500, {"error": "settings disk full"})


def test_missing_shared_asset_is_a_404(app, monkeypatch, tmp_path):
    monkeypatch.setitem(server.GuiHandler._SHARED_ASSETS, "/common/ui.js", (tmp_path / "missing.js", "text/javascript"))
    response, _ = app.request("GET", "/common/ui.js")
    assert response.status == 404


def test_settings_script_read_failure_is_a_404(app):
    def fail():
        raise OSError("settings unavailable")

    app.ui.script = fail
    response, _ = app.request("GET", "/common/settings.js")
    assert response.status == 404


class _Request:
    def __init__(self, error=None):
        self.sent, self.error = [], error

    def sendall(self, data):
        if self.error:
            raise self.error
        self.sent.append(data)


def test_events_send_nan_as_null():
    handler = types.SimpleNamespace(request=_Request())
    server.GuiHandler._send_event(handler, "progress", value=float("nan"))
    assert handler.request.sent == [b'{"type": "progress", "value": null}\n']


def test_a_closed_connection_ends_the_stream(capsys):
    handler = types.SimpleNamespace(request=_Request(BrokenPipeError("gone")))
    with pytest.raises(server.ClientDisconnected):
        server.GuiHandler._send_event(handler, "progress")
    assert "BrokenPipeError" in capsys.readouterr().err


def test_json_responses_send_nan_as_null(capsys):
    sent = {}
    handler = types.SimpleNamespace(request=_Request(), send_response=lambda status: sent.update(status=status),
                                    send_header=lambda *a: None, end_headers=lambda: None)
    server.GuiHandler._json_response(handler, 200, {"value": float("inf")})
    assert (sent["status"], handler.request.sent) == (200, [b'{"value": null}'])


@pytest.mark.parametrize("result, path", [(None, None), ((), None), ("/a.png", "/a.png"), (("/a.png", "/b.png"), "/a.png")])
def test_the_dialog_result_path_for_the_handler_and_its_consumers(result, path):
    assert server.dialog_result_path(result) == path
    assert server.GuiHandler._dialog_path(result) == path
