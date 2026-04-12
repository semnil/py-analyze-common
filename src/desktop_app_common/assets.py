"""Cross-platform binary names and download helpers for bundled tools.

Keeps only the platform mapping. URL discovery and checksum verification live
in each project's build.py to accommodate project-specific requirements.
"""

from __future__ import annotations

from desktop_app_common.platform import IS_MAC, IS_WINDOWS


def exe(name: str) -> str:
    """Append the platform-appropriate executable suffix."""
    return f"{name}.exe" if IS_WINDOWS else name


def required_bins() -> list[str]:
    """Return the list of bundled binary basenames for the current platform."""
    return [exe("ffmpeg"), exe("ffprobe"), exe("yt-dlp")]


def ytdlp_asset_name() -> str:
    """Return the yt-dlp release asset filename for the current platform."""
    if IS_WINDOWS:
        return "yt-dlp.exe"
    if IS_MAC:
        return "yt-dlp_macos"
    return "yt-dlp"
