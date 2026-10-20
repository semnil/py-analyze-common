"""Tests for analyze_common.settings."""

import json
import os
from pathlib import Path
from unittest import mock

import pytest

from analyze_common import settings
from analyze_common.settings import SettingsStore


class TestSettingsDir:
    def test_windows_uses_appdata(self, monkeypatch):
        monkeypatch.setenv("APPDATA", r"C:\Users\u\AppData\Roaming")
        with mock.patch.object(settings, "IS_WINDOWS", True), mock.patch.object(settings, "IS_MAC", False):
            assert settings.settings_dir("analyze-test") == Path(r"C:\Users\u\AppData\Roaming") / "analyze-test"

    def test_mac_uses_application_support(self):
        with mock.patch.object(settings, "IS_WINDOWS", False), mock.patch.object(settings, "IS_MAC", True):
            assert settings.settings_dir("analyze-test") == \
                Path.home() / "Library" / "Application Support" / "analyze-test"

    def test_other_systems_use_xdg_config_home(self, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xdg")
        with mock.patch.object(settings, "IS_WINDOWS", False), mock.patch.object(settings, "IS_MAC", False):
            assert settings.settings_dir("analyze-test") == Path("/tmp/xdg") / "analyze-test"


class TestSettingsStore:
    def test_missing_file_reads_as_defaults(self, tmp_path):
        store = SettingsStore(tmp_path / "missing" / "settings.json")
        assert store.get("anything", 42) == 42

    def test_set_then_get_survives_a_new_store(self, tmp_path):
        path = tmp_path / "app" / "settings.json"
        SettingsStore(path).set("flag", False)
        assert SettingsStore(path).get("flag", True) is False
        assert json.loads(path.read_text(encoding="utf-8")) == {"flag": False}

    def test_set_keeps_other_keys(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
        SettingsStore(path).set("flag", True)
        assert json.loads(path.read_text(encoding="utf-8")) == {"theme": "dark", "flag": True}

    @pytest.mark.parametrize("content", ["{not json", "[1, 2]", "\xff\xfe"])
    def test_malformed_file_reads_as_defaults_and_warns(self, tmp_path, capsys, content):
        path = tmp_path / "settings.json"
        path.write_text(content, encoding="latin-1")
        store = SettingsStore(path)
        assert store.get("flag", True) is True
        assert "Ignoring" in capsys.readouterr().err
        store.set("flag", False)
        assert json.loads(path.read_text(encoding="utf-8")) == {"flag": False}

    def test_failed_write_leaves_no_temp_file(self, tmp_path):
        path = tmp_path / "settings.json"
        store = SettingsStore(path)
        with mock.patch.object(settings.os, "replace", side_effect=OSError(28, "No space left on device")):
            with pytest.raises(OSError):
                store.set("flag", False)
        assert list(tmp_path.iterdir()) == []

    @pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
    def test_unwritable_folder_raises(self, tmp_path):
        folder = tmp_path / "locked"
        folder.mkdir()
        folder.chmod(0o500)
        try:
            with pytest.raises(OSError):
                SettingsStore(folder / "settings.json").set("flag", False)
        finally:
            folder.chmod(0o700)
