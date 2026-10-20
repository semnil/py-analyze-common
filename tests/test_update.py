"""Tests for analyze_common.update."""

import base64
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

from analyze_common import update as update_client
from analyze_common.update import (
    Handoff, Update, UpdateConfig, UpdateError, Updater, is_newer, parse_version,
    statement,
)

IS_DARWIN = sys.platform == "darwin"


def _config(signer, base="http://127.0.0.1:9/releases", version="1.4.1", **overrides):
    return UpdateConfig(product="analyze-test", repo="semnil/analyze-test",
                        current_version=version, public_key=signer.public_key_b64,
                        temp_prefix="analyzetest_update_", releases_url=base, **overrides)


def _entry(config, signer, version, platform, data, name="App-setup.exe", tag=None):
    tag = tag or f"v{version}"
    digest = hashlib.sha256(data).hexdigest()
    sig = signer.sign(statement(config.product, version, platform, digest))
    return {"url": config.asset_url(tag, name), "signature": base64.b64encode(sig).decode()}


# ---------- versions ----------

class TestVersions:
    @pytest.mark.parametrize("newer,older", [
        ("1.4.2", "1.4.1"),
        ("1.10.0", "1.9.9"),
        ("2.0.0", "1.99.99"),
        ("1.5.0", "1.5.0-rc1"),
        ("1.5.0-rc.2", "1.5.0-rc.1"),
        ("1.5.0-rc.10", "1.5.0-rc.9"),
        ("1.5.0-rc", "1.5.0-beta"),
        ("1.5.0-alpha.beta", "1.5.0-alpha.1"),
        ("1.5.0-alpha.1", "1.5.0-alpha"),
    ])
    def test_ordering(self, newer, older):
        assert is_newer(newer, older)
        assert not is_newer(older, newer)

    def test_equal_is_not_newer(self):
        assert not is_newer("1.4.1", "1.4.1")

    @pytest.mark.parametrize("bad", ["", "1.4", "v1.4.1", "1.4.1.0", "1.4.1 ", "1.4.x", None, 141])
    def test_rejects_non_versions(self, bad):
        with pytest.raises(UpdateError):
            parse_version(bad)


# ---------- statement / platform ----------

class TestStatement:
    def test_exact_bytes(self):
        assert statement("p", "1.2.3", "darwin-aarch64", "ab") == \
            b"analyze-update-v1\np\n1.2.3\ndarwin-aarch64\nab\n"

    @pytest.mark.parametrize("field", ["", "a\nb"])
    def test_rejects_empty_or_multiline_fields(self, field):
        with pytest.raises(UpdateError):
            statement("p", field, "darwin-aarch64", "ab")


class TestPlatformKey:
    @pytest.mark.parametrize("win,mac,machine,expected", [
        (True, False, "AMD64", "windows-x86_64"),
        (True, False, "ARM64", None),
        (False, True, "arm64", "darwin-aarch64"),
        (False, True, "x86_64", None),
        (False, False, "x86_64", None),
    ])
    def test_keys(self, win, mac, machine, expected):
        with mock.patch.object(update_client, "IS_WINDOWS", win), mock.patch.object(update_client, "IS_MAC", mac), \
                mock.patch("platform.machine", return_value=machine):
            assert update_client.platform_key() == expected


# ---------- manifest ----------

