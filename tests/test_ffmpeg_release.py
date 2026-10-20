"""Tests for analyze_common.ffmpeg_release (pin file, osxexperts.net page, BtbN, detect)."""

import hashlib
import io
import json
import os
import subprocess
import zipfile

import pytest

from analyze_common import ffmpeg_release as fr

DIGEST_FFMPEG = "591260c945d0eef150e3bf82b0ef988bd36a9cecc18ff05d6679617159f0a95e"
DIGEST_FFPROBE = "e11c17e8200b3ee4c4c186d245e2b4053f01d56957336c1817fca0b997469106"


def _entry(tool, version, platform, url, digest):
    return (
        '<div class="col-md-6 text-left">\n'
        f'\t<a href="{url}" class="btn btn-c-5861" target="_blank">Download {tool} {version} ({platform})</a>\n'
        '\t<p class="p-bloc-1-style">\n'
        f'\t\t<br>SHA256 checksum of {tool.capitalize()} file : {digest}<br>Source used to compile : '
        '<a href="https://github.com/FFmpeg/FFmpeg" target="_blank">here</a><br>\n'
        '\t</p>\n'
        '</div>\n'
    )


def _page(*entries):
    return "<html><body>\n" + "".join(entries) + "</body></html>\n"


def _site_page(version="9.0", stem="9"):
    return _page(
        _entry("ffmpeg", version, "Apple Silicon", f"https://www.osxexperts.net/ffmpeg{stem}arm.zip", DIGEST_FFMPEG),
        _entry("ffmpeg", "8.0", "Intel", "https://www.osxexperts.net/ffmpeg80intel.zip", "d" * 64),
        _entry("ffprobe", version, "Apple Silicon", f"https://www.osxexperts.net/ffprobe{stem}arm.zip",
               DIGEST_FFPROBE.upper()),
        _entry("ffprobe", "8.0", "Intel", "https://www.osxexperts.net/ffprobe80intel.zip", "e" * 64),
        _entry("ffplay", version, "Apple Silicon", f"https://www.osxexperts.net/ffplay{stem}arm.zip", "f" * 64),
    )


def _pin(series="8.1", stem="81", ffmpeg="a" * 64, ffprobe="b" * 64):
    return {
        "series": series,
        "macos_arm64": {
            "ffmpeg": {"url": f"https://www.osxexperts.net/ffmpeg{stem}arm.zip", "sha256": ffmpeg},
            "ffprobe": {"url": f"https://www.osxexperts.net/ffprobe{stem}arm.zip", "sha256": ffprobe},
        },
    }


OFFER_90 = _pin("9.0", "9", DIGEST_FFMPEG, DIGEST_FFPROBE)


