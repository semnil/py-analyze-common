"""Auto-update client shared by the analyze-* GUIs.

Each GitHub release carries a manifest (``latest.json``) naming the installer
for every platform and an Ed25519 signature over a statement binding the
product, the version, the platform and the installer's SHA-256.  The app
fetches the manifest of the latest release, downloads the installer for its
own platform, verifies the signature against the public key built into the
app, and hands off to the platform's installer:

- Windows: the Inno Setup installer runs silently (``INSTALLER_ARGS``), waits
  for the app's mutex to disappear, and starts the app again.
- macOS: the app copies the ``.app`` out of the DMG, swaps it with the running
  bundle, and leaves a shell behind that opens the new bundle once this
  process has exited.
"""

import base64
import hashlib
import http.client
import json
import os
import plistlib
import re
import shlex
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from analyze_common import ed25519
from analyze_common.platform import IS_FROZEN, IS_MAC, IS_WINDOWS, subprocess_kwargs

MANIFEST_NAME = "latest.json"
STATEMENT_TAG = "analyze-update-v1"
PLATFORM_WINDOWS = "windows-x86_64"
PLATFORM_MAC = "darwin-aarch64"
PLATFORMS = (PLATFORM_WINDOWS, PLATFORM_MAC)

CHECK_TIMEOUT_SEC = 10.0
# Whole download, from the request to the last byte.  Each read waits at most
# READ_TIMEOUT_SEC, so a stalled transfer ends within that past the deadline.
DOWNLOAD_DEADLINE_SEC = 600.0
READ_TIMEOUT_SEC = 30.0
MAX_MANIFEST_BYTES = 64 * 1024
MAX_DOWNLOAD_BYTES = 1024 * 1024 * 1024

# Inno Setup switches for an update run.  /UPDATE=1 is read by the shared
# installer/auto_update.iss, which waits for the app to exit and relaunches it.
INSTALLER_ARGS = "/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /UPDATE=1"

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?")
_ASSET_NAME_RE = re.compile(r"[A-Za-z0-9._-]+")
_ERROR_CANCELLED = 1223  # Windows: the user declined an elevation prompt
# Makes a PyInstaller bootloader started from this process (the relaunched or
# installed app) start as an independent instance rather than as a worker of
# this one, whose _PYI_* variables it would otherwise inherit.
_RESET_PYINSTALLER_ENV = ("PYINSTALLER_RESET_ENVIRONMENT", "1")
_RENAME_SWAP = 0x2


class UpdateError(Exception):
    """An update check, download or install that did not complete."""


@dataclass(frozen=True)
class UpdateConfig:
    """What identifies one app's releases and signing key."""

    product: str            # signed into every statement, e.g. "analyze-loudness"
    repo: str               # GitHub "owner/name"
    current_version: str
    public_key: str         # base64 of the raw 32-byte Ed25519 public key
    temp_prefix: str        # prefix of the temp directories an update creates
    mutex_name: str = ""    # Windows: the mutex the installer waits on
    releases_url: str = ""  # defaults to https://github.com/{repo}/releases

    @property
    def releases(self) -> str:
        return (self.releases_url or f"https://github.com/{self.repo}/releases").rstrip("/")

    @property
    def manifest_url(self) -> str:
        return f"{self.releases}/latest/download/{MANIFEST_NAME}"

    @property
    def download_prefix(self) -> str:
        return f"{self.releases}/download/"

    def asset_url(self, tag: str, name: str) -> str:
        return f"{self.download_prefix}{tag}/{name}"


@dataclass(frozen=True)
class Update:
    version: str
    platform: str
    url: str
    signature: bytes


@dataclass(frozen=True)
class Handoff:
    """What the app does once it has answered the install request.

    exit_mode "close": quit the normal way (the installer is running).
    exit_mode "immediate": ``os._exit`` right after the answer -- the bundle on
    disk is already the new version, so nothing may be imported any more.
    exit_mode None: keep running; ``restart_error`` says why the installed
    update could not be started.
    """

    exit_mode: str | None
    restart_error: str | None = None


