"""Shared platform abstraction layer for pywebview-based desktop apps."""

from desktop_app_common.platform import (
    IS_FROZEN,
    IS_LINUX,
    IS_MAC,
    IS_WINDOWS,
    subprocess_kwargs,
)
from desktop_app_common.theme import is_dark_mode

__all__ = [
    "IS_FROZEN",
    "IS_LINUX",
    "IS_MAC",
    "IS_WINDOWS",
    "is_dark_mode",
    "subprocess_kwargs",
    "__version__",
]

__version__ = "0.1.1"