class TestParseOsxexperts:
    def test_reads_the_apple_silicon_ffmpeg_and_ffprobe(self):
        assert fr.parse_osxexperts(_site_page()) == OFFER_90

    def test_lowercases_the_page_digest(self):
        offer = fr.parse_osxexperts(_site_page())
        assert offer["macos_arm64"]["ffprobe"]["sha256"] == DIGEST_FFPROBE

    def test_missing_tool_fails(self):
        html = _page(_entry("ffmpeg", "9.0", "Apple Silicon", "https://www.osxexperts.net/ffmpeg9arm.zip", "a" * 64))
        with pytest.raises(fr.FfmpegReleaseError, match="no Apple Silicon ffprobe"):
            fr.parse_osxexperts(html)

    def test_only_intel_builds_fail(self):
        html = _page(
            _entry("ffmpeg", "8.0", "Intel", "https://www.osxexperts.net/ffmpeg80intel.zip", "a" * 64),
            _entry("ffprobe", "8.0", "Intel", "https://www.osxexperts.net/ffprobe80intel.zip", "b" * 64),
        )
        with pytest.raises(fr.FfmpegReleaseError, match="no Apple Silicon ffmpeg, ffprobe"):
            fr.parse_osxexperts(html)

    def test_two_apple_silicon_builds_of_one_tool_fail(self):
        html = _site_page() + _entry("ffmpeg", "8.1", "Apple Silicon",
                                     "https://www.osxexperts.net/ffmpeg81arm.zip", "c" * 64)
        with pytest.raises(fr.FfmpegReleaseError, match="more than one Apple Silicon ffmpeg"):
            fr.parse_osxexperts(html)

    def test_different_versions_fail(self):
        html = _page(
            _entry("ffmpeg", "9.0", "Apple Silicon", "https://www.osxexperts.net/ffmpeg9arm.zip", "a" * 64),
            _entry("ffprobe", "8.1", "Apple Silicon", "https://www.osxexperts.net/ffprobe81arm.zip", "b" * 64),
        )
        with pytest.raises(fr.FfmpegReleaseError, match="different versions"):
            fr.parse_osxexperts(html)

    def test_version_that_is_not_major_minor_fails(self):
        with pytest.raises(fr.FfmpegReleaseError, match="not a MAJOR.MINOR series"):
            fr.parse_osxexperts(_site_page(version="9.0.1", stem="901"))

    def test_digest_is_read_before_the_next_download_only(self):
        html = _page(
            '<a href="https://www.osxexperts.net/ffmpeg9arm.zip" class="btn">Download ffmpeg 9.0 (Apple Silicon)</a>\n',
            _entry("ffprobe", "9.0", "Apple Silicon", "https://www.osxexperts.net/ffprobe9arm.zip", DIGEST_FFPROBE),
        )
        with pytest.raises(fr.FfmpegReleaseError, match="no SHA256 for the Apple Silicon ffmpeg"):
            fr.parse_osxexperts(html)

    @pytest.mark.parametrize("url", [
        "http://www.osxexperts.net/ffmpeg9arm.zip",
        "https://osxexperts.example/ffmpeg9arm.zip",
        "https://www.osxexperts.net/ffmpeg9arm.dmg",
    ])
    def test_download_outside_osxexperts_zip_fails(self, url):
        html = _site_page().replace("https://www.osxexperts.net/ffmpeg9arm.zip", url)
        with pytest.raises(fr.FfmpegReleaseError, match="is not an https://www.osxexperts.net/ zip"):
            fr.parse_osxexperts(html)


class TestPin:
    def test_round_trip(self, tmp_path):
        path = tmp_path / "ffmpeg.json"
        path.write_text(fr.dump_pin(OFFER_90), encoding="utf-8")
        assert fr.load_pin(path) == OFFER_90

    @pytest.mark.parametrize("mutate, message", [
        (lambda p: p.update(series="9"), "MAJOR.MINOR"),
        (lambda p: p["macos_arm64"].pop("ffprobe"), "exactly ffmpeg, ffprobe"),
        (lambda p: p["macos_arm64"]["ffmpeg"].update(sha256="A" * 64), "64 lowercase hex"),
        (lambda p: p["macos_arm64"]["ffmpeg"].update(url="https://example.com/ffmpeg.zip"), "not an https://"),
        (lambda p: p["macos_arm64"]["ffmpeg"].update(extra=1), "exactly \"url\" and \"sha256\""),
    ])
    def test_malformed_pin_fails(self, mutate, message):
        pin = json.loads(json.dumps(OFFER_90))
        mutate(pin)
        with pytest.raises(fr.FfmpegReleaseError, match=message):
            fr.validate_pin(pin)

    def test_unreadable_pin_fails(self, tmp_path):
        path = tmp_path / "ffmpeg.json"
        path.write_text("{", encoding="utf-8")
        with pytest.raises(fr.FfmpegReleaseError, match="cannot read the pin"):
            fr.load_pin(path)


def _btbn(*names):
    return {"tag_name": "latest", "assets": [
        {"name": name, "browser_download_url": f"https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/{name}"}
        for name in names
    ]}