def parse_version(text: str) -> tuple:
    """Sort key for ``X.Y.Z`` or ``X.Y.Z-pre`` (SemVer precedence)."""
    match = _VERSION_RE.fullmatch(text) if isinstance(text, str) else None
    if not match:
        raise UpdateError(f"Not a version number: {text!r}")
    core = tuple(int(part) for part in match.groups()[:3])
    pre = match.group(4)
    if pre is None:
        return core + ((1,),)
    ids = tuple((0, int(part), "") if part.isdigit() else (1, 0, part) for part in pre.split("."))
    return core + ((0, ids),)


def is_newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


def platform_key() -> str | None:
    """Manifest key for this machine, or None where no installer is published."""
    import platform

    machine = platform.machine().lower()
    if IS_WINDOWS and machine in ("amd64", "x86_64"):
        return PLATFORM_WINDOWS
    if IS_MAC and machine == "arm64":
        return PLATFORM_MAC
    return None


def statement(product: str, version: str, platform: str, sha256_hex: str) -> bytes:
    """The bytes a manifest signature covers."""
    for field in (product, version, platform, sha256_hex):
        if not field or "\n" in field:
            raise UpdateError(f"Invalid statement field: {field!r}")
    return f"{STATEMENT_TAG}\n{product}\n{version}\n{platform}\n{sha256_hex}\n".encode("utf-8")


def _public_key_bytes(config: UpdateConfig) -> bytes:
    try:
        key = base64.b64decode(config.public_key, validate=True)
    except ValueError as e:
        raise UpdateError("The app's update key is not valid base64") from e
    if len(key) != 32:
        raise UpdateError("The app's update key is not an Ed25519 public key")
    return key


def _strip_query(url: str) -> str:
    return url.split("?", 1)[0]


class _SameSchemeRedirect(urllib.request.HTTPRedirectHandler):
    """Follow redirects only when they keep the scheme of the request."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old = urllib.parse.urlsplit(req.full_url).scheme
        new = urllib.parse.urlsplit(newurl).scheme
        if new != old:
            raise UpdateError(f"Refused a redirect from {old} to {new}: {_strip_query(newurl)}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _ssl_context() -> ssl.SSLContext:
    """TLS context trusting certifi's CA bundle (a frozen app has no other)."""
    try:
        import certifi
    except ImportError as e:
        raise UpdateError("certifi is not installed") from e
    return ssl.create_default_context(cafile=certifi.where())


def _open(config: UpdateConfig, url: str, timeout: float):
    handlers: list = [_SameSchemeRedirect()]
    if urllib.parse.urlsplit(url).scheme == "https":
        handlers.append(urllib.request.HTTPSHandler(context=_ssl_context()))
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(
        url, headers={"User-Agent": f"{config.product}/{config.current_version}"})
    try:
        return opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise UpdateError(f"HTTP {e.code} from {_strip_query(e.geturl() or url)}") from e
    except urllib.error.URLError as e:
        raise UpdateError(f"Could not reach {_strip_query(url)}: {e.reason}") from e
    except (OSError, http.client.HTTPException) as e:
        raise UpdateError(f"Could not reach {_strip_query(url)}: {e}") from e


def _validate_asset_url(config: UpdateConfig, url) -> str:
    """Accept only ``{releases}/download/{tag}/{name}`` of the app's own repo."""
    if not isinstance(url, str) or not url.startswith(config.download_prefix):
        raise UpdateError(f"The manifest names a download outside {config.download_prefix}")
    rest = url[len(config.download_prefix):].split("/")
    if len(rest) != 2 or any(p in (".", "..") or not _ASSET_NAME_RE.fullmatch(p) for p in rest):
        raise UpdateError("The manifest's download URL is not a release asset")
    return url


