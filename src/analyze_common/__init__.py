"""Shared utilities for analyze-loudness / analyze-spectrum."""

from analyze_common.download import (
    compute_middle,
    download_audio,
    is_url,
    sanitize_filename,
)
from analyze_common.ffmpeg import ffmpeg_kwargs, probe_info
from analyze_common.json_util import json_safe
from analyze_common.platform import (
    IS_FROZEN,
    IS_LINUX,
    IS_MAC,
    IS_WINDOWS,
    subprocess_kwargs,
)
from analyze_common.theme import is_dark_mode

__all__ = [
    "IS_FROZEN",
    "IS_LINUX",
    "IS_MAC",
    "IS_WINDOWS",
    "compute_middle",
    "download_audio",
    "ffmpeg_kwargs",
    "is_dark_mode",
    "is_url",
    "json_safe",
    "probe_info",
    "sanitize_filename",
    "subprocess_kwargs",
    "__version__",
]

__version__ = "0.2.0"