class TestParseManifest:
    def test_newer_version_is_offered(self, signer):
        config = _config(signer)
        entry = _entry(config, signer, "1.5.0", "windows-x86_64", b"x")
        update = update_client.parse_manifest(config, {"version": "1.5.0", "platforms": {"windows-x86_64": entry}},
                                   "windows-x86_64")
        assert update == Update("1.5.0", "windows-x86_64", entry["url"], base64.b64decode(entry["signature"]))

    @pytest.mark.parametrize("version", ["1.4.1", "1.4.0", "1.4.1-rc1"])
    def test_same_or_older_is_not_offered(self, signer, version):
        config = _config(signer)
        manifest = {"version": version, "platforms": {}}
        assert update_client.parse_manifest(config, manifest, "windows-x86_64") is None

    def test_missing_platform_is_an_error(self, signer):
        config = _config(signer)
        entry = _entry(config, signer, "1.5.0", "windows-x86_64", b"x")
        with pytest.raises(UpdateError, match="darwin-aarch64"):
            update_client.parse_manifest(config, {"version": "1.5.0", "platforms": {"windows-x86_64": entry}},
                              "darwin-aarch64")

    @pytest.mark.parametrize("manifest", [[], "x", None, {"platforms": {}}, {"version": 1}])
    def test_malformed_manifest(self, signer, manifest):
        with pytest.raises(UpdateError):
            update_client.parse_manifest(_config(signer), manifest, "windows-x86_64")

    @pytest.mark.parametrize("url", [
        "https://example.com/App-setup.exe",
        "http://127.0.0.1:9/releases/download/v1.5.0/App-setup.exe?x=1",
        "http://127.0.0.1:9/releases/download/v1.5.0/App-setup.exe#x",
        "http://127.0.0.1:9/releases/download/../../other/App-setup.exe",
        "http://127.0.0.1:9/releases/download/v1.5.0/..",
        "http://127.0.0.1:9/releases/download/v1.5.0/sub/App-setup.exe",
        "http://127.0.0.1:9/releases/download/v1.5.0/App%20setup.exe",
        "http://127.0.0.1:9/releases/downloadx/v1.5.0/App-setup.exe",
        None,
    ])
    def test_rejects_urls_outside_the_releases(self, signer, url):
        config = _config(signer)
        entry = _entry(config, signer, "1.5.0", "windows-x86_64", b"x")
        entry["url"] = url
        with pytest.raises(UpdateError):
            update_client.parse_manifest(config, {"version": "1.5.0", "platforms": {"windows-x86_64": entry}},
                              "windows-x86_64")

    def test_rejects_another_host_with_the_same_shape(self, signer):
        config = _config(signer)
        host = "http://evil.example/"
        url = host + "x" * (len(config.download_prefix) - len(host) - 1) + "/v1.5.0/App-setup.exe"
        assert len(url) - len("v1.5.0/App-setup.exe") == len(config.download_prefix)
        entry = _entry(config, signer, "1.5.0", "windows-x86_64", b"x")
        entry["url"] = url
        with pytest.raises(UpdateError, match="outside"):
            update_client.parse_manifest(config, {"version": "1.5.0", "platforms": {"windows-x86_64": entry}},
                              "windows-x86_64")

    @pytest.mark.parametrize("signature", ["not base64!", base64.b64encode(b"\x00" * 63).decode(), None, 5])
    def test_rejects_bad_signatures(self, signer, signature):
        config = _config(signer)
        entry = _entry(config, signer, "1.5.0", "windows-x86_64", b"x")
        entry["signature"] = signature
        with pytest.raises(UpdateError):
            update_client.parse_manifest(config, {"version": "1.5.0", "platforms": {"windows-x86_64": entry}},
                              "windows-x86_64")


# ---------- network ----------

def _trickle(body: bytes, gap: float = 0.04):
    """A route body that sends one byte every ``gap`` seconds."""
    def send(handler):
        handler.send_response(200)
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        for byte in body:
            try:
                handler.wfile.write(bytes([byte]))
                handler.wfile.flush()
            except OSError:
                return None
            time.sleep(gap)
        return None
    return send


def _publish(routes, config, signer, version, data, platform="windows-x86_64", name="App-setup.exe",
             manifest_version=None):
    """Serve a release the way GitHub does: latest/download redirects to the tag."""
    tag = f"v{version}"
    entry = _entry(config, signer, version, platform, data, name=name, tag=tag)
    manifest = {"version": manifest_version or version, "platforms": {platform: entry}}
    routes.add("/releases/latest/download/latest.json", status=302,
               headers={"Location": f"{routes.base}/releases/download/{tag}/latest.json"})
    routes.add(f"/releases/download/{tag}/latest.json", json.dumps(manifest).encode())
    routes.add(f"/releases/download/{tag}/{name}", data)
    return entry


class TestFetchUpdate:
    def test_follows_the_latest_redirect(self, signer, http_server):
        config = _config(signer, base=http_server.base + "/releases")
        _publish(http_server, config, signer, "1.5.0", b"payload")
        update = update_client.fetch_update(config, "windows-x86_64")
        assert update.version == "1.5.0"
        assert http_server.hits["/releases/latest/download/latest.json"] == 1

    def test_up_to_date(self, signer, http_server):
        config = _config(signer, base=http_server.base + "/releases", version="1.5.0")
        _publish(http_server, config, signer, "1.5.0", b"payload")
        assert update_client.fetch_update(config, "windows-x86_64") is None

    def test_http_error(self, signer, http_server):
        config = _config(signer, base=http_server.base + "/releases")
        with pytest.raises(UpdateError, match="HTTP 404"):
            update_client.fetch_update(config, "windows-x86_64")

    def test_refuses_a_redirect_that_changes_scheme(self, signer, http_server):
        config = _config(signer, base=http_server.base + "/releases")
        http_server.add("/releases/latest/download/latest.json", status=302,
                        headers={"Location": "https://127.0.0.1:1/latest.json?token=secret"})
        with pytest.raises(UpdateError, match="Refused a redirect") as info:
            update_client.fetch_update(config, "windows-x86_64")
        assert "secret" not in str(info.value)

    def test_unreachable(self, signer):
        config = _config(signer, base="http://127.0.0.1:9/releases")
        with pytest.raises(UpdateError, match="Could not reach"):
            update_client.fetch_update(config, "windows-x86_64")

    def test_not_json(self, signer, http_server):
        config = _config(signer, base=http_server.base + "/releases")
        http_server.add("/releases/latest/download/latest.json", b"<html>")
        with pytest.raises(UpdateError, match="not valid JSON"):
            update_client.fetch_update(config, "windows-x86_64")

    def test_too_large(self, signer, http_server):
        config = _config(signer, base=http_server.base + "/releases")
        http_server.add("/releases/latest/download/latest.json", b" " * (update_client.MAX_MANIFEST_BYTES + 1))
        with pytest.raises(UpdateError, match="too large"):
            update_client.fetch_update(config, "windows-x86_64")

    def test_deadline_holds_while_the_manifest_trickles_in(self, signer, http_server, monkeypatch):
        config = _config(signer, base=http_server.base + "/releases")
        http_server.add("/releases/latest/download/latest.json", _trickle(b" " * 200))
        monkeypatch.setattr(update_client, "CHECK_DEADLINE_SEC", 0.3)
        monkeypatch.setattr(update_client, "CHECK_TIMEOUT_SEC", 0.5)
        started = time.monotonic()
        with pytest.raises(UpdateError, match="update check did not finish within 0.3 s"):
            update_client.fetch_update(config, "windows-x86_64")
        assert time.monotonic() - started < 2.0

    def test_no_platform(self, signer):
        with mock.patch.object(update_client, "platform_key", return_value=None):
            with pytest.raises(UpdateError, match="platform"):
                update_client.fetch_update(_config(signer))

    def test_https_uses_certifi(self, signer):
        config = _config(signer, base="https://127.0.0.1:9/releases")
        with mock.patch.object(update_client, "_ssl_context", side_effect=UpdateError("certifi is not installed")):
            with pytest.raises(UpdateError, match="certifi"):
                update_client.fetch_update(config, "windows-x86_64")


