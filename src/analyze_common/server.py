"""The request handling both consumers' GUI servers share.

The consumer's handler subclasses ``GuiHandler``: it sets ``frontend_dir``, ``save_image_name`` and ``_AUDIO_TYPES``
(and the size limits when they differ), returns its state from ``updater()``, ``ui_settings()``, ``window()``,
``dialog_lock()`` and ``exit_for_update()``, and routes the shared endpoints from its own ``do_POST`` through
``_shared_handlers()``.
"""

import base64
import json
import traceback
from http.server import SimpleHTTPRequestHandler
from pathlib import Path

from analyze_common.download import sanitize_filename
from analyze_common.json_util import json_safe
from analyze_common.update import UpdateError
from analyze_common.web import BOOT_JS, COMMON_CSS, I18N_JS, UI_JS, UPDATE_JS


class ClientDisconnected(Exception):
    """The client closed the connection while an NDJSON stream was being written."""


class GuiHandler(SimpleHTTPRequestHandler):
    """Serves the consumer's frontend and analyze_common's shared assets, and the endpoints both GUIs have."""

    frontend_dir = None
    save_image_name = "result.png"
    _AUDIO_TYPES = ()
    _ALLOWED_HOSTS = ("127.0.0.1", "localhost")
    _MAX_BODY = 10 * 1024 * 1024
    _MAX_IMAGE_BODY = 50 * 1024 * 1024

    # analyze_common's shared assets, which live outside frontend_dir.
    _SHARED_ASSETS = {
        "/common/common.css": (COMMON_CSS, "text/css; charset=utf-8"),
        "/common/update.js": (UPDATE_JS, "text/javascript; charset=utf-8"),
        "/common/i18n.js": (I18N_JS, "text/javascript; charset=utf-8"),
        "/common/boot.js": (BOOT_JS, "text/javascript; charset=utf-8"),
        "/common/ui.js": (UI_JS, "text/javascript; charset=utf-8"),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(self.frontend_dir), **kwargs)

    def updater(self):
        """The consumer's ``Updater``."""
        raise NotImplementedError

    def ui_settings(self):
        """The consumer's ``UiSettings``."""
        raise NotImplementedError

    def window(self):
        """The consumer's pywebview window, for its native dialogs."""
        raise NotImplementedError

    def dialog_lock(self):
        """The lock that keeps one native dialog open at a time."""
        raise NotImplementedError

    def exit_for_update(self, exit_mode):
        """End the app once an update has been handed off (``Handoff.exit_mode``)."""
        raise NotImplementedError

    def _shared_handlers(self) -> dict:
        """The POST endpoints both GUIs have, by path, for the consumer's ``do_POST`` routing table."""
        return {
            "/save-image": self._handle_save_image,
            "/browse": self._handle_browse,
            "/settings": self._handle_settings,
            "/update/status": self._handle_update_status,
            "/update/settings": self._handle_update_settings,
            "/update/check": self._handle_update_check,
            "/update/install": self._handle_update_install,
        }

    def _check_host(self) -> bool:
        """Reject requests whose Host header is not a loopback literal.

        Defends against DNS rebinding: a malicious page could ask the browser
        to resolve an attacker-controlled name to 127.0.0.1 and talk to this
        server. Rejecting non-loopback Host literals blocks that.
        """
        host = self.headers.get("Host", "")
        host_name = host.split(":", 1)[0] if host else ""
        if host_name not in self._ALLOWED_HOSTS:
            self.send_error(403, "Forbidden: invalid Host")
            return False
        return True

    def _read_json_body(self, max_size: int | None = None) -> dict | None:
        """Read and parse JSON body. Returns None on parse failure."""
        limit = max_size or self._MAX_BODY
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            return None
        if length <= 0:
            return {}
        if length > limit:
            return None
        try:
            return json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, ValueError):
            return None

    @staticmethod
    def _dialog_path(result) -> str | None:
        """Extract file path from pywebview dialog result."""
        if not result:
            return None
        return result if isinstance(result, str) else result[0]

    def do_GET(self):
        if not self._check_host():
            return
        path = self.path.split("?", 1)[0]
        if path == "/common/settings.js":
            self._send_settings_script()
            return
        asset = self._SHARED_ASSETS.get(path)
        if asset:
            self._send_shared_asset(*asset)
            return
        super().do_GET()

    def _send_shared_asset(self, path: Path, content_type: str):
        try:
            body = path.read_bytes()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_settings_script(self):
        """The shared settings.js with the stored theme and language, read anew
        for every page load."""
        try:
            body = self.ui_settings().script()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _check_content_type(self) -> bool:
        """Accept only the Content-Type the frontend sends.  Browsers send
        cross-origin requests with these types only after a CORS preflight,
        which this server never answers."""
        expected = "application/octet-stream" if self.path == "/upload" else "application/json"
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != expected:
            self._json_error(415, f"Content-Type must be {expected}")
            return False
        return True

    def _handle_browse(self):
        import webview
        if not self.dialog_lock().acquire(blocking=False):
            self._json_error(409, "A dialog is already open")
            return
        try:
            result = self.window().create_file_dialog(
                webview.OPEN_DIALOG,
                file_types=self._AUDIO_TYPES,
            )
        except Exception as e:
            traceback.print_exc()
            self._json_error(500, f"File dialog error: {e}")
            return
        finally:
            self.dialog_lock().release()

        file_path = self._dialog_path(result)
        if not file_path:
            self._json_response(200, {"selected": False})
            return
        self._json_response(200, {"selected": True, "path": file_path})

    def _handle_save_image(self):
        import webview
        body = self._read_json_body(max_size=self._MAX_IMAGE_BODY)
        if body is None:
            self._json_error(400, "Invalid JSON body")
            return
        data_url = body.get("dataUrl", "")
        filename = sanitize_filename(body.get("filename", self.save_image_name))

        if not data_url or not data_url.startswith("data:image/png;base64,"):
            self._json_error(400, "Missing or invalid 'dataUrl' field")
            return

        if not self.dialog_lock().acquire(blocking=False):
            self._json_error(409, "A dialog is already open")
            return
        try:
            result = self.window().create_file_dialog(
                webview.SAVE_DIALOG,
                save_filename=filename,
                file_types=("PNG Images (*.png)",),
            )
        except Exception as e:
            traceback.print_exc()
            self._json_error(500, f"File dialog error: {e}")
            return
        finally:
            self.dialog_lock().release()

        save_path = self._dialog_path(result)
        if not save_path:
            self._json_response(200, {"saved": False})
            return
        try:
            png_data = base64.b64decode(data_url.split(",", 1)[1])
            Path(save_path).write_bytes(png_data)
        except (OSError, ValueError) as e:
            self._json_error(500, f"Failed to write image: {e}")
            return
        self._json_response(200, {"saved": True, "path": save_path})

    def _handle_settings(self):
        """Store the theme or the language in the app's settings file."""
        body = self._read_json_body()
        try:
            values = self.ui_settings().update(body)
        except ValueError as err:
            self._json_error(400, str(err))
            return
        except OSError as err:
            self._json_error(500, str(err))
            return
        self._json_response(200, values)

    def _handle_update_status(self):
        self._json_response(200, self.updater().status())

    def _handle_update_settings(self):
        """Store the "Check at launch" setting in the app's settings file."""
        body = self._read_json_body()
        on = body.get("launch_check") if isinstance(body, dict) else None
        if not isinstance(on, bool):
            self._json_error(400, "'launch_check' must be true or false")
            return
        try:
            self.updater().set_launch_check(on)
        except UpdateError as err:
            self._json_error(500, str(err))
            return
        self._json_response(200, {"launch_check": self.updater().launch_check()})

    def _handle_update_check(self):
        try:
            version = self.updater().check()
        except UpdateError as err:
            self._json_error(502, str(err))
            return
        if version is None:
            self._json_response(200, {"available": False})
        else:
            self._json_response(200, {"available": True, "version": version})

    def _handle_update_install(self):
        """Download, verify and hand off the update; the app then exits."""
        body = self._read_json_body()
        version = body.get("version") if isinstance(body, dict) else None
        if not isinstance(version, str) or not version:
            self._json_error(400, "Missing or invalid 'version' field")
            return
        try:
            handoff = self.updater().install(version)
        except UpdateError as err:
            self._json_error(500, str(err))
            return
        if handoff.exit_mode is None:
            self._json_response(200, {"installed": True, "restart_error": handoff.restart_error})
            return
        self._json_response(200, {"restarting": True})
        self.exit_for_update(handoff.exit_mode)

    def _json_response(self, status, obj):
        # A NaN/Inf hidden inside externally-loaded JSON is sanitized on retry,
        # so the client always gets a JSON body; the traceback goes to stderr.
        try:
            body = json.dumps(obj, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (ValueError, TypeError):
            traceback.print_exc()
            body = json.dumps(
                json_safe(obj), ensure_ascii=False, allow_nan=False
            ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        # wfile (SocketIO, wbufsize=0) delegates to socket.send() which may
        # perform a partial write when body exceeds SO_SNDBUF (~128 KB).
        # sendall() loops internally until every byte is delivered.
        self.request.sendall(body)

    def _json_error(self, status, message):
        self._json_response(status, {"error": message})

    def _send_event(self, event_type, **kwargs):
        """One NDJSON line; NaN / Infinity in the payload are sent as null."""
        payload = json_safe({"type": event_type, **kwargs})
        line = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        try:
            self.request.sendall((line + "\n").encode("utf-8"))
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError):
            # The client aborted mid-stream; the traceback goes to stderr.
            traceback.print_exc()
            raise ClientDisconnected()

    def log_message(self, format, *args):
        pass
