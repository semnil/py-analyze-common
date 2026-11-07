"""Shared utilities for analyze-loudness / analyze-spectrum."""

from analyze_common.download import (
    compute_middle,
    download_audio,
    is_url,
    sanitize_filename,
)
from analyze_common.ffmpeg import ffmpeg_kwargs, probe_info, run_ffmpeg
from analyze_common.json_util import json_safe
from analyze_common.platform import (
    IS_FROZEN,
    IS_LINUX,
    IS_MAC,
    IS_WINDOWS,
    find_executable,
    subprocess_kwargs,
)
from analyze_common.server import CACHE_MAX_ENTRIES, MAX_TRACKS, ClientDisconnected, GuiHandler, GuiServer
from analyze_common.settings import SettingsStore, settings_dir
from analyze_common.tempdirs import InstanceLock, sweep_orphan_tempdirs
from analyze_common.theme import is_dark_mode
from analyze_common.ui_settings import UiSettings, show_window_color_until_paint
from analyze_common.update import (
    Handoff,
    UpdateConfig,
    UpdateError,
    Updater,
    hold_instance_mutex,
)
from analyze_common.web import BOOT_JS, COMMON_CSS, I18N_JS, SETTINGS_JS, UI_JS, UPDATE_JS
from analyze_common.window import run_atexit_on_app_quit, set_app_user_model_id

__all__ = [
    "BOOT_JS",
    "CACHE_MAX_ENTRIES",
    "COMMON_CSS",
    "ClientDisconnected",
    "GuiHandler",
    "GuiServer",
    "Handoff",
    "I18N_JS",
    "IS_FROZEN",
    "InstanceLock",
    "IS_LINUX",
    "IS_MAC",
    "IS_WINDOWS",
    "MAX_TRACKS",
    "SETTINGS_JS",
    "SettingsStore",
    "UI_JS",
    "UPDATE_JS",
    "UiSettings",
    "UpdateConfig",
    "UpdateError",
    "Updater",
    "compute_middle",
    "download_audio",
    "ffmpeg_kwargs",
    "find_executable",
    "hold_instance_mutex",
    "is_dark_mode",
    "is_url",
    "json_safe",
    "probe_info",
    "run_atexit_on_app_quit",
    "run_ffmpeg",
    "sanitize_filename",
    "set_app_user_model_id",
    "settings_dir",
    "show_window_color_until_paint",
    "subprocess_kwargs",
    "sweep_orphan_tempdirs",
    "__version__",
]

__version__ = "1.0.0"