class TestBtbnAsset:
    def test_prefers_lgpl(self):
        release = _btbn("ffmpeg-master-latest-win64-lgpl.zip", "ffmpeg-n9.0-latest-win64-gpl-9.0.zip",
                        "ffmpeg-n9.0-latest-win64-lgpl-9.0.zip", "ffmpeg-n8.1-latest-win64-lgpl-8.1.zip")
        assert fr.btbn_asset(release, "9.0")["name"] == "ffmpeg-n9.0-latest-win64-lgpl-9.0.zip"

    def test_falls_back_to_gpl(self):
        release = _btbn("ffmpeg-n9.0-latest-win64-gpl-9.0.zip", "ffmpeg-n9.0-latest-win64-lgpl-shared-9.0.zip")
        asset = fr.btbn_asset(release, "9.0")
        assert asset["name"] == "ffmpeg-n9.0-latest-win64-gpl-9.0.zip"
        assert asset["url"].endswith("/ffmpeg-n9.0-latest-win64-gpl-9.0.zip")

    def test_missing_series_fails(self):
        release = _btbn("ffmpeg-master-latest-win64-lgpl.zip", "ffmpeg-n9.0-latest-win64-lgpl-9.0.zip",
                        "ffmpeg-n9.0-latest-linux64-lgpl-9.0.tar.xz")
        with pytest.raises(fr.FfmpegReleaseError, match="no win64 build of the 8.1 series"):
            fr.btbn_asset(release, "8.1")


