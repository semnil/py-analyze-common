"""Tests for analyze_common.update_manifest (needs the openssl command)."""

import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from analyze_common import update as update_client
from analyze_common import update_manifest as manifest_tool
from analyze_common.update import UpdateConfig, UpdateError

def _openssl_has_ed25519() -> bool:
    if shutil.which("openssl") is None:
        return False
    probe = subprocess.run(["openssl", "genpkey", "-algorithm", "ed25519"], capture_output=True)
    return probe.returncode == 0


# release.yaml runs this tool on ubuntu (OpenSSL 3); macOS ships LibreSSL 3.3, which has no Ed25519.
pytestmark = pytest.mark.skipif(not _openssl_has_ed25519(), reason="openssl on PATH cannot create Ed25519 keys")


def _genkey(path: Path) -> Path:
    subprocess.run(["openssl", "genpkey", "-algorithm", "ed25519", "-out", str(path)], check=True)
    return path


@pytest.fixture
def key(tmp_path):
    return _genkey(tmp_path / "key.pem")


def _config(public_key, version="1.5.0", base="https://github.com/semnil/analyze-test/releases"):
    return UpdateConfig(product="analyze-test", repo="semnil/analyze-test", current_version=version,
                        public_key=public_key, temp_prefix="analyzetest_update_", releases_url=base)


@pytest.fixture
def assets(tmp_path):
    exe = tmp_path / "App-1.5.0-setup.exe"
    exe.write_bytes(b"windows installer")
    dmg = tmp_path / "App.dmg"
    dmg.write_bytes(b"mac image")
    return {"windows-x86_64": exe, "darwin-aarch64": dmg}


def test_public_key_is_raw_32_bytes(key):
    assert len(base64.b64decode(manifest_tool.public_key(key), validate=True)) == 32


def test_public_key_refuses_other_key_types(tmp_path):
    rsa = tmp_path / "rsa.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:1024",
                    "-out", str(rsa)], check=True, capture_output=True)
    with pytest.raises(UpdateError, match="not an Ed25519 key"):
        manifest_tool.public_key(rsa)


def test_manifest_shape(key, assets):
    manifest = manifest_tool.build_manifest(_config(manifest_tool.public_key(key)), "v1.5.0", key, assets)
    assert manifest["version"] == "1.5.0"
    assert manifest["platforms"]["windows-x86_64"]["url"] == \
        "https://github.com/semnil/analyze-test/releases/download/v1.5.0/App-1.5.0-setup.exe"
    assert manifest["platforms"]["darwin-aarch64"]["url"] == \
        "https://github.com/semnil/analyze-test/releases/download/v1.5.0/App.dmg"


def test_signed_manifest_is_accepted_by_the_client(key, assets, http_server, tmp_path):
    # OpenSSL signs in CI; the app's pure-Python verifier must accept it.
    base = http_server.base + "/releases"
    manifest = manifest_tool.build_manifest(_config(manifest_tool.public_key(key), base=base), "v1.5.0", key, assets)
    http_server.add("/releases/latest/download/latest.json", json.dumps(manifest).encode())
    http_server.add("/releases/download/v1.5.0/App-1.5.0-setup.exe", b"windows installer")
    http_server.add("/releases/download/v1.5.0/App.dmg", b"mac image")
    installed = _config(manifest_tool.public_key(key), version="1.4.1", base=base)
    for platform, name in (("windows-x86_64", "App-1.5.0-setup.exe"), ("darwin-aarch64", "App.dmg")):
        update = update_client.fetch_update(installed, platform)
        dest = tmp_path / platform
        dest.mkdir()
        assert update_client.download(installed, update, dest).read_bytes() == assets[platform].read_bytes()


def test_key_that_does_not_match_the_app_fails(key, assets, tmp_path):
    other = manifest_tool.public_key(_genkey(tmp_path / "other.pem"))
    with pytest.raises(UpdateError, match="does not match the app's public key"):
        manifest_tool.build_manifest(_config(other), "v1.5.0", key, assets)


@pytest.mark.parametrize("tag", ["v1.5.1", "1.5.0", "v1.5.0-rc1"])
def test_tag_must_match_the_app_version(key, assets, tag):
    with pytest.raises(UpdateError, match="does not match the app version"):
        manifest_tool.build_manifest(_config(manifest_tool.public_key(key)), tag, key, assets)


def test_unknown_platform(key, assets):
    with pytest.raises(UpdateError, match="Unknown platform"):
        manifest_tool.build_manifest(_config(manifest_tool.public_key(key)), "v1.5.0", key, {"linux-x86_64": assets["darwin-aarch64"]})


def test_cli_writes_the_manifest(key, assets, tmp_path, monkeypatch, capsys):
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "fake_app_update.py").write_text(
        "from analyze_common.update import UpdateConfig\n"
        f"CONFIG = UpdateConfig(product='analyze-test', repo='semnil/analyze-test', current_version='1.5.0',"
        f" public_key={manifest_tool.public_key(key)!r}, temp_prefix='x_')\n")
    out = tmp_path / "latest.json"
    argv = ["sign", "--config", "fake_app_update:CONFIG", "--tag", "v1.5.0", "--key", str(key),
            "--out", str(out)] + [f"{p}={path}" for p, path in assets.items()]
    assert manifest_tool.main(argv) == 0
    assert set(json.loads(out.read_text())["platforms"]) == set(assets)


def test_cli_reports_failures(key, assets, tmp_path, capsys):
    out = tmp_path / "latest.json"
    argv = ["sign", "--config", "analyze_common.update:PLATFORMS", "--tag", "v1.5.0", "--key", str(key),
            "--out", str(out), f"windows-x86_64={assets['windows-x86_64']}"]
    assert manifest_tool.main(argv) == 1
    assert "is not an UpdateConfig" in capsys.readouterr().err
    assert not out.exists()


def test_cli_public_key(key, capsys):
    assert manifest_tool.main(["public-key", str(key)]) == 0
    assert capsys.readouterr().out.strip() == manifest_tool.public_key(key)