def parse_manifest(config: UpdateConfig, manifest, platform: str) -> Update | None:
    """The update a manifest offers this platform, or None when it is not newer."""
    if not isinstance(manifest, dict):
        raise UpdateError("The update manifest is not a JSON object")
    version = manifest.get("version")
    if not is_newer(version, config.current_version):
        return None
    platforms = manifest.get("platforms")
    entry = platforms.get(platform) if isinstance(platforms, dict) else None
    if not isinstance(entry, dict):
        raise UpdateError(f"Version {version} has no update for {platform}")
    url = _validate_asset_url(config, entry.get("url"))
    try:
        signature = base64.b64decode(entry.get("signature") or "", validate=True)
    except (TypeError, ValueError) as e:
        raise UpdateError("The manifest's signature is not valid base64") from e
    if len(signature) != 64:
        raise UpdateError("The manifest's signature is not an Ed25519 signature")
    return Update(version=version, platform=platform, url=url, signature=signature)


def fetch_update(config: UpdateConfig, platform: str | None = None) -> Update | None:
    """Ask the latest release whether it is newer than the running version."""
    platform = platform or platform_key()
    if platform is None:
        raise UpdateError("No update is published for this platform")
    with _open(config, config.manifest_url, CHECK_TIMEOUT_SEC) as response:
        try:
            raw = response.read(MAX_MANIFEST_BYTES + 1)
        except (OSError, http.client.HTTPException) as e:
            raise UpdateError(f"Reading the update manifest failed: {e}") from e
    if len(raw) > MAX_MANIFEST_BYTES:
        raise UpdateError("The update manifest is too large")
    try:
        manifest = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise UpdateError("The update manifest is not valid JSON") from e
    return parse_manifest(config, manifest, platform)


def download(config: UpdateConfig, update: Update, dest_dir: Path, *,
             deadline: float = DOWNLOAD_DEADLINE_SEC,
             max_bytes: int = MAX_DOWNLOAD_BYTES) -> Path:
    """Download the update into ``dest_dir`` and verify its signature.

    A file that fails any check -- size, deadline, signature -- is deleted
    before the error is raised, so a returned path is always verified.
    """
    key = _public_key_bytes(config)
    path = Path(dest_dir) / update.url.rsplit("/", 1)[1]
    digest = hashlib.sha256()
    started = time.monotonic()
    try:
        with _open(config, update.url, READ_TIMEOUT_SEC) as response:
            length = response.headers.get("Content-Length")
            if length and length.isdigit() and int(length) > max_bytes:
                raise UpdateError(f"The update is larger than {max_bytes} bytes")
            total = 0
            with open(path, "wb") as f:
                while True:
                    try:
                        chunk = response.read(65536)
                    except (OSError, http.client.HTTPException) as e:
                        raise UpdateError(f"The download was interrupted: {e}") from e
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise UpdateError(f"The update is larger than {max_bytes} bytes")
                    if time.monotonic() - started > deadline:
                        raise UpdateError(f"The download did not finish within {deadline:.0f} s")
                    digest.update(chunk)
                    f.write(chunk)
            if length and length.isdigit() and total != int(length):
                raise UpdateError(f"The download ended at {total} of {length} bytes")
        message = statement(config.product, update.version, update.platform, digest.hexdigest())
        if not ed25519.verify(key, message, update.signature):
            raise UpdateError("The downloaded update does not match its signature")
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    return path


def running_bundle() -> Path | None:
    """The ``.app`` a frozen macOS process runs from, or None."""
    if not (IS_MAC and IS_FROZEN):
        return None
    executable = Path(os.path.abspath(sys.executable))
    if executable.parent.name != "MacOS" or executable.parent.parent.name != "Contents":
        return None
    app = executable.parent.parent.parent
    return app if app.suffix == ".app" else None


def _tool_kwargs() -> dict:
    """subprocess kwargs for the system tools an install runs (C locale)."""
    kwargs = subprocess_kwargs()
    env = dict(kwargs.get("env") or os.environ)
    env["LC_ALL"] = "C"
    kwargs["env"] = env
    return kwargs


def _run_tool(args: list, what: str) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(args, capture_output=True, text=True, **_tool_kwargs())
    except OSError as e:
        raise UpdateError(f"{what} failed: {e}") from e
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip()[-200:]
        raise UpdateError(f"{what} failed (exit {result.returncode}): {tail}")
    return result