class TestDownload:
    def _update(self, config, routes, signer, data, **overrides):
        _publish(routes, config, signer, "1.5.0", data, **overrides)
        return update_client.fetch_update(config, "windows-x86_64")

    def test_verified_download(self, signer, http_server, tmp_path):
        config = _config(signer, base=http_server.base + "/releases")
        update = self._update(config, http_server, signer, b"installer bytes")
        path = update_client.download(config, update, tmp_path)
        assert path == tmp_path / "App-setup.exe"
        assert path.read_bytes() == b"installer bytes"

    def test_tampered_file_is_rejected_and_deleted(self, signer, http_server, tmp_path):
        config = _config(signer, base=http_server.base + "/releases")
        update = self._update(config, http_server, signer, b"installer bytes")
        http_server.add("/releases/download/v1.5.0/App-setup.exe", b"installer byteZ")
        with pytest.raises(UpdateError, match="signature"):
            update_client.download(config, update, tmp_path)
        assert list(tmp_path.iterdir()) == []

    def test_relabelled_old_release_is_rejected(self, signer, http_server, tmp_path):
        # A genuine 1.4.0 installer offered under a newer version number.
        config = _config(signer, base=http_server.base + "/releases")
        old = _entry(config, signer, "1.4.0", "windows-x86_64", b"old installer", tag="v1.4.0")
        manifest = {"version": "9.9.9", "platforms": {"windows-x86_64": {
            "url": config.asset_url("v9.9.9", "App-setup.exe"), "signature": old["signature"]}}}
        http_server.add("/releases/latest/download/latest.json", json.dumps(manifest).encode())
        http_server.add("/releases/download/v9.9.9/App-setup.exe", b"old installer")
        update = update_client.fetch_update(config, "windows-x86_64")
        with pytest.raises(UpdateError, match="signature"):
            update_client.download(config, update, tmp_path)

    def test_other_platforms_file_is_rejected(self, signer, http_server, tmp_path):
        config = _config(signer, base=http_server.base + "/releases")
        mac = _entry(config, signer, "1.5.0", "darwin-aarch64", b"dmg bytes")
        manifest = {"version": "1.5.0", "platforms": {"windows-x86_64": {
            "url": config.asset_url("v1.5.0", "App-setup.exe"), "signature": mac["signature"]}}}
        http_server.add("/releases/latest/download/latest.json", json.dumps(manifest).encode())
        http_server.add("/releases/download/v1.5.0/App-setup.exe", b"dmg bytes")
        update = update_client.fetch_update(config, "windows-x86_64")
        with pytest.raises(UpdateError, match="signature"):
            update_client.download(config, update, tmp_path)

    def test_other_key_is_rejected(self, signer, http_server, tmp_path):
        from conftest import Signer
        config = _config(signer, base=http_server.base + "/releases")
        update = self._update(config, http_server, Signer(b"\x09" * 32), b"installer bytes")
        with pytest.raises(UpdateError, match="signature"):
            update_client.download(config, update, tmp_path)

    def test_size_cap(self, signer, http_server, tmp_path):
        config = _config(signer, base=http_server.base + "/releases")
        update = self._update(config, http_server, signer, b"x" * 1000)
        with pytest.raises(UpdateError, match="larger than"):
            update_client.download(config, update, tmp_path, max_bytes=999)
        assert list(tmp_path.iterdir()) == []

    def test_size_cap_without_content_length(self, signer, http_server, tmp_path):
        config = _config(signer, base=http_server.base + "/releases")
        update = self._update(config, http_server, signer, b"x" * 200000)

        def stream(handler):
            handler.send_response(200)
            handler.end_headers()
            handler.wfile.write(b"x" * 200000)
            handler.close_connection = True
            return None
        http_server.add("/releases/download/v1.5.0/App-setup.exe", stream)
        with pytest.raises(UpdateError, match="larger than"):
            update_client.download(config, update, tmp_path, max_bytes=100000)
        assert list(tmp_path.iterdir()) == []

    def test_deadline(self, signer, http_server, tmp_path):
        config = _config(signer, base=http_server.base + "/releases")
        update = self._update(config, http_server, signer, b"x" * 1000)
        with pytest.raises(UpdateError, match="did not finish"):
            update_client.download(config, update, tmp_path, deadline=-1)
        assert list(tmp_path.iterdir()) == []

    def test_deadline_holds_while_bytes_trickle_in(self, signer, http_server, tmp_path, monkeypatch):
        config = _config(signer, base=http_server.base + "/releases")
        update = self._update(config, http_server, signer, b"x" * 200)
        http_server.add("/releases/download/v1.5.0/App-setup.exe", _trickle(b"x" * 200))
        monkeypatch.setattr(update_client, "READ_TIMEOUT_SEC", 0.5)
        started = time.monotonic()
        with pytest.raises(UpdateError, match="download did not finish within 0.3 s"):
            update_client.download(config, update, tmp_path, deadline=0.3)
        assert time.monotonic() - started < 2.0
        assert list(tmp_path.iterdir()) == []

    def test_truncated_body(self, signer, http_server, tmp_path):
        config = _config(signer, base=http_server.base + "/releases")
        update = self._update(config, http_server, signer, b"x" * 1000)

        def short(handler):
            handler.send_response(200)
            handler.send_header("Content-Length", "1000")
            handler.end_headers()
            handler.wfile.write(b"x" * 10)
            handler.close_connection = True
            return None
        http_server.add("/releases/download/v1.5.0/App-setup.exe", short)
        with pytest.raises(UpdateError, match="interrupted|ended at"):
            update_client.download(config, update, tmp_path)
        assert list(tmp_path.iterdir()) == []

    def test_invalid_app_key(self, signer, http_server, tmp_path):
        config = _config(signer, base=http_server.base + "/releases")
        update = self._update(config, http_server, signer, b"x")
        bad = UpdateConfig(**{**config.__dict__, "public_key": "AAAA"})
        with pytest.raises(UpdateError, match="update key"):
            update_client.download(bad, update, tmp_path)


