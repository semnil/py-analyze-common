"""FFmpeg / ffprobe subprocess helpers."""

import json
import math
import os
import subprocess

from analyze_common.platform import subprocess_kwargs


def ffmpeg_kwargs() -> dict:
    """Return subprocess kwargs with LC_ALL=C for ffmpeg / ffprobe.

    ffmpeg / ffprobe stderr / stdout parsers assume '.' as the decimal
    separator.  Non-C locales can substitute ',' and break regexes.
    """
    kwargs = dict(subprocess_kwargs())
    env = dict(kwargs["env"]) if "env" in kwargs else os.environ.copy()
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    kwargs["env"] = env
    return kwargs


def probe_info(path: str) -> tuple[int, float]:
    """Return (channels, duration_sec) via a single ffprobe call."""
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-select_streams", "a:0",
         "-show_format", path],
        capture_output=True, text=True, encoding="utf-8",
        timeout=30, **ffmpeg_kwargs(),
    )
    if r.returncode != 0:
        stderr_tail = (r.stderr or "")[-200:]
        raise RuntimeError(f"ffprobe failed (exit {r.returncode}): {stderr_tail}")
    stdout = r.stdout or ""
    if not stdout.strip():
        raise RuntimeError(f"ffprobe returned empty output for: {path}")
    info = json.loads(stdout)

    channels = 2
    streams = info.get("streams", [])
    if streams:
        channels = int(streams[0].get("channels", 2))
    if channels < 1:
        channels = 1

    dur = info.get("format", {}).get("duration")
    if dur is None:
        raise RuntimeError(f"ffprobe could not determine duration for: {path}")
    try:
        duration_sec = float(dur)
    except (TypeError, ValueError) as e:
        raise RuntimeError(
            f"ffprobe returned non-numeric duration ({dur!r}) for: {path}"
        ) from e
    if not math.isfinite(duration_sec) or duration_sec <= 0:
        raise RuntimeError(f"ffprobe returned invalid duration ({dur}) for: {path}")
    return channels, duration_sec
