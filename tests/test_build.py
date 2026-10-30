import contextlib
import hashlib
import io
import zipfile

import pytest

from analyze_common import build


def _app(root, package="analyze_loudness", display_name="Loudness Analyzer"):
    return build.App(root=root, package=package, display_name=display_name, uplot_version="1.6.31")


def _app_tree(root, package="analyze_loudness", update_py='UPDATE_CONFIG = UpdateConfig(mutex_name="com.example.app")\n'):
    (root / "src" / package).mkdir(parents=True)
    (root / "src" / package / "__init__.py").write_text('__version__ = "1.2.3"\n', encoding="utf-8")
    (root / "src" / package / "update.py").write_text(update_py, encoding="utf-8")


def _run_recorder(monkeypatch):
    calls = []
    monkeypatch.setattr(build.subprocess, "run", lambda args, **kwargs: calls.append(args))
    return calls


@pytest.mark.parametrize("package, display_name, dist, dmg", [
    ("analyze_loudness", "Loudness Analyzer", "analyze-loudness", "Loudness-Analyzer.dmg"),
    ("analyze_spectrum", "Spectrum Analyzer", "analyze-spectrum", "Spectrum-Analyzer.dmg"),
])
def test_names_come_from_the_package_and_the_display_name(tmp_path, package, display_name, dist, dmg):
    app = _app(tmp_path, package, display_name)
    assert app.spec == tmp_path / f"{dist}.spec"
    assert app.dist_bundle == tmp_path / "dist" / dist
    assert app.dist_app == tmp_path / "dist" / f"{display_name}.app"
    assert app.dmg_name == dmg
    assert app.iss == tmp_path / "installer.iss"
    assert app.bin_dir == tmp_path / "build_assets" / "bin"
    assert app.vendor_dir == tmp_path / "frontend" / "vendor"
    assert app.ffmpeg_pin == tmp_path / "build_assets" / "ffmpeg.json"


def test_reads_the_version_and_the_mutex_name_of_the_package(tmp_path):
    _app_tree(tmp_path)
    app = _app(tmp_path)
    assert build._read_version(app) == "1.2.3"
    assert build._read_mutex_name(app) == "com.example.app"


def test_stops_without_a_mutex_name(tmp_path):
    _app_tree(tmp_path, update_py="UPDATE_CONFIG = None\n")
    with pytest.raises(SystemExit, match="src/analyze_loudness/update.py"):
        build._read_mutex_name(_app(tmp_path))


@pytest.mark.parametrize("certifi, stops", [(object(), False), (None, True)])
def test_stops_without_certifi(tmp_path, monkeypatch, capsys, certifi, stops):
    app = _app(tmp_path)
    app.bin_dir.mkdir(parents=True)
    for name in build.REQUIRED_BINS:
        (app.bin_dir / name).touch()
    monkeypatch.setitem(build.sys.modules, "PyInstaller", object())
    monkeypatch.setitem(build.sys.modules, "certifi", certifi)
    if stops:
        with pytest.raises(SystemExit):
            build.check_prerequisites(app)
    else:
        build.check_prerequisites(app)
    assert ("certifi not installed" in capsys.readouterr().out) == stops


def test_inno_setup_gets_the_version_and_the_mutex_name(tmp_path, monkeypatch):
    _app_tree(tmp_path)
    app = _app(tmp_path)
    monkeypatch.setattr(build.shutil, "which", lambda name: "/bin/iscc" if name == "iscc" else None)
    calls = _run_recorder(monkeypatch)
    build._build_inno(app)
    assert calls == [["/bin/iscc", "/DMyAppVersion=1.2.3", "/DMyAppMutex=com.example.app", str(app.iss)]]