def _bundle_info(app: Path) -> dict:
    try:
        with open(app / "Contents" / "Info.plist", "rb") as f:
            info = plistlib.load(f)
    except (OSError, plistlib.InvalidFileException, ValueError) as e:
        raise UpdateError(f"Could not read {app.name}'s Info.plist: {e}") from e
    if not isinstance(info, dict):
        raise UpdateError(f"{app.name}'s Info.plist is not a dictionary")
    return info


def _team_id(app: Path) -> str | None:
    """The Developer ID team that signed ``app``, or None when it has none."""
    try:
        result = subprocess.run(["/usr/bin/codesign", "--display", "--verbose=2", str(app)],
                                capture_output=True, text=True, **_tool_kwargs())
    except OSError as e:
        raise UpdateError(f"codesign failed: {e}") from e
    if result.returncode != 0:
        return None
    for line in result.stderr.splitlines():
        if line.startswith("TeamIdentifier="):
            team = line.split("=", 1)[1].strip()
            return None if team == "not set" else team
    return None


def other_instances(executable: Path) -> list[int]:
    """PIDs of other processes running ``executable`` (macOS ``ps``)."""
    result = _run_tool(["/bin/ps", "-axww", "-o", "pid=,command="], "Listing processes")
    executable_path = str(executable)
    process_ids = []
    for line in result.stdout.splitlines():
        process_id, _, command = line.strip().partition(" ")
        command = command.lstrip()
        if (process_id.isdigit() and int(process_id) != os.getpid()
                and (command == executable_path or command.startswith(executable_path + " "))):
            process_ids.append(int(process_id))
    return process_ids


def _refuse_other_instances() -> None:
    # Another instance would keep running from a bundle whose files are
    # replaced under it.
    process_ids = other_instances(Path(os.path.abspath(sys.executable)))
    if process_ids:
        raise UpdateError(f"Another window of the app is open (process {process_ids[0]}); quit it, then update again")


def _same_volume_dir(app: Path) -> Path:
    """A writable place on the app's volume (renames do not cross volumes)."""
    device = os.lstat(app).st_dev
    for candidate in (Path(tempfile.gettempdir()), app.parent):
        try:
            if os.stat(candidate).st_dev == device:
                return candidate
        except OSError:
            continue
    raise UpdateError("No folder on the app's disk to prepare the update in")


def stage_mac_bundle(dmg: Path, current: Path, version: str, stage_dir: Path) -> Path:
    """Copy the new ``.app`` out of ``dmg`` into ``stage_dir`` and vet it.

    The copy must carry the running bundle's identifier and the offered
    version; when the running bundle is signed by a team, the copy must be
    signed by the same team and pass a strict deep verification.
    """
    mount = Path(tempfile.mkdtemp(prefix="mount_", dir=stage_dir))
    _run_tool(["/usr/bin/hdiutil", "attach", "-readonly", "-nobrowse", "-noautoopen",
               "-mountpoint", str(mount), str(dmg)], "Opening the update image")
    try:
        apps = [p for p in mount.iterdir() if p.suffix == ".app" and p.is_dir() and not p.is_symlink()]
        if len(apps) != 1:
            raise UpdateError(f"The update image holds {len(apps)} apps, expected 1")
        staged = stage_dir / current.name
        _run_tool(["/usr/bin/ditto", str(apps[0]), str(staged)], "Copying the update")
    finally:
        try:
            _run_tool(["/usr/bin/hdiutil", "detach", str(mount)], "Closing the update image")
        except UpdateError:
            _run_tool(["/usr/bin/hdiutil", "detach", "-force", str(mount)], "Closing the update image")
        try:
            mount.rmdir()
        except OSError:
            pass
    new_info, current_info = _bundle_info(staged), _bundle_info(current)
    if new_info.get("CFBundleIdentifier") != current_info.get("CFBundleIdentifier"):
        raise UpdateError("The update is a different app")
    if new_info.get("CFBundleShortVersionString") != version:
        raise UpdateError(f"The update image holds version {new_info.get('CFBundleShortVersionString')}, not {version}")
    team = _team_id(current)
    if team is not None:
        if _team_id(staged) != team:
            raise UpdateError("The update is not signed by the same developer")
        _run_tool(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(staged)],
                  "Verifying the update's code signature")
    return staged