# ---------- config ----------

def test_default_urls_point_at_github_releases(signer):
    config = UpdateConfig(product="p", repo="semnil/analyze-loudness", current_version="1.0.0",
                          public_key=signer.public_key_b64, temp_prefix="x_")
    assert config.manifest_url == "https://github.com/semnil/analyze-loudness/releases/latest/download/latest.json"
    assert config.asset_url("v1.0.0", "a.dmg") == \
        "https://github.com/semnil/analyze-loudness/releases/download/v1.0.0/a.dmg"


# ---------- macOS bundle replacement ----------

def _fake_app(path: Path, identifier="com.example.test", version="1.0.0", marker="old"):
    (path / "Contents" / "MacOS").mkdir(parents=True)
    with open(path / "Contents" / "Info.plist", "wb") as f:
        plistlib.dump({"CFBundleIdentifier": identifier, "CFBundleShortVersionString": version}, f)
    (path / "Contents" / "MacOS" / "marker").write_text(marker)
    return path


def _marker(app: Path) -> str:
    return (app / "Contents" / "MacOS" / "marker").read_text()


@pytest.fixture(scope="module")
def make_dmg(tmp_path_factory):
    """A DMG holding "Test App.app" (marker "new"), built once per Info.plist."""
    built = {}

    def make(identifier="com.example.test", version="1.5.0"):
        key = (identifier, version)
        if key not in built:
            root = tmp_path_factory.mktemp("dmg")
            src = root / "src"
            _fake_app(src / "Test App.app", identifier=identifier, version=version, marker="new")
            (src / "Applications").symlink_to("/Applications")
            dmg = root / "Test.dmg"
            subprocess.run(["/usr/bin/hdiutil", "create", "-quiet", "-fs", "HFS+", "-srcfolder", str(src),
                            "-volname", "Test", "-format", "UDZO", str(dmg)], check=True)
            built[key] = dmg
        return built[key]
    return make


