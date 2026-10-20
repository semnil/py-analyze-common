"""Pin the bundled ffmpeg / ffprobe and find newer builds (build.py and CI).

Each app keeps a pin file, ``build_assets/ffmpeg.json``::

    {
      "series": "8.1",
      "macos_arm64": {
        "ffmpeg": {"url": "https://www.osxexperts.net/ffmpeg81arm.zip", "sha256": "..."},
        "ffprobe": {"url": "https://www.osxexperts.net/ffprobe81arm.zip", "sha256": "..."}
      }
    }

macOS bundles the osxexperts.net Apple Silicon builds the pin names.  Each
``sha256`` is the digest of the binary inside the zip, the value the
osxexperts.net page prints next to the download.  Windows bundles the build of
the same release series in the floating ``latest`` release of
BtbN/FFmpeg-Builds (``ffmpeg-n{series}-latest-win64-lgpl-{series}.zip``, else
the ``gpl`` one), which has no pinned digest.

    python -m analyze_common.ffmpeg_release detect --pin PIN --version-file FILE \\
        --candidate OUT.json [--github-output FILE]

``detect`` compares the pin with the osxexperts.net page.  When the page
offers other builds, it requires the series in BtbN's ``latest`` release,
downloads both macOS zips, checks each binary against the page's digest and
writes the new pin to ``--candidate``.  It then decides whether the app takes
a patch release: when ``__version__`` equals the latest ``vX.Y.Z`` tag and
either the pin changes now or the pin already differs from the one that tag
released (``released_pin()``: the pin file at the tag, or, for a tag without
it, the pin file as the first commit after the tag added it).  It prints ``pin_update``, ``bump``, ``series``, ``version`` and
``next_version`` as ``key=value`` lines, and appends them to
``--github-output`` when given.
"""

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

OSXEXPERTS_URL = "https://www.osxexperts.net/"
OSXEXPERTS_HOST = "www.osxexperts.net"
BTBN_LATEST_URL = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/latest"
TOOLS = ("ffmpeg", "ffprobe")
WINDOWS_LICENSES = ("lgpl", "gpl")

_PAGE_TIMEOUT = 60
_DOWNLOAD_TIMEOUT = 300
_SERIES = re.compile(r"[0-9]+\.[0-9]+")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_RELEASE_TAG = re.compile(r"v([0-9]+)\.([0-9]+)\.([0-9]+)")
_RELEASE_VERSION = re.compile(r"([0-9]+)\.([0-9]+)\.([0-9]+)")
_VERSION_LINE = re.compile(r'^__version__\s*=\s*"([^"]*)"\s*$', re.MULTILINE)

# One Apple Silicon download button and the page text up to the next download button.
_OSXEXPERTS_ENTRY = re.compile(
    r'<a\s[^>]*?href="(?P<url>[^"]+)"[^>]*>\s*Download\s+(?P<tool>\w+)\s+(?P<version>[0-9][0-9.]*)'
    r'\s+\(Apple Silicon\)\s*</a>(?P<tail>.*?)(?=<a\s[^>]*>\s*Download\s|\Z)',
    re.IGNORECASE | re.DOTALL,
)
_PAGE_DIGEST = re.compile(r"SHA256 checksum of \w+ file\s*:\s*([0-9a-fA-F]{64})", re.IGNORECASE)


class FfmpegReleaseError(Exception):
    """The page, the pin or a download is not what this module expects."""


def _osxexperts_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != OSXEXPERTS_HOST or not parts.path.endswith(".zip"):
        raise FfmpegReleaseError(f"{url} is not an https://{OSXEXPERTS_HOST}/ zip")
    return url


def validate_pin(pin) -> dict:
    """``pin`` itself, or FfmpegReleaseError naming what is malformed."""
    if not isinstance(pin, dict) or not isinstance(pin.get("series"), str) or not _SERIES.fullmatch(pin["series"]):
        raise FfmpegReleaseError("the pin needs a MAJOR.MINOR \"series\"")
    macos = pin.get("macos_arm64")
    if not isinstance(macos, dict) or set(macos) != set(TOOLS):
        raise FfmpegReleaseError(f"the pin's \"macos_arm64\" needs exactly {', '.join(TOOLS)}")
    for tool in TOOLS:
        entry = macos[tool]
        if not isinstance(entry, dict) or set(entry) != {"url", "sha256"}:
            raise FfmpegReleaseError(f"the pin's macos_arm64.{tool} needs exactly \"url\" and \"sha256\"")
        if not isinstance(entry["url"], str):
            raise FfmpegReleaseError(f"the pin's macos_arm64.{tool}.url is not a string")
        _osxexperts_url(entry["url"])
        if not isinstance(entry["sha256"], str) or not _SHA256.fullmatch(entry["sha256"]):
            raise FfmpegReleaseError(f"the pin's macos_arm64.{tool}.sha256 is not 64 lowercase hex digits")
    return pin


