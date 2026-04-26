"""Tests for analyze_common.platform."""

import os
import subprocess
from unittest import mock

import pytest


def _reload_platform(**overrides):
    """Reload platform module with patched sys attributes."""
    import importlib
    patches = []
    for attr, value in overrides.items():
        patches.append(mock.patch(f"sys.{attr}", value))
    for p in patches:
        p.start()
    try:
        import analyze_common.platform as mod
        importlib.reload(mod)
        return mod
    finally:
        for p in patches:
            p.stop()


class TestPlatformDetection:
    def test_darwin(self):
        mod = _reload_platform(platform="darwin")
        assert mod.IS_MAC is True
        assert mod.IS_WINDOWS is False
        assert mod.IS_LINUX is False

    def test_win32(self):
        mod = _reload_platform(platform="win32")
        assert mod.IS_WINDOWS is True
        assert mod.IS_MAC is False
        assert mod.IS_LINUX is False

    def test_linux(self):
        mod = _reload_platform(platform="linux")
        assert mod.IS_LINUX is True
        assert mod.IS_WINDOWS is False
        assert mod.IS_MAC is False

    def teardown_method(self):
        import importlib
        import analyze_common.platform as mod
        importlib.reload(mod)


class TestSubprocessKwargs:
    def test_non_frozen_returns_empty(self):
        from analyze_common.platform import subprocess_kwargs
        result = subprocess_kwargs()
        assert result == {}

    @pytest.mark.skipif(
        not hasattr(subprocess, "STARTUPINFO"),
        reason="STARTUPINFO is Windows-only",
    )
    def test_windows_frozen(self):
        import analyze_common.platform as mod
        with mock.patch.object(mod, "IS_WINDOWS", True), \
             mock.patch.object(mod, "IS_FROZEN", True):
            result = mod.subprocess_kwargs()
            assert "startupinfo" in result
            si = result["startupinfo"]
            assert si.dwFlags & subprocess.STARTF_USESHOWWINDOW

    def test_mac_frozen_dyld_orig_exists(self):
        import analyze_common.platform as mod
        env = os.environ.copy()
        env["DYLD_LIBRARY_PATH"] = "/pyinstaller/path"
        env["DYLD_LIBRARY_PATH_ORIG"] = "/original/path"
        with mock.patch.object(mod, "IS_MAC", True), \
             mock.patch.object(mod, "IS_WINDOWS", False), \
             mock.patch.object(mod, "IS_FROZEN", True), \
             mock.patch.dict(os.environ, env, clear=True):
            result = mod.subprocess_kwargs()
            assert "env" in result
            assert result["env"]["DYLD_LIBRARY_PATH"] == "/original/path"
            assert "DYLD_LIBRARY_PATH_ORIG" not in result["env"]

    def test_mac_frozen_dyld_orig_empty(self):
        import analyze_common.platform as mod
        env = os.environ.copy()
        env["DYLD_LIBRARY_PATH"] = "/pyinstaller/path"
        env["DYLD_LIBRARY_PATH_ORIG"] = ""
        with mock.patch.object(mod, "IS_MAC", True), \
             mock.patch.object(mod, "IS_WINDOWS", False), \
             mock.patch.object(mod, "IS_FROZEN", True), \
             mock.patch.dict(os.environ, env, clear=True):
            result = mod.subprocess_kwargs()
            assert result["env"]["DYLD_LIBRARY_PATH"] == ""

    def test_mac_frozen_dyld_no_orig(self):
        import analyze_common.platform as mod
        env = os.environ.copy()
        env["DYLD_LIBRARY_PATH"] = "/pyinstaller/path"
        env.pop("DYLD_LIBRARY_PATH_ORIG", None)
        with mock.patch.object(mod, "IS_MAC", True), \
             mock.patch.object(mod, "IS_WINDOWS", False), \
             mock.patch.object(mod, "IS_FROZEN", True), \
             mock.patch.dict(os.environ, env, clear=True):
            result = mod.subprocess_kwargs()
            assert "DYLD_LIBRARY_PATH" not in result["env"]

    def test_mac_frozen_all_dyld_vars_restored(self):
        import analyze_common.platform as mod
        env = os.environ.copy()
        env["DYLD_LIBRARY_PATH"] = "/pi/lib"
        env["DYLD_LIBRARY_PATH_ORIG"] = "/orig/lib"
        env["DYLD_FRAMEWORK_PATH"] = "/pi/fw"
        env["DYLD_FRAMEWORK_PATH_ORIG"] = "/orig/fw"
        env["DYLD_INSERT_LIBRARIES"] = "/pi/ins"
        env["DYLD_INSERT_LIBRARIES_ORIG"] = "/orig/ins"
        with mock.patch.object(mod, "IS_MAC", True), \
             mock.patch.object(mod, "IS_WINDOWS", False), \
             mock.patch.object(mod, "IS_FROZEN", True), \
             mock.patch.dict(os.environ, env, clear=True):
            result = mod.subprocess_kwargs()
            assert result["env"]["DYLD_LIBRARY_PATH"] == "/orig/lib"
            assert result["env"]["DYLD_FRAMEWORK_PATH"] == "/orig/fw"
            assert result["env"]["DYLD_INSERT_LIBRARIES"] == "/orig/ins"
            assert "DYLD_LIBRARY_PATH_ORIG" not in result["env"]
            assert "DYLD_FRAMEWORK_PATH_ORIG" not in result["env"]
            assert "DYLD_INSERT_LIBRARIES_ORIG" not in result["env"]