class TestReplaceBundle:
    @pytest.mark.skipif(not IS_DARWIN, reason="renamex_np is macOS-only")
    def test_swap(self, tmp_path):
        target = _fake_app(tmp_path / "App.app", marker="old")
        staged = _fake_app(tmp_path / "stage" / "App.app", marker="new")
        previous = update_client.replace_bundle(target, staged, tmp_path / "stage" / "previous.app")
        assert _marker(target) == "new"
        assert previous == staged and _marker(previous) == "old"

    def test_two_renames_when_swap_is_unsupported(self, tmp_path):
        target = _fake_app(tmp_path / "App.app", marker="old")
        staged = _fake_app(tmp_path / "stage" / "App.app", marker="new")
        backup = tmp_path / "stage" / "previous.app"
        with mock.patch.object(update_client, "_swap", side_effect=OSError(45, "Operation not supported")):
            previous = update_client.replace_bundle(target, staged, backup)
        assert _marker(target) == "new"
        assert previous == backup and _marker(backup) == "old"

    def test_second_rename_failure_restores_the_app(self, tmp_path):
        target = _fake_app(tmp_path / "App.app", marker="old")
        staged = _fake_app(tmp_path / "stage" / "App.app", marker="new")
        backup = tmp_path / "stage" / "previous.app"
        real_rename = os.rename
        calls = []

        def rename(src, dst):
            calls.append((src, dst))
            if len(calls) == 2:
                raise OSError(28, "No space left on device")
            return real_rename(src, dst)
        with mock.patch.object(update_client, "_swap", side_effect=OSError(45, "Operation not supported")), \
                mock.patch.object(update_client.os, "rename", side_effect=rename):
            with pytest.raises(UpdateError, match="Installing the update failed"):
                update_client.replace_bundle(target, staged, backup)
        assert _marker(target) == "old"
        assert len(calls) == 3

    def test_permission_error_asks_for_administrator(self, tmp_path):
        target = _fake_app(tmp_path / "App.app")
        staged = _fake_app(tmp_path / "stage" / "App.app", marker="new")
        with mock.patch.object(update_client, "_swap", side_effect=PermissionError(13, "Permission denied")), \
                mock.patch.object(update_client, "_privileged_replace") as privileged:
            update_client.replace_bundle(target, staged, tmp_path / "stage" / "previous.app")
        privileged.assert_called_once()

    def test_cancelled_authorization(self, tmp_path):
        result = subprocess.CompletedProcess([], 1, "", "execution error: User canceled. (-128)")
        with mock.patch.object(update_client.subprocess, "run", return_value=result):
            with pytest.raises(UpdateError, match="cancelled"):
                update_client._privileged_replace(tmp_path / "a", tmp_path / "b", tmp_path / "c")


@pytest.mark.skipif(sys.platform == "win32", reason="needs /bin/sh")
class TestPrivilegedCommand:
    def _run(self, command):
        return subprocess.run(["/bin/sh", "-c", command]).returncode

    def test_moves_the_new_app_in(self, tmp_path):
        target = _fake_app(tmp_path / "My App.app", marker="old")
        staged = _fake_app(tmp_path / "it's staged" / "My App.app", marker="new")
        backup = tmp_path / "it's staged" / "previous.app"
        assert self._run(update_client.privileged_replace_command(target, staged, backup)) == 0
        assert _marker(target) == "new" and _marker(backup) == "old"

    def test_restores_when_the_new_app_is_missing(self, tmp_path):
        target = _fake_app(tmp_path / "App.app", marker="old")
        backup = tmp_path / "previous.app"
        assert self._run(update_client.privileged_replace_command(target, tmp_path / "missing.app", backup)) == 1
        assert _marker(target) == "old"

    def test_applescript_quoting(self):
        assert update_client._applescript_string('a "b" \\c') == '"a \\"b\\" \\\\c"'


@pytest.mark.skipif(sys.platform == "win32", reason="needs /bin/sh")
def test_relaunch_waits_for_the_process_to_exit(tmp_path):
    waited = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1.0)"])
    marker = tmp_path / "opened"
    cleanup = tmp_path / "stage"
    cleanup.mkdir()
    started = time.monotonic()
    update_client._relaunch_after_exit(marker, cleanup, process_id=waited.pid, opener="/usr/bin/touch")
    time.sleep(0.4)
    assert not marker.exists()
    waited.wait()
    deadline = time.monotonic() + 5
    while not (marker.exists() and not cleanup.exists()) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert marker.exists()
    assert not cleanup.exists()
    assert time.monotonic() - started >= 1.0


