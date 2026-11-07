"""Audio download (yt-dlp) and filename utilities."""

import math
import re
import threading
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import Popen as YtDlpPopen

from analyze_common.platform import find_executable
from analyze_common.programs import start_program

_yt_dlp_programs_lock = threading.Lock()
_yt_dlp_programs_watched = False


_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def is_url(s: str) -> bool:
    """Check if a string looks like an HTTP(S) URL."""
    return s.startswith("http://") or s.startswith("https://")


def sanitize_filename(name: str) -> str:
    """Remove or replace characters that are unsafe for filenames.

    Rejects null byte and ASCII control characters (0x00-0x1F) in addition to
    the usual Windows-reserved set.  Prefixes '_' when the stem matches a
    Windows-reserved device name (CON, PRN, COM1-9, LPT1-9, ...).
    """
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name)
    name = name.strip(". ")
    if not name:
        return "untitled"
    stem, _dot, _ext = name.partition(".")
    if stem.upper() in _WINDOWS_RESERVED_NAMES:
        name = "_" + name
    return name[:200]


def _stop_yt_dlp_programs_at_exit() -> None:
    """Make the programs yt-dlp starts, all of which go through its Popen, end with this process (start_program)."""
    global _yt_dlp_programs_watched
    with _yt_dlp_programs_lock:
        if _yt_dlp_programs_watched:
            return
        start = YtDlpPopen.__init__

        def start_with_this_process(self, *args, **kwargs):
            start_program(lambda: start(self, *args, **kwargs) or self)

        YtDlpPopen.__init__ = start_with_this_process
        _yt_dlp_programs_watched = True


def download_audio(url: str, workdir: str) -> tuple[str, str]:
    """Download audio track via yt-dlp Python API and return (file_path, title).

    yt-dlp runs ffmpeg (and the ffprobe next to it) and deno from the paths
    find_executable() gives.  FileNotFoundError when ffmpeg is not on PATH;
    without deno on PATH yt-dlp runs with no JavaScript runtime.  The programs
    yt-dlp starts end with this process.
    """
    _stop_yt_dlp_programs_at_exit()
    ffmpeg = find_executable("ffmpeg")
    if ffmpeg is None:
        raise FileNotFoundError("ffmpeg was not found on PATH")
    deno = find_executable("deno")
    template = str(Path(workdir) / "%(id)s.%(ext)s")
    opts = {
        "format": "bestaudio/best",
        "outtmpl": template,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "ffmpeg_location": ffmpeg,
        "js_runtimes": {"deno": {"path": deno}} if deno else {},
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "opus",
            "preferredquality": "0",
        }],
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:
        raise RuntimeError(f"yt-dlp failed: {e}") from e

    title = (info or {}).get("title") or "Untitled"
    files = sorted(
        (f for f in Path(workdir).iterdir() if f.is_file()),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if files:
        return str(files[0]), title
    raise FileNotFoundError("yt-dlp produced no audio file")


def compute_middle(total_sec: float, duration_min: float) -> tuple[float | None, float | None, str]:
    """Return (start_sec, extract_sec, info_message) for the middle segment.

    When total_sec is no longer than duration_min, the whole source is used: start_sec and extract_sec are None, so
    ffmpeg reads to the end of the source, which can lie past the total_sec ffprobe estimated.
    """
    if not math.isfinite(total_sec) or total_sec <= 0:
        raise ValueError(f"total_sec must be a positive finite number, got {total_sec}")
    if not math.isfinite(duration_min) or duration_min <= 0:
        raise ValueError(f"duration_min must be a positive finite number, got {duration_min}")
    extract_sec = duration_min * 60
    if total_sec <= extract_sec:
        msg = f"Source shorter than {duration_min}m -- using full duration ({total_sec:.0f}s)"
        return None, None, msg
    start = (total_sec - extract_sec) / 2
    msg = f"Total {total_sec:.0f}s -> extracting {start:.0f}s - {start + extract_sec:.0f}s"
    return start, extract_sec, msg
