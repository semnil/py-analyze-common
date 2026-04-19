"""Tests for desktop_app_common.theme."""

import subprocess
from unittest import mock

import pytest

import desktop_app_common.theme as theme_mod
from desktop_app_common.theme import is_dark_mode


class TestIsDarkModeDispatch:
    def test_unsupported_platform_returns_false(self):
        with mock.patch.object(theme_mod, "IS_WINDOWS", False), \
             mock.patch.object(theme_mod, "IS_MAC", False), \
             mock.patch.object(theme_mod, "IS_LINUX", False):
            assert is_dark_mode() is False


class TestIsDarkModeMacOS:
    def test_dark_mode(self):
        result = subprocess.CompletedProcess([], 0, stdout="Dark\n", stderr="")
        with mock.patch.object(theme_mod, "IS_WINDOWS", False), \
             mock.patch.object(theme_mod, "IS_MAC", True), \
             mock.patch("desktop_app_common.theme.subprocess.run", return_value=result):
            assert is_dark_mode() is True

    def test_light_mode(self):
        result = subprocess.CompletedProcess([], 1, stdout="", stderr="")
        with mock.patch.object(theme_mod, "IS_WINDOWS", False), \
             mock.patch.object(theme_mod, "IS_MAC", True), \
             mock.patch("desktop_app_common.theme.subprocess.run", return_value=result):
            assert is_dark_mode() is False

    def test_defaults_not_found(self):
        with mock.patch.object(theme_mod, "IS_WINDOWS", False), \
             mock.patch.object(theme_mod, "IS_MAC", True), \
             mock.patch("desktop_app_common.theme.subprocess.run",
                        side_effect=FileNotFoundError):
            assert is_dark_mode() is False


class TestIsDarkModeLinux:
    def test_prefer_dark(self):
        result = subprocess.CompletedProcess([], 0, stdout="'prefer-dark'\n", stderr="")
        with mock.patch.object(theme_mod, "IS_WINDOWS", False), \
             mock.patch.object(theme_mod, "IS_MAC", False), \
             mock.patch.object(theme_mod, "IS_LINUX", True), \
             mock.patch("desktop_app_common.theme.subprocess.run", return_value=result):
            assert is_dark_mode() is True

    def test_prefer_light(self):
        result = subprocess.CompletedProcess([], 0, stdout="'default'\n", stderr="")
        with mock.patch.object(theme_mod, "IS_WINDOWS", False), \
             mock.patch.object(theme_mod, "IS_MAC", False), \
             mock.patch.object(theme_mod, "IS_LINUX", True), \
             mock.patch("desktop_app_common.theme.subprocess.run", return_value=result):
            assert is_dark_mode() is False

    def test_no_gsettings(self):
        with mock.patch.object(theme_mod, "IS_WINDOWS", False), \
             mock.patch.object(theme_mod, "IS_MAC", False), \
             mock.patch.object(theme_mod, "IS_LINUX", True), \
             mock.patch("desktop_app_common.theme.subprocess.run",
                        side_effect=FileNotFoundError):
            assert is_dark_mode() is False


class TestIsDarkModeWindows:
    def test_dark_mode_value_zero(self):
        mock_winreg = mock.MagicMock()
        mock_key = mock.MagicMock()
        mock_winreg.OpenKey.return_value.__enter__ = mock.Mock(return_value=mock_key)
        mock_winreg.OpenKey.return_value.__exit__ = mock.Mock(return_value=False)
        mock_winreg.QueryValueEx.return_value = (0, 4)
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        with mock.patch.object(theme_mod, "IS_WINDOWS", True), \
             mock.patch.object(theme_mod, "IS_MAC", False), \
             mock.patch.dict("sys.modules", {"winreg": mock_winreg}):
            assert is_dark_mode() is True

    def test_light_mode_value_one(self):
        mock_winreg = mock.MagicMock()
        mock_key = mock.MagicMock()
        mock_winreg.OpenKey.return_value.__enter__ = mock.Mock(return_value=mock_key)
        mock_winreg.OpenKey.return_value.__exit__ = mock.Mock(return_value=False)
        mock_winreg.QueryValueEx.return_value = (1, 4)
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        with mock.patch.object(theme_mod, "IS_WINDOWS", True), \
             mock.patch.object(theme_mod, "IS_MAC", False), \
             mock.patch.dict("sys.modules", {"winreg": mock_winreg}):
            assert is_dark_mode() is False

    def test_key_missing(self):
        mock_winreg = mock.MagicMock()
        mock_winreg.OpenKey.side_effect = FileNotFoundError
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        with mock.patch.object(theme_mod, "IS_WINDOWS", True), \
             mock.patch.object(theme_mod, "IS_MAC", False), \
             mock.patch.dict("sys.modules", {"winreg": mock_winreg}):
            assert is_dark_mode() is False