@pytest.mark.skipif(not IS_DARWIN, reason="hdiutil is macOS-only")
class TestStageMacBundle:
    def test_stages_the_app(self, tmp_path, make_dmg):
        current = _fake_app(tmp_path / "installed" / "Test App.app")
        stage = tmp_path / "stage"
        stage.mkdir()
        staged = update_client.stage_mac_bundle(make_dmg(), current, "1.5.0", stage)
        assert staged == stage / "Test App.app"
        assert _marker(staged) == "new"
        assert sorted(p.name for p in stage.iterdir()) == ["Test App.app"]  # mount point removed
        out = subprocess.run(["/usr/bin/hdiutil", "info"], capture_output=True, text=True).stdout
        assert str(stage) not in out

    def test_rejects_another_app(self, tmp_path, make_dmg):
        current = _fake_app(tmp_path / "installed" / "Test App.app")
        stage = tmp_path / "stage"
        stage.mkdir()
        dmg = make_dmg(identifier="com.example.other")
        with pytest.raises(UpdateError, match="different app"):
            update_client.stage_mac_bundle(dmg, current, "1.5.0", stage)

    def test_rejects_another_version(self, tmp_path, make_dmg):
        current = _fake_app(tmp_path / "installed" / "Test App.app")
        stage = tmp_path / "stage"
        stage.mkdir()
        with pytest.raises(UpdateError, match="version 1.4.9"):
            update_client.stage_mac_bundle(make_dmg(version="1.4.9"), current, "1.5.0", stage)

    def test_rejects_another_team(self, tmp_path, make_dmg):
        current = _fake_app(tmp_path / "installed" / "Test App.app")
        stage = tmp_path / "stage"
        stage.mkdir()
        teams = {str(current): "TEAMAAAAAA"}
        with mock.patch.object(update_client, "_team_id", side_effect=lambda app: teams.get(str(app), "TEAMBBBBBB")):
            with pytest.raises(UpdateError, match="same developer"):
                update_client.stage_mac_bundle(make_dmg(), current, "1.5.0", stage)

    def test_unsigned_app_has_no_team(self, tmp_path):
        assert update_client._team_id(_fake_app(tmp_path / "Unsigned.app")) is None


# ---------- Updater ----------