def load_pin(path) -> dict:
    try:
        pin = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise FfmpegReleaseError(f"cannot read the pin {path}: {e}") from e
    return validate_pin(pin)


def dump_pin(pin: dict) -> str:
    return json.dumps(validate_pin(pin), indent=2) + "\n"


def parse_osxexperts(html: str) -> dict:
    """The Apple Silicon ffmpeg / ffprobe the osxexperts.net page offers, as a pin."""
    found = {}
    for match in _OSXEXPERTS_ENTRY.finditer(html):
        tool = match.group("tool").lower()
        if tool not in TOOLS:
            continue
        if tool in found:
            raise FfmpegReleaseError(f"osxexperts.net offers more than one Apple Silicon {tool}")
        digest = _PAGE_DIGEST.search(match.group("tail"))
        if digest is None:
            raise FfmpegReleaseError(f"osxexperts.net prints no SHA256 for the Apple Silicon {tool}")
        found[tool] = (match.group("version"), {
            "url": _osxexperts_url(match.group("url")),
            "sha256": digest.group(1).lower(),
        })
    missing = [tool for tool in TOOLS if tool not in found]
    if missing:
        raise FfmpegReleaseError(f"osxexperts.net offers no Apple Silicon {', '.join(missing)}")
    versions = sorted({found[tool][0] for tool in TOOLS})
    if len(versions) != 1:
        raise FfmpegReleaseError(f"osxexperts.net offers different versions of the tools: {', '.join(versions)}")
    if not _SERIES.fullmatch(versions[0]):
        raise FfmpegReleaseError(f"osxexperts.net names version {versions[0]}, not a MAJOR.MINOR series")
    return validate_pin({"series": versions[0], "macos_arm64": {tool: found[tool][1] for tool in TOOLS}})


def btbn_asset(release: dict, series: str) -> dict:
    """The win64 build of ``series`` in BtbN's ``latest`` release: ``{"name", "url"}``."""
    urls = {asset.get("name"): asset.get("browser_download_url") for asset in release.get("assets", [])}
    for license_name in WINDOWS_LICENSES:
        name = f"ffmpeg-n{series}-latest-win64-{license_name}-{series}.zip"
        if urls.get(name):
            return {"name": name, "url": urls[name]}
    raise FfmpegReleaseError(f"BtbN/FFmpeg-Builds latest has no win64 build of the {series} series")


def _read(url: str, timeout: int, token: str | None = None) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "analyze-common"})
    if token:
        request.add_header("Authorization", f"Bearer {token}")
        request.add_header("Accept", "application/vnd.github+json")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_osxexperts(url: str = OSXEXPERTS_URL) -> str:
    return _read(url, _PAGE_TIMEOUT).decode("utf-8", "replace")


def fetch_btbn_latest(token: str | None = None, url: str = BTBN_LATEST_URL) -> dict:
    return json.loads(_read(url, _PAGE_TIMEOUT, token))


def extract_binary(data: bytes, tool: str) -> bytes:
    """The one file named ``tool`` in the zip ``data``."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = [name for name in archive.namelist() if not name.endswith("/") and Path(name).name == tool]
        if len(members) != 1:
            raise FfmpegReleaseError(f"the zip holds {len(members)} files named {tool}, not 1")
        return archive.read(members[0])


def fetch_macos_binary(entry: dict, tool: str) -> bytes:
    """Download ``entry["url"]`` and return ``tool`` from it, checked against ``entry["sha256"]``."""
    binary = extract_binary(_read(entry["url"], _DOWNLOAD_TIMEOUT), tool)
    actual = hashlib.sha256(binary).hexdigest()
    if actual != entry["sha256"]:
        raise FfmpegReleaseError(f"{tool} from {entry['url']}: SHA256 {actual}, expected {entry['sha256']}")
    return binary


def read_version(path) -> str:
    match = _VERSION_LINE.search(Path(path).read_text(encoding="utf-8"))
    if match is None:
        raise FfmpegReleaseError(f"no __version__ line in {path}")
    return match.group(1)


def next_patch(version: str) -> str:
    match = _RELEASE_VERSION.fullmatch(version)
    if match is None:
        raise FfmpegReleaseError(f"{version} is not MAJOR.MINOR.PATCH")
    major, minor, patch = (int(part) for part in match.groups())
    return f"{major}.{minor}.{patch + 1}"


def _git(repo, *args) -> str:
    env = dict(os.environ, LC_ALL="C", LANG="C")
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise FfmpegReleaseError(f"git {' '.join(args)} failed (exit {result.returncode}): {result.stderr.strip()}")
    return result.stdout


def latest_release_tag(repo) -> str | None:
    """The highest ``vX.Y.Z`` tag reachable from HEAD."""
    tags = [tag for tag in _git(repo, "tag", "--list", "v*", "--merged", "HEAD").split()
            if _RELEASE_TAG.fullmatch(tag)]
    if not tags:
        return None
    return max(tags, key=lambda tag: tuple(int(part) for part in _RELEASE_TAG.fullmatch(tag).groups()))


def _repo_path(repo, path) -> tuple[Path, str]:
    """The repository's top directory and ``path`` relative to it."""
    top = Path(_git(repo, "rev-parse", "--show-toplevel").strip())
    return top, Path(path).resolve().relative_to(top.resolve()).as_posix()