def _zip(**files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class TestFetchMacosBinary:
    def test_returns_the_binary_that_matches(self, http_server):
        binary = b"\xcf\xfa\xed\xfe arm64 ffmpeg"
        http_server.add("/ffmpeg9arm.zip", _zip(**{"__MACOSX/._ffmpeg": b"x", "ffmpeg": binary, "ffprobe": b"other"}))
        entry = {"url": http_server.base + "/ffmpeg9arm.zip", "sha256": hashlib.sha256(binary).hexdigest()}
        assert fr.fetch_macos_binary(entry, "ffmpeg") == binary

    def test_zip_with_two_files_of_the_name_fails(self, http_server):
        http_server.add("/ffmpeg9arm.zip", _zip(**{"a/ffmpeg": b"1", "b/ffmpeg": b"2"}))
        entry = {"url": http_server.base + "/ffmpeg9arm.zip", "sha256": "0" * 64}
        with pytest.raises(fr.FfmpegReleaseError, match="2 files named ffmpeg"):
            fr.fetch_macos_binary(entry, "ffmpeg")

    def test_digest_mismatch_fails(self, http_server):
        http_server.add("/ffprobe9arm.zip", _zip(ffprobe=b"changed"))
        entry = {"url": http_server.base + "/ffprobe9arm.zip", "sha256": "0" * 64}
        with pytest.raises(fr.FfmpegReleaseError, match="expected 0{64}"):
            fr.fetch_macos_binary(entry, "ffprobe")


class TestVersion:
    def test_read_version(self, tmp_path):
        path = tmp_path / "__init__.py"
        path.write_text('"""pkg"""\n\n__version__ = "1.4.1"\nSCHEMA_VERSION = 3\n', encoding="utf-8")
        assert fr.read_version(path) == "1.4.1"

    def test_missing_version_fails(self, tmp_path):
        path = tmp_path / "__init__.py"
        path.write_text("VERSION = '1.0.0'\n", encoding="utf-8")
        with pytest.raises(fr.FfmpegReleaseError, match="no __version__"):
            fr.read_version(path)

    @pytest.mark.parametrize("version, expected", [("1.4.1", "1.4.2"), ("2.0.9", "2.0.10")])
    def test_next_patch(self, version, expected):
        assert fr.next_patch(version) == expected

    def test_next_patch_of_prerelease_fails(self):
        with pytest.raises(fr.FfmpegReleaseError, match="not MAJOR.MINOR.PATCH"):
            fr.next_patch("1.5.0-rc1")


class TestPlan:
    def test_new_build_on_a_released_version_bumps(self):
        assert fr.plan(_pin(), OFFER_90, "1.4.1", "v1.4.1", None) == {
            "pin_update": "true", "bump": "true", "series": "9.0", "version": "1.4.1", "next_version": "1.4.2",
        }

    def test_same_build_does_nothing(self):
        assert fr.plan(OFFER_90, OFFER_90, "1.4.1", "v1.4.1", OFFER_90) == {
            "pin_update": "false", "bump": "false", "series": "9.0", "version": "1.4.1", "next_version": "",
        }

    def test_pin_landed_after_the_release_bumps(self):
        result = fr.plan(OFFER_90, OFFER_90, "1.4.1", "v1.4.1", _pin())
        assert (result["pin_update"], result["bump"], result["next_version"]) == ("false", "true", "1.4.2")

    def test_release_without_a_pin_file_does_not_bump_by_itself(self):
        result = fr.plan(OFFER_90, OFFER_90, "1.4.1", "v1.4.1", None)
        assert (result["pin_update"], result["bump"]) == ("false", "false")

    def test_unreleased_version_updates_the_pin_without_a_bump(self):
        result = fr.plan(_pin(), OFFER_90, "1.4.2", "v1.4.1", None)
        assert (result["pin_update"], result["bump"], result["next_version"]) == ("true", "false", "")

    def test_no_release_tag_does_not_bump(self):
        result = fr.plan(_pin(), OFFER_90, "1.4.1", None, None)
        assert (result["pin_update"], result["bump"]) == ("true", "false")

    def test_changed_digest_in_the_same_series_is_an_update(self):
        offer = _pin(ffmpeg="c" * 64)
        result = fr.plan(_pin(), offer, "1.4.1", "v1.4.1", None)
        assert (result["pin_update"], result["bump"], result["series"]) == ("true", "true", "8.1")


def _git(repo, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_CONFIG_NOSYSTEM="1")
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "app"
    (root / "build_assets").mkdir(parents=True)
    (root / "src").mkdir()
    _git(root, "init", "-q", "-b", "master")
    return root


def _commit(repo, version, pin=None, tag=None):
    (repo / "src" / "__init__.py").write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    paths = ["src/__init__.py"]
    if pin is not None:
        (repo / "build_assets" / "ffmpeg.json").write_text(fr.dump_pin(pin), encoding="utf-8")
        paths.append("build_assets/ffmpeg.json")
    _git(repo, "add", *paths)
    _git(repo, "commit", "-q", "-m", f"v{version}")
    if tag:
        _git(repo, "tag", tag)


class TestReleaseTag:
    def test_highest_release_tag_by_version(self, repo):
        _commit(repo, "1.9.0", tag="v1.9.0")
        _commit(repo, "1.10.0", tag="v1.10.0")
        _commit(repo, "1.11.0-rc1", tag="v1.11.0-rc1")
        assert fr.latest_release_tag(repo) == "v1.10.0"

    def test_no_release_tag(self, repo):
        _commit(repo, "0.1.0")
        assert fr.latest_release_tag(repo) is None

    @pytest.mark.parametrize("where", [".", "build_assets"])
    def test_pin_at_a_tag(self, repo, where):
        _commit(repo, "1.4.0", tag="v1.4.0")
        _commit(repo, "1.4.1", pin=_pin(), tag="v1.4.1")
        _commit(repo, "1.4.1", pin=OFFER_90)
        pin_path = repo / "build_assets" / "ffmpeg.json"
        assert fr.pin_at(repo / where, "v1.4.0", pin_path) is None
        assert fr.pin_at(repo / where, "v1.4.1", pin_path) == _pin()


class TestDetect:
    def _run(self, repo, tmp_path, page, btbn=None, fetched=None):
        candidate = tmp_path / "candidate.json"
        fetched = [] if fetched is None else fetched
        result = fr.detect(
            repo / "build_assets" / "ffmpeg.json", repo / "src" / "__init__.py", candidate,
            fetch_page=lambda: page,
            fetch_btbn=lambda token: btbn or _btbn("ffmpeg-n9.0-latest-win64-lgpl-9.0.zip"),
            fetch_binary=lambda entry, tool: fetched.append((tool, entry["url"])),
        )
        return result, candidate

    def test_new_build_writes_the_candidate(self, repo, tmp_path):
        _commit(repo, "1.4.1", pin=_pin(), tag="v1.4.1")
        fetched = []
        result, candidate = self._run(repo, tmp_path, _site_page(), fetched=fetched)
        assert (result["pin_update"], result["bump"], result["next_version"]) == ("true", "true", "1.4.2")
        assert fr.load_pin(candidate) == OFFER_90
        assert fetched == [("ffmpeg", "https://www.osxexperts.net/ffmpeg9arm.zip"),
                           ("ffprobe", "https://www.osxexperts.net/ffprobe9arm.zip")]

    def test_series_missing_on_btbn_fails_without_a_candidate(self, repo, tmp_path):
        _commit(repo, "1.4.1", pin=_pin(), tag="v1.4.1")
        with pytest.raises(fr.FfmpegReleaseError, match="no win64 build of the 9.0 series"):
            self._run(repo, tmp_path, _site_page(), btbn=_btbn("ffmpeg-n8.1-latest-win64-lgpl-8.1.zip"))
        assert not (tmp_path / "candidate.json").exists()

    def test_pin_landed_after_the_release_resumes_the_bump(self, repo, tmp_path):
        _commit(repo, "1.4.1", pin=_pin(), tag="v1.4.1")
        _commit(repo, "1.4.1", pin=OFFER_90)
        fetched = []
        result, candidate = self._run(repo, tmp_path, _site_page(), fetched=fetched)
        assert (result["pin_update"], result["bump"], result["next_version"]) == ("false", "true", "1.4.2")
        assert not candidate.exists()
        assert fetched == []

    def test_pin_landed_with_the_bump_pending_does_not_bump_again(self, repo, tmp_path):
        _commit(repo, "1.4.1", pin=_pin(), tag="v1.4.1")
        _commit(repo, "1.4.1", pin=OFFER_90)
        _commit(repo, "1.4.2")
        result, _ = self._run(repo, tmp_path, _site_page())
        assert (result["pin_update"], result["bump"], result["next_version"]) == ("false", "false", "")

    def test_unchanged_page_writes_nothing(self, repo, tmp_path):
        _commit(repo, "1.4.1", pin=OFFER_90, tag="v1.4.1")
        fetched = []
        result, candidate = self._run(repo, tmp_path, _site_page(), fetched=fetched)
        assert (result["pin_update"], result["bump"]) == ("false", "false")
        assert not candidate.exists()
        assert fetched == []

    def test_main_appends_github_output(self, repo, tmp_path, monkeypatch, capsys):
        _commit(repo, "1.4.1", pin=OFFER_90, tag="v1.4.1")
        monkeypatch.setattr(fr, "fetch_osxexperts", lambda: _site_page())
        output = tmp_path / "github_output"
        output.write_text("earlier=1\n", encoding="utf-8")
        code = fr.main(["detect", "--pin", str(repo / "build_assets" / "ffmpeg.json"),
                        "--version-file", str(repo / "src" / "__init__.py"),
                        "--candidate", str(tmp_path / "candidate.json"), "--github-output", str(output)])
        assert code == 0
        lines = "pin_update=false\nbump=false\nseries=9.0\nversion=1.4.1\nnext_version=\n"
        assert capsys.readouterr().out == lines
        assert output.read_text(encoding="utf-8") == "earlier=1\n" + lines

    def test_main_reports_errors_with_exit_1(self, repo, tmp_path, monkeypatch, capsys):
        _commit(repo, "1.4.1", pin=OFFER_90, tag="v1.4.1")
        monkeypatch.setattr(fr, "fetch_osxexperts", lambda: "<html></html>")
        code = fr.main(["detect", "--pin", str(repo / "build_assets" / "ffmpeg.json"),
                        "--version-file", str(repo / "src" / "__init__.py"),
                        "--candidate", str(tmp_path / "candidate.json")])
        assert code == 1
        assert "error: osxexperts.net offers no Apple Silicon ffmpeg, ffprobe" in capsys.readouterr().err