class TestUpdater:
    def test_status_outside_a_packaged_build(self, signer):
        updater = Updater(_config(signer))
        with mock.patch.object(update_client, "IS_FROZEN", False):
            assert updater.status() == {"current": "1.4.1", "supported": False}

    def test_install_needs_a_packaged_build(self, signer):
        updater = Updater(_config(signer))
        with mock.patch.object(update_client, "IS_FROZEN", False):
            with pytest.raises(UpdateError, match="packaged app"):
                updater.install("1.5.0")

    def test_install_only_the_offered_version(self, signer, http_server):
        config = _config(signer, base=http_server.base + "/releases")
        _publish(http_server, config, signer, "1.5.0", b"x")
        updater = Updater(config)
        with mock.patch.object(update_client, "platform_key", return_value="windows-x86_64"):
            assert updater.check() == "1.5.0"
        with mock.patch.object(Updater, "supported", return_value=True):
            with pytest.raises(UpdateError, match="not offered"):
                updater.install("1.6.0")

    def test_install_before_any_check(self, signer):
        with mock.patch.object(Updater, "supported", return_value=True):
            with pytest.raises(UpdateError, match="not offered"):
                Updater(_config(signer)).install("1.5.0")

    def test_windows_hands_off_to_the_installer(self, signer, http_server):
        config = _config(signer, base=http_server.base + "/releases")
        _publish(http_server, config, signer, "1.5.0", b"setup bytes")
        updater = Updater(config)
        with mock.patch.object(update_client, "platform_key", return_value="windows-x86_64"):
            updater.check()
        started = []
        with mock.patch.object(Updater, "supported", return_value=True), \
                mock.patch.object(update_client, "IS_WINDOWS", True), \
                mock.patch.object(update_client, "_launch_installer", side_effect=started.append):
            assert updater.install("1.5.0") == Handoff("close")
        assert started[0].read_bytes() == b"setup bytes"
        assert started[0].parent.name.startswith("analyzetest_update_")
        shutil.rmtree(started[0].parent)

    def test_windows_failure_removes_the_download(self, signer, http_server):
        config = _config(signer, base=http_server.base + "/releases")
        _publish(http_server, config, signer, "1.5.0", b"setup bytes")
        updater = Updater(config)
        with mock.patch.object(update_client, "platform_key", return_value="windows-x86_64"):
            updater.check()
        seen = []

        def refuse(path):
            seen.append(path)
            raise UpdateError("The installer was cancelled")
        with mock.patch.object(Updater, "supported", return_value=True), \
                mock.patch.object(update_client, "IS_WINDOWS", True), \
                mock.patch.object(update_client, "_launch_installer", side_effect=refuse):
            with pytest.raises(UpdateError, match="cancelled"):
                updater.install("1.5.0")
        assert not seen[0].parent.exists()

    @pytest.mark.skipif(not IS_DARWIN, reason="hdiutil and renamex_np are macOS-only")
    def test_mac_replaces_the_bundle_and_relaunches(self, signer, http_server, tmp_path, make_dmg):
        dmg = make_dmg()
        config = _config(signer, base=http_server.base + "/releases")
        _publish(http_server, config, signer, "1.5.0", dmg.read_bytes(), platform="darwin-aarch64",
                 name="Test.dmg")
        current = _fake_app(tmp_path / "Applications" / "Test App.app", version="1.4.1", marker="old")
        updater = Updater(config)
        with mock.patch.object(update_client, "platform_key", return_value="darwin-aarch64"):
            assert updater.check() == "1.5.0"
        relaunched = []
        with mock.patch.object(Updater, "supported", return_value=True), \
                mock.patch.object(update_client, "IS_WINDOWS", False), \
                mock.patch.object(update_client, "running_bundle", return_value=current), \
                mock.patch.object(update_client, "other_instances", return_value=[]), \
                mock.patch.object(update_client, "_relaunch_after_exit", side_effect=lambda t, c: relaunched.append((t, c))):
            assert updater.install("1.5.0") == Handoff("immediate")
        assert _marker(current) == "new"
        target, stage = relaunched[0]
        assert target == current
        assert _marker(stage / "Test App.app") == "old"
        with mock.patch.object(Updater, "supported", return_value=True):
            with pytest.raises(UpdateError, match="already"):
                updater.install("1.5.0")
        shutil.rmtree(stage)

    @pytest.mark.skipif(not IS_DARWIN, reason="hdiutil and renamex_np are macOS-only")
    def test_mac_relaunch_failure_is_reported(self, signer, http_server, tmp_path, make_dmg):
        dmg = make_dmg()
        config = _config(signer, base=http_server.base + "/releases")
        _publish(http_server, config, signer, "1.5.0", dmg.read_bytes(), platform="darwin-aarch64",
                 name="Test.dmg")
        current = _fake_app(tmp_path / "Applications" / "Test App.app", version="1.4.1")
        updater = Updater(config)
        with mock.patch.object(update_client, "platform_key", return_value="darwin-aarch64"):
            updater.check()
        with mock.patch.object(Updater, "supported", return_value=True), \
                mock.patch.object(update_client, "IS_WINDOWS", False), \
                mock.patch.object(update_client, "running_bundle", return_value=current), \
                mock.patch.object(update_client, "other_instances", return_value=[]), \
                mock.patch.object(update_client, "_relaunch_after_exit", side_effect=OSError(35, "Resource busy")):
            handoff = updater.install("1.5.0")
        assert handoff.exit_mode is None
        assert "Resource busy" in handoff.restart_error
        assert _marker(current) == "new"

    @pytest.mark.skipif(not IS_DARWIN, reason="hdiutil is macOS-only")
    def test_mac_keeps_the_only_copy_of_the_previous_app(self, signer, http_server, tmp_path, make_dmg):
        config = _config(signer, base=http_server.base + "/releases")
        _publish(http_server, config, signer, "1.5.0", make_dmg().read_bytes(), platform="darwin-aarch64",
                 name="Test.dmg")
        current = _fake_app(tmp_path / "Applications" / "Test App.app", version="1.4.1", marker="old")
        updater = Updater(config)
        with mock.patch.object(update_client, "platform_key", return_value="darwin-aarch64"):
            updater.check()

        def lose_the_app(target, staged, backup):
            os.rename(target, backup)
            raise UpdateError(f"Installing the update failed, and the previous app could not be put back; it is at {backup}")
        with mock.patch.object(Updater, "supported", return_value=True), \
                mock.patch.object(update_client, "IS_WINDOWS", False), \
                mock.patch.object(update_client, "running_bundle", return_value=current), \
                mock.patch.object(update_client, "other_instances", return_value=[]), \
                mock.patch.object(update_client, "replace_bundle", side_effect=lose_the_app):
            with pytest.raises(UpdateError) as info:
                updater.install("1.5.0")
        backup = Path(str(info.value).rsplit("it is at ", 1)[1])
        assert _marker(backup) == "old"
        shutil.rmtree(backup.parent)

    @pytest.mark.skipif(not IS_DARWIN, reason="hdiutil is macOS-only")
    def test_mac_failed_replace_removes_the_stage(self, signer, http_server, tmp_path, make_dmg):
        config = _config(signer, base=http_server.base + "/releases")
        _publish(http_server, config, signer, "1.5.0", make_dmg().read_bytes(), platform="darwin-aarch64",
                 name="Test.dmg")
        current = _fake_app(tmp_path / "Applications" / "Test App.app", version="1.4.1", marker="old")
        updater = Updater(config)
        with mock.patch.object(update_client, "platform_key", return_value="darwin-aarch64"):
            updater.check()
        seen = []

        def refuse(target, staged, backup):
            seen.append(backup.parent)
            raise UpdateError("Moving the current app aside failed: busy")
        with mock.patch.object(Updater, "supported", return_value=True), \
                mock.patch.object(update_client, "IS_WINDOWS", False), \
                mock.patch.object(update_client, "running_bundle", return_value=current), \
                mock.patch.object(update_client, "other_instances", return_value=[]), \
                mock.patch.object(update_client, "replace_bundle", side_effect=refuse):
            with pytest.raises(UpdateError, match="busy"):
                updater.install("1.5.0")
        assert not seen[0].exists()
        assert _marker(current) == "old"

    def test_mac_refuses_a_translocated_app(self, signer, http_server):
        config = _config(signer, base=http_server.base + "/releases")
        _publish(http_server, config, signer, "1.5.0", b"x", platform="darwin-aarch64", name="T.dmg")
        updater = Updater(config)
        with mock.patch.object(update_client, "platform_key", return_value="darwin-aarch64"):
            updater.check()
        app = Path("/private/var/folders/xx/T/AppTranslocation/ABC/d/Test App.app")
        with mock.patch.object(Updater, "supported", return_value=True), \
                mock.patch.object(update_client, "IS_WINDOWS", False), \
                mock.patch.object(update_client, "running_bundle", return_value=app):
            with pytest.raises(UpdateError, match="Applications folder"):
                updater.install("1.5.0")