def pin_at(repo, ref: str, path) -> dict | None:
    """The pin file at ``ref``, or None when ``ref`` has no such file."""
    top, relative = _repo_path(repo, path)
    if not _git(top, "ls-tree", "--name-only", ref, "--", relative).strip():
        return None
    try:
        return validate_pin(json.loads(_git(top, "show", f"{ref}:{relative}")))
    except ValueError as e:
        raise FfmpegReleaseError(f"the pin at {ref} is not JSON: {e}") from e


def released_pin(repo, tag: str, path) -> dict | None:
    """The pin ``tag`` released: the pin file at the tag, or, when the tag has none, the pin file as the
    first commit after the tag added it.  None when neither exists."""
    pin = pin_at(repo, tag, path)
    if pin is not None:
        return pin
    top, relative = _repo_path(repo, path)
    added = _git(top, "log", "--diff-filter=A", "--format=%H", f"{tag}..HEAD", "--", relative).split()
    return pin_at(repo, added[-1], path) if added else None


def plan(pin: dict, offer: dict, version: str, released_tag: str | None, released_pin: dict | None) -> dict:
    """What ``detect`` reports for the pin, the page's offer and the latest release."""
    pin_update = offer != pin
    released = released_tag is not None and released_tag == f"v{version}"
    bump = released and (pin_update or (released_pin is not None and released_pin != pin))
    return {
        "pin_update": "true" if pin_update else "false",
        "bump": "true" if bump else "false",
        "series": offer["series"] if pin_update else pin["series"],
        "version": version,
        "next_version": next_patch(version) if bump else "",
    }


def detect(pin_path, version_file, candidate_path, *, token=None,
           fetch_page=None, fetch_btbn=None, fetch_binary=None) -> dict:
    fetch_page = fetch_page or fetch_osxexperts
    fetch_btbn = fetch_btbn or fetch_btbn_latest
    fetch_binary = fetch_binary or fetch_macos_binary
    pin = load_pin(pin_path)
    version = read_version(version_file)
    offer = parse_osxexperts(fetch_page())
    repo = Path(pin_path).resolve().parent
    released_tag = latest_release_tag(repo)
    baseline = released_pin(repo, released_tag, pin_path) if released_tag else None
    result = plan(pin, offer, version, released_tag, baseline)
    if result["pin_update"] == "true":
        asset = btbn_asset(fetch_btbn(token), offer["series"])
        print(f"BtbN/FFmpeg-Builds latest: {asset['name']}", file=sys.stderr)
        for tool in TOOLS:
            fetch_binary(offer["macos_arm64"][tool], tool)
            print(f"osxexperts.net {tool} {offer['series']}: SHA256 matches the page", file=sys.stderr)
        Path(candidate_path).write_text(dump_pin(offer), encoding="utf-8")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m analyze_common.ffmpeg_release")
    commands = parser.add_subparsers(dest="command", required=True)
    detect_parser = commands.add_parser("detect", help="compare the pin with osxexperts.net")
    detect_parser.add_argument("--pin", required=True, type=Path)
    detect_parser.add_argument("--version-file", required=True, type=Path)
    detect_parser.add_argument("--candidate", required=True, type=Path)
    detect_parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)
    try:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        result = detect(args.pin, args.version_file, args.candidate, token=token)
    except (FfmpegReleaseError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    lines = "".join(f"{key}={value}\n" for key, value in result.items())
    sys.stdout.write(lines)
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as out:
            out.write(lines)
    return 0


if __name__ == "__main__":
    sys.exit(main())