def _swap(a: Path, b: Path) -> None:
    """Exchange two paths in one step (``renamex_np`` with ``RENAME_SWAP``)."""
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    renamex_np = libc.renamex_np
    renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    renamex_np.restype = ctypes.c_int
    if renamex_np(os.fsencode(a), os.fsencode(b), _RENAME_SWAP) != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err), str(a))


def _applescript_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def privileged_replace_command(target: Path, staged: Path, backup: Path) -> str:
    """Shell command moving ``staged`` onto ``target``, ``target`` to ``backup``,
    and putting ``target`` back when the second move fails."""
    quoted_target, quoted_staged, quoted_backup = (shlex.quote(str(p)) for p in (target, staged, backup))
    return (f"/bin/mv -f {quoted_target} {quoted_backup} && {{ /bin/mv -f {quoted_staged} {quoted_target} "
            f"|| {{ /bin/mv -f {quoted_backup} {quoted_target}; exit 1; }}; }}")


def _privileged_replace(target: Path, staged: Path, backup: Path) -> None:
    script = ("do shell script "
              + _applescript_string(privileged_replace_command(target, staged, backup))
              + " with administrator privileges")
    try:
        result = subprocess.run(["/usr/bin/osascript", "-e", script],
                                capture_output=True, text=True, **_tool_kwargs())
    except OSError as e:
        raise UpdateError(f"Replacing the app failed: {e}") from e
    if result.returncode != 0:
        if "-128" in result.stderr:
            raise UpdateError("Administrator authorization was cancelled")
        raise UpdateError(f"Replacing the app failed: {result.stderr.strip()[-200:]}")


def replace_bundle(target: Path, staged: Path, backup: Path) -> Path:
    """Put ``staged`` at ``target``.  Returns where the previous app now is.

    Swaps in one step where the file system can, else moves the current app
    to ``backup`` and the new one in, restoring the current app when the
    second move fails.  A permission error asks for administrator rights.
    """
    try:
        _swap(staged, target)
        return staged
    except PermissionError:
        _privileged_replace(target, staged, backup)
        return backup
    except OSError:
        pass
    try:
        os.rename(target, backup)
    except PermissionError:
        _privileged_replace(target, staged, backup)
        return backup
    except OSError as e:
        raise UpdateError(f"Moving the current app aside failed: {e}") from e
    try:
        os.rename(staged, target)
    except OSError as e:
        try:
            os.rename(backup, target)
        except OSError as restore:
            raise UpdateError(f"Installing the update failed ({e}), and the previous app "
                              f"could not be put back; it is at {backup} ({restore})") from e
        raise UpdateError(f"Installing the update failed: {e}") from e
    return backup


def _relaunch_after_exit(target: Path, cleanup: Path, process_id: int | None = None,
                         opener: str = "/usr/bin/open") -> None:
    """Open ``target`` once process ``process_id`` (this one) has exited, then remove ``cleanup``."""
    script = 'while kill -0 "$1" 2>/dev/null; do sleep 0.2; done; "$4" "$2"; rm -rf "$3"'
    kwargs = subprocess_kwargs()
    env = dict(kwargs.pop("env", None) or os.environ)
    env[_RESET_PYINSTALLER_ENV[0]] = _RESET_PYINSTALLER_ENV[1]
    subprocess.Popen(
        ["/bin/sh", "-c", script, "sh", str(process_id or os.getpid()), str(target), str(cleanup), opener],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True, close_fds=True, env=env, **kwargs)