def test_the_dmg_carries_the_display_name(tmp_path, monkeypatch):
    app = _app(tmp_path)
    app.dist_app.mkdir(parents=True)
    monkeypatch.setattr(build.shutil, "which", lambda name: "/bin/create-dmg" if name == "create-dmg" else None)
    calls = _run_recorder(monkeypatch)
    build._build_dmg(app)
    (args,) = calls
    assert args[args.index("--volname") + 1] == "Loudness Analyzer"
    assert args[args.index("--icon") + 1] == "Loudness Analyzer.app"
    assert args[-2:] == [str(tmp_path / "installer_output" / "Loudness-Analyzer.dmg"), str(app.dist_app)]


def test_uplot_comes_from_the_apps_version(tmp_path, monkeypatch):
    app = _app(tmp_path)
    app.vendor_dir.mkdir(parents=True)
    urls = []

    def urlopen(url):
        urls.append(url)
        return contextlib.closing(io.BytesIO(url.encode()))

    monkeypatch.setattr(build.network, "urlopen", urlopen)
    build._download_uplot(app)
    base = "https://cdn.jsdelivr.net/npm/uplot@1.6.31/dist"
    assert urls == [f"{base}/uPlot.iife.min.js", f"{base}/uPlot.min.css"]
    assert (app.vendor_dir / "uPlot.min.css").read_bytes() == f"{base}/uPlot.min.css".encode()


@pytest.mark.parametrize("argv, expected", [
    ([], ["download_assets", "_verify_checksums", "check_prerequisites", "build_pyinstaller"]),
    (["--installer"], ["download_assets", "_verify_checksums", "check_prerequisites", "build_pyinstaller",
                       "build_installer"]),
    (["--skip-download", "--skip-build", "--installer"], ["build_installer"]),
    (["--ffmpeg-only"], ["_download_ffmpeg"]),
    (["--update-checksums"], ["update_checksums"]),
])
def test_the_command_line_picks_the_steps(tmp_path, monkeypatch, argv, expected):
    app = _app(tmp_path)
    steps = []
    for name in ("download_assets", "_verify_checksums", "check_prerequisites", "build_pyinstaller",
                 "build_installer", "_download_ffmpeg", "update_checksums"):
        monkeypatch.setattr(build, name, lambda received, name=name: steps.append((name, received)))
    build.main(app, argv)
    assert steps == [(name, app) for name in expected]


def _zip(members):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    return data.getvalue()


def _response(body):
    return contextlib.closing(io.BytesIO(body))


def _platform(monkeypatch, name):
    monkeypatch.setattr(build, "IS_WINDOWS", name == "win32")
    monkeypatch.setattr(build, "IS_MAC", name == "darwin")
    monkeypatch.setattr(build, "_EXE", ".exe" if name == "win32" else "")
    monkeypatch.setattr(build.sys, "platform", name)


def _uplot(app, js=b"js", css=b"css"):
    app.vendor_dir.mkdir(parents=True, exist_ok=True)
    (app.vendor_dir / "uPlot.iife.min.js").write_bytes(js)
    (app.vendor_dir / "uPlot.min.css").write_bytes(css)


def test_checksums_are_written_read_and_verified(tmp_path, capsys):
    app = _app(tmp_path)
    assert build._load_checksums(app) == {}
    _uplot(app)
    entry = {"version": "1.6.31", "sha256_uPlot.iife.min.js": hashlib.sha256(b"js").hexdigest(),
             "sha256_uPlot.min.css": hashlib.sha256(b"css").hexdigest()}
    build._save_checksums(app, {"uplot": entry})
    assert app.checksums_file.read_text(encoding="utf-8").endswith("}\n")
    assert build._load_checksums(app) == {"uplot": entry}
    build._verify_checksums(app)
    assert "All checksums verified." in capsys.readouterr().out


