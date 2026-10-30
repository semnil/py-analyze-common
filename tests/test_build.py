import contextlib
import io

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