def _launch_installer(path: Path) -> None:
    """Start the Windows installer, which asks for elevation (UAC) itself.

    The installer, and the app it starts again, inherit this environment.
    """
    os.environ[_RESET_PYINSTALLER_ENV[0]] = _RESET_PYINSTALLER_ENV[1]
    try:
        os.startfile(str(path), "open", INSTALLER_ARGS)
    except OSError as e:
        if getattr(e, "winerror", None) == _ERROR_CANCELLED:
            raise UpdateError("The installer was cancelled") from e
        raise UpdateError(f"Could not start the installer: {e}") from e


_mutex_handle = None


def hold_instance_mutex(name: str) -> None:
    """Windows: hold the named mutex the installer waits on, for the process's life."""
    global _mutex_handle
    if not IS_WINDOWS or not name or _mutex_handle:
        return
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    _mutex_handle = kernel32.CreateMutexW(None, False, name)


class Updater:
    """One app's update state: the update the last check offered, and the install."""

    def __init__(self, config: UpdateConfig):
        self.config = config
        self._lock = threading.Lock()
        self._pending: Update | None = None
        self._busy = False
        self._replaced = False

    def supported(self) -> bool:
        """True in a packaged build on a platform that has an installer."""
        if not IS_FROZEN or platform_key() is None:
            return False
        if IS_MAC:
            return running_bundle() is not None
        return IS_WINDOWS

    def status(self) -> dict:
        return {"current": self.config.current_version, "supported": self.supported()}

    def check(self) -> str | None:
        """The newer version the latest release offers, or None."""
        update = fetch_update(self.config)
        with self._lock:
            self._pending = update
        return update.version if update else None

    def install(self, version: str) -> Handoff:
        """Download, verify and hand off the update the last check offered."""
        if not self.supported():
            raise UpdateError("Updates can only be installed in the packaged app")
        with self._lock:
            if self._busy or self._replaced:
                raise UpdateError("An update is already being installed")
            update = self._pending
            if update is None or update.version != version:
                raise UpdateError(f"Version {version} was not offered by the last check")
            self._busy = True
        try:
            if IS_WINDOWS:
                return self._install_windows(update)
            return self._install_mac(update)
        except OSError as e:
            raise UpdateError(str(e)) from e
        finally:
            with self._lock:
                self._busy = False

    def _install_windows(self, update: Update) -> Handoff:
        # The installer runs from this directory after the app has exited, so
        # it is left in place; the app's own temp sweep removes it later.
        stage = Path(tempfile.mkdtemp(prefix=self.config.temp_prefix))
        try:
            installer = download(self.config, update, stage)
            _launch_installer(installer)
        except BaseException:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        return Handoff("close")

    def _install_mac(self, update: Update) -> Handoff:
        current = running_bundle()
        if current is None:
            raise UpdateError("The app is not running from an application bundle")
        if "/AppTranslocation/" in str(current) or str(current).startswith("/Volumes/"):
            raise UpdateError("Move the app into the Applications folder, then update again")
        _refuse_other_instances()
        root = _same_volume_dir(current)
        # Hidden when it has to sit next to the app rather than in the temp dir.
        prefix = self.config.temp_prefix if root == Path(tempfile.gettempdir()) else "." + self.config.temp_prefix
        stage = Path(tempfile.mkdtemp(prefix=prefix, dir=root))
        download_dir = None
        try:
            download_dir = Path(tempfile.mkdtemp(prefix=self.config.temp_prefix))
            dmg = download(self.config, update, download_dir)
            staged = stage_mac_bundle(dmg, current, update.version, stage)
        except BaseException:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        finally:
            if download_dir is not None:
                shutil.rmtree(download_dir, ignore_errors=True)
        try:
            _refuse_other_instances()
            replace_bundle(current, staged, stage / "previous.app")
        except BaseException:
            # Kept when the current app is not back in place: its only copy is in there.
            if os.path.lexists(current):
                shutil.rmtree(stage, ignore_errors=True)
            raise
        with self._lock:
            self._replaced = True
        try:
            os.utime(current)
        except OSError:
            pass
        try:
            _relaunch_after_exit(current, stage)
        except OSError as e:
            return Handoff(None, restart_error=str(e))
        return Handoff("immediate")