@pytest.mark.parametrize("change", ["mismatch", "missing"])
def test_a_wrong_or_missing_uplot_file_stops_the_build(tmp_path, capsys, change):
    app = _app(tmp_path)
    _uplot(app)
    build._save_checksums(app, {"uplot": {"sha256_uPlot.iife.min.js": hashlib.sha256(b"js").hexdigest(),
                                          "sha256_uPlot.min.css": hashlib.sha256(b"css").hexdigest()}})
    if change == "mismatch":
        (app.vendor_dir / "uPlot.min.css").write_bytes(b"changed")
    else:
        (app.vendor_dir / "uPlot.min.css").unlink()
    with pytest.raises(SystemExit):
        build._verify_checksums(app)
    out = capsys.readouterr().out
    assert ("uPlot.min.css: MISMATCH" if change == "mismatch" else "uPlot.min.css: file not found") in out


def test_without_checksums_the_check_is_skipped_with_a_warning(tmp_path, capsys):
    build._verify_checksums(_app(tmp_path))
    assert "WARNING: checksums.json missing" in capsys.readouterr().out


def test_update_checksums_records_the_downloaded_uplot(tmp_path, monkeypatch):
    app = _app(tmp_path)
    monkeypatch.setattr(build, "download_assets", lambda received: _uplot(received, b"new js", b"new css"))
    build.update_checksums(app)
    assert build._load_checksums(app) == {"uplot": {
        "version": "1.6.31",
        "sha256_uPlot.iife.min.js": hashlib.sha256(b"new js").hexdigest(),
        "sha256_uPlot.min.css": hashlib.sha256(b"new css").hexdigest()}}


def test_download_assets_creates_the_folders_and_fetches_each_asset(tmp_path, monkeypatch):
    app = _app(tmp_path)
    fetched = []
    for name in ("_download_deno", "_download_ffmpeg", "_download_uplot"):
        monkeypatch.setattr(build, name, lambda received, name=name: fetched.append(name))
    build.download_assets(app)
    assert fetched == ["_download_deno", "_download_ffmpeg", "_download_uplot"]
    assert app.bin_dir.is_dir() and app.vendor_dir.is_dir()


@pytest.mark.parametrize("token_env", [None, "GITHUB_TOKEN", "GH_TOKEN"])
def test_github_api_requests_carry_the_token_when_there_is_one(monkeypatch, token_env):
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    if token_env:
        monkeypatch.setenv(token_env, "t0ken")
    requests = []
    monkeypatch.setattr(build.network, "urlopen", lambda req: requests.append(req) or "opened")
    assert build._github_api_open("https://api.github.com/x") == "opened"
    (req,) = requests
    assert req.full_url == "https://api.github.com/x"
    assert req.get_header("Accept") == "application/vnd.github+json"
    assert req.get_header("Authorization") == ("Bearer t0ken" if token_env else None)


@pytest.mark.parametrize("platform, asset, member", [
    ("darwin", "deno-aarch64-apple-darwin.zip", "deno"),
    ("linux", "deno-x86_64-unknown-linux-gnu.zip", "deno"),
    ("win32", "deno-x86_64-pc-windows-msvc.zip", "deno.exe"),
])
def test_deno_comes_from_the_latest_release_for_the_platform(tmp_path, monkeypatch, platform, asset, member):
    _platform(monkeypatch, platform)
    app = _app(tmp_path)
    app.bin_dir.mkdir(parents=True)
    monkeypatch.setattr(build, "_github_api_open", lambda url: _response(b'{"tag_name": "v9.9.9"}'))
    urls = []
    monkeypatch.setattr(build.network, "urlopen", lambda url: urls.append(url) or _response(_zip({member: b"deno binary"})))
    build._download_deno(app)
    assert urls == [f"https://github.com/denoland/deno/releases/download/v9.9.9/{asset}"]
    assert (app.bin_dir / member).read_bytes() == b"deno binary"


