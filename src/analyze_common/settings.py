"""Per-user settings of the analyze-* GUIs, kept in a JSON file outside the webview.

The webview's own storage does not last: pywebview starts in private mode, and
the local server's port, which is part of the page's origin, changes on every
launch.  Settings that have to survive a restart live here instead.
"""

import json
import os
import sys
import tempfile
import threading
from pathlib import Path

from analyze_common.platform import IS_MAC, IS_WINDOWS

SETTINGS_NAME = "settings.json"


def settings_dir(product: str) -> Path:
    """The per-user folder for ``product``'s settings on this OS."""
    if IS_WINDOWS:
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    elif IS_MAC:
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / product


class SettingsStore:
    """A JSON object of settings in one file.

    A missing file reads as no settings.  An unreadable or malformed file also
    reads as no settings, with a warning on stderr, and the next write replaces
    it.  Writes go to a temporary file in the same folder and replace the file
    in one step.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def _read(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            print(f"Ignoring unreadable settings {self.path}: {e}", file=sys.stderr)
            return {}
        if not isinstance(data, dict):
            print(f"Ignoring settings {self.path}: not a JSON object", file=sys.stderr)
            return {}
        return data

    def get(self, key: str, default):
        with self._lock:
            return self._read().get(key, default)

    def set(self, key: str, value) -> None:
        """Store ``value`` under ``key``.  Raises OSError when it cannot be written."""
        with self._lock:
            data = self._read()
            data[key] = value
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".settings-", suffix=".tmp", dir=self.path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    f.write("\n")
                os.replace(tmp, self.path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