@pytest.mark.skipif(not IS_DARWIN, reason="uses macOS ps")
class TestOtherInstances:
    def test_finds_another_process_of_the_executable(self):
        other = subprocess.Popen(["/bin/sleep", "30"])
        try:
            assert other.pid in update_client.other_instances(Path("/bin/sleep"))
            assert update_client.other_instances(Path("/bin/sleep-not")) == []
        finally:
            other.kill()
            other.wait()

    def test_ignores_this_process(self):
        assert os.getpid() not in update_client.other_instances(Path(sys.executable))

    def test_refuses_to_replace_under_another_instance(self, tmp_path):
        with mock.patch.object(update_client, "other_instances", return_value=[4242]):
            with pytest.raises(UpdateError, match="process 4242"):
                update_client._refuse_other_instances()


@pytest.mark.skipif(not IS_DARWIN, reason="hdiutil and renamex_np are macOS-only")
def test_mac_install_refused_while_another_instance_runs(signer, http_server, tmp_path, make_dmg):
    config = _config(signer, base=http_server.base + "/releases")
    _publish(http_server, config, signer, "1.5.0", make_dmg().read_bytes(), platform="darwin-aarch64",
             name="Test.dmg")
    current = _fake_app(tmp_path / "Applications" / "Test App.app", version="1.4.1", marker="old")
    updater = Updater(config)
    with mock.patch.object(update_client, "platform_key", return_value="darwin-aarch64"):
        updater.check()
    with mock.patch.object(Updater, "supported", return_value=True), \
            mock.patch.object(update_client, "IS_WINDOWS", False), \
            mock.patch.object(update_client, "running_bundle", return_value=current), \
            mock.patch.object(update_client, "other_instances", side_effect=[[], [4242]]):
        with pytest.raises(UpdateError, match="Another window"):
            updater.install("1.5.0")
    assert _marker(current) == "old"


class TestRunningBundle:
    def test_finds_the_app(self):
        with mock.patch.object(update_client, "IS_MAC", True), mock.patch.object(update_client, "IS_FROZEN", True), \
                mock.patch.object(update_client.sys, "executable", "/Applications/Test App.app/Contents/MacOS/test"):
            assert update_client.running_bundle() == Path("/Applications/Test App.app")

    @pytest.mark.parametrize("executable", ["/usr/local/bin/test", "/Applications/Test/Contents/MacOS/test"])
    def test_not_in_a_bundle(self, executable):
        with mock.patch.object(update_client, "IS_MAC", True), mock.patch.object(update_client, "IS_FROZEN", True), \
                mock.patch.object(update_client.sys, "executable", executable):
            assert update_client.running_bundle() is None


def test_relaunch_starts_an_independent_pyinstaller_instance(tmp_path):
    with mock.patch.object(update_client.subprocess, "Popen") as popen:
        update_client._relaunch_after_exit(tmp_path / "App.app", tmp_path / "stage")
    assert popen.call_args.kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    assert popen.call_args.kwargs["start_new_session"] is True


class TestWindows:
    @pytest.fixture(autouse=True)
    def _restore_environment(self, monkeypatch):
        # _launch_installer sets the variable in os.environ; monkeypatch puts back the original.
        monkeypatch.setenv("PYINSTALLER_RESET_ENVIRONMENT", "")

    def test_installer_starts_an_independent_pyinstaller_instance(self, tmp_path):
        seen = []
        with mock.patch.object(update_client.os, "startfile", create=True,
                               side_effect=lambda *a: seen.append(os.environ.get("PYINSTALLER_RESET_ENVIRONMENT"))):
            update_client._launch_installer(tmp_path / "setup.exe")
        assert seen == ["1"]

    def test_installer_arguments(self, tmp_path):
        calls = []
        with mock.patch.object(update_client.os, "startfile", create=True, side_effect=lambda *a: calls.append(a)):
            update_client._launch_installer(tmp_path / "setup.exe")
        assert calls == [(str(tmp_path / "setup.exe"), "open", update_client.INSTALLER_ARGS)]
        assert "/UPDATE=1" in update_client.INSTALLER_ARGS.split()

    def test_declined_uac(self, tmp_path):
        err = OSError("cancelled")
        err.winerror = 1223
        with mock.patch.object(update_client.os, "startfile", create=True, side_effect=err):
            with pytest.raises(UpdateError, match="cancelled"):
                update_client._launch_installer(tmp_path / "setup.exe")

    def test_mutex_is_windows_only(self):
        with mock.patch.object(update_client, "IS_WINDOWS", False):
            update_client.hold_instance_mutex("com.example.test")
        assert update_client._mutex_handle is None