def test_the_windows_ffmpeg_url_is_the_btbn_build_of_the_pinned_series(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t0ken")
    calls = []
    monkeypatch.setattr(build.ffmpeg_release, "load_pin", lambda path: calls.append(("pin", path)) or {"series": "9.0"})
    monkeypatch.setattr(build.ffmpeg_release, "fetch_btbn_latest", lambda token: calls.append(("latest", token)) or "listing")
    monkeypatch.setattr(build.ffmpeg_release, "btbn_asset", lambda listing, series: calls.append(("asset", listing, series))
                        or {"name": "ffmpeg-n9.0-latest-win64-gpl-9.0.zip", "url": "https://example.invalid/ffmpeg.zip"})
    app = _app(tmp_path)
    assert build._get_ffmpeg_win_url(app) == "https://example.invalid/ffmpeg.zip"
    assert calls == [("pin", app.ffmpeg_pin), ("latest", "t0ken"), ("asset", "listing", "9.0")]


def test_the_windows_ffmpeg_zip_gives_only_ffmpeg_and_ffprobe(tmp_path, monkeypatch):
    app = _app(tmp_path)
    app.bin_dir.mkdir(parents=True)
    monkeypatch.setattr(build, "_get_ffmpeg_win_url", lambda received: "https://example.invalid/ffmpeg.zip")
    archive = _zip({"ffmpeg-n9.0/bin/ffmpeg.exe": b"ffmpeg", "ffmpeg-n9.0/bin/ffprobe.exe": b"ffprobe",
                    "ffmpeg-n9.0/bin/ffplay.exe": b"ffplay", "ffmpeg-n9.0/LICENSE.txt": b"license"})
    monkeypatch.setattr(build.network, "urlopen", lambda url: _response(archive))
    build._download_ffmpeg_windows(app)
    assert sorted(p.name for p in app.bin_dir.iterdir()) == ["ffmpeg.exe", "ffprobe.exe"]
    assert (app.bin_dir / "ffprobe.exe").read_bytes() == b"ffprobe"


def test_the_macos_ffmpeg_comes_from_the_pin_and_is_executable(tmp_path, monkeypatch):
    _platform(monkeypatch, "darwin")
    app = _app(tmp_path)
    app.bin_dir.mkdir(parents=True)
    pin = {"series": "9.0", "macos_arm64": {"ffmpeg": {"url": "u1"}, "ffprobe": {"url": "u2"}}}
    monkeypatch.setattr(build.ffmpeg_release, "load_pin", lambda path: pin)
    monkeypatch.setattr(build.ffmpeg_release, "fetch_macos_binary", lambda entry, name: f"{name} from {entry['url']}".encode())
    build._download_ffmpeg_macos(app)
    for name, url in (("ffmpeg", "u1"), ("ffprobe", "u2")):
        path = app.bin_dir / name
        assert path.read_bytes() == f"{name} from {url}".encode()
        assert path.stat().st_mode & 0o111 == 0o111


@pytest.mark.parametrize("platform, expected", [("win32", "windows"), ("darwin", "macos")])
def test_ffmpeg_comes_from_the_platforms_source(tmp_path, monkeypatch, platform, expected):
    _platform(monkeypatch, platform)
    fetched = []
    monkeypatch.setattr(build, "_download_ffmpeg_windows", lambda app: fetched.append("windows"))
    monkeypatch.setattr(build, "_download_ffmpeg_macos", lambda app: fetched.append("macos"))
    build._download_ffmpeg(_app(tmp_path))
    assert fetched == [expected]


def test_ffmpeg_has_no_source_on_other_platforms(tmp_path, monkeypatch):
    _platform(monkeypatch, "linux")
    with pytest.raises(RuntimeError, match="Unsupported platform: linux"):
        build._download_ffmpeg(_app(tmp_path))


def test_windows_leaves_the_file_mode_alone(tmp_path, monkeypatch):
    _platform(monkeypatch, "win32")
    path = tmp_path / "deno.exe"
    path.write_bytes(b"")
    path.chmod(0o644)
    build._make_executable(path)
    assert path.stat().st_mode & 0o777 == 0o644


def test_missing_binaries_stop_the_build(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(build.sys.modules, "PyInstaller", object())
    monkeypatch.setitem(build.sys.modules, "certifi", object())
    with pytest.raises(SystemExit):
        build.check_prerequisites(_app(tmp_path))
    out = capsys.readouterr().out
    for name in build.REQUIRED_BINS:
        assert f"Missing binary: build_assets/bin/{name}" in out


@pytest.mark.parametrize("platform, iconset, iconutil, ran", [
    ("linux", True, True, False),
    ("darwin", False, True, False),
    ("darwin", True, False, False),
    ("darwin", True, True, True),
])
def test_the_icns_is_built_from_the_iconset_on_macos(tmp_path, monkeypatch, platform, iconset, iconutil, ran):
    _platform(monkeypatch, platform)
    app = _app(tmp_path)
    if iconset:
        (app.root / "build_assets" / "icon.iconset").mkdir(parents=True)
    monkeypatch.setattr(build.shutil, "which", lambda name: "/usr/bin/iconutil" if iconutil and name == "iconutil" else None)
    calls = _run_recorder(monkeypatch)
    build._build_icns_macos(app)
    expected = [["/usr/bin/iconutil", "-c", "icns", str(app.root / "build_assets" / "icon.iconset"),
                 "-o", str(app.root / "build_assets" / "icon.icns")]]
    assert calls == (expected if ran else [])


def test_pyinstaller_builds_the_apps_spec(tmp_path, monkeypatch):
    _platform(monkeypatch, "linux")
    app = _app(tmp_path)
    calls = _run_recorder(monkeypatch)
    build.build_pyinstaller(app)
    assert calls == [[build.sys.executable, "-m", "PyInstaller", str(app.spec), "--noconfirm"]]


@pytest.mark.parametrize("platform, expected", [("win32", ["inno"]), ("darwin", ["dmg"]), ("linux", [])])
def test_the_installer_is_the_platforms(tmp_path, monkeypatch, capsys, platform, expected):
    _platform(monkeypatch, platform)
    built = []
    monkeypatch.setattr(build, "_build_inno", lambda app: built.append("inno"))
    monkeypatch.setattr(build, "_build_dmg", lambda app: built.append("dmg"))
    build.build_installer(_app(tmp_path))
    assert built == expected
    if not expected:
        assert "No installer builder configured for linux." in capsys.readouterr().out


@pytest.mark.parametrize("app_exists, create_dmg", [(False, True), (True, False)])
def test_the_dmg_is_skipped_without_the_app_or_create_dmg(tmp_path, monkeypatch, app_exists, create_dmg):
    app = _app(tmp_path)
    if app_exists:
        app.dist_app.mkdir(parents=True)
    monkeypatch.setattr(build.shutil, "which", lambda name: "/bin/create-dmg" if create_dmg else None)
    calls = _run_recorder(monkeypatch)
    build._build_dmg(app)
    assert calls == []


def test_an_old_dmg_is_replaced(tmp_path, monkeypatch):
    app = _app(tmp_path)
    app.dist_app.mkdir(parents=True)
    old = tmp_path / "installer_output" / app.dmg_name
    old.parent.mkdir()
    old.write_bytes(b"old")
    monkeypatch.setattr(build.shutil, "which", lambda name: "/bin/create-dmg")
    _run_recorder(monkeypatch)
    build._build_dmg(app)
    assert not old.exists()


def test_inno_setup_is_found_under_local_app_data_or_skipped(tmp_path, monkeypatch, capsys):
    _app_tree(tmp_path)
    app = _app(tmp_path)
    monkeypatch.setattr(build.shutil, "which", lambda name: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    calls = _run_recorder(monkeypatch)
    build._build_inno(app)
    assert calls == []
    assert "Inno Setup (ISCC.exe) not found" in capsys.readouterr().out
    iscc = tmp_path / "local" / "Programs\\Inno Setup 6\\ISCC.exe"
    iscc.parent.mkdir(parents=True, exist_ok=True)
    iscc.write_bytes(b"")
    build._build_inno(app)
    assert calls == [[str(iscc), "/DMyAppVersion=1.2.3", "/DMyAppMutex=com.example.app", str(app.iss)]]
