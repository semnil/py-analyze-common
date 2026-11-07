# py-analyze-common

[![Test coverage](https://codecov.io/gh/semnil/py-analyze-common/branch/main/graph/badge.svg)](https://codecov.io/gh/semnil/py-analyze-common)

> 日本語版は [README.ja.md](README.ja.md) を参照してください.

A utility library shared by analyze-loudness / analyze-spectrum (the consumers).
It provides platform abstraction, an ffmpeg/ffprobe wrapper, yt-dlp downloads, JSON sanitization, app auto-update, storage of the theme and language settings, the request handling and frontend files the two graphical user interface (GUI) apps share, the consumers' build, and tests the consumers run on their own repository.

## Modules

Paths are relative to `src/analyze_common/`, except `installer/auto_update.iss`, which is relative to the repository root.

- `__init__.py` — the public API (`__all__`) and `__version__`
- `platform.py` — OS detection, subprocess kwargs, frozen build detection, `find_executable()` (absolute path of a program on PATH)
- `theme.py` — dark mode detection (Windows registry / macOS `defaults` / Linux `gsettings` + `kreadconfig5`)
- `ffmpeg.py` — `ffmpeg_kwargs()` (subprocess kwargs with LC_ALL=C), `run_ffmpeg()` (`subprocess.run()` for a program that ends with the process), `probe_info()` (ffprobe JSON parsing)
- `download.py` — `download_audio()` (yt-dlp), `sanitize_filename()`, `compute_middle()`, `is_url()`
- `programs.py` — `start_program()`: starts a program that ends with the process. `run_ffmpeg()` and the programs yt-dlp runs start through it
- `json_util.py` — `json_safe()` (converts NaN/Infinity to None)
- `update.py` — the auto-update client (`UpdateConfig`, `Updater`, `hold_instance_mutex()`). It checks `latest.json` of the latest GitHub Release, downloads the installer, verifies its Ed25519 signature, and applies it with the installer on Windows and by swapping the `.app` on macOS. [docs/auto-update.md](docs/auto-update.md) describes how an update runs
- `settings.py` — reading and writing the per-product user settings file (JSON) (`SettingsStore`, `settings_dir()`). Holds the auto-update "Check at launch" setting, the theme and the language
- `ui_settings.py` — the theme and language settings (`UiSettings`): value validation, the pywebview window's background color, and the script that hands the stored values to the page. `show_window_color_until_paint()` shows the window's background color on macOS until the page paints
- `ed25519.py` — Ed25519 signature verification (RFC 8032, pure Python, verification only)
- `update_manifest.py` — a command-line interface (CLI) that creates and signs `latest.json` in continuous integration (CI) (`python -m analyze_common.update_manifest sign | public-key`). Signing uses `openssl pkeyutl -rawin`
- `ffmpeg_release.py` — reading and writing the pin of the bundled ffmpeg / ffprobe (the consumer's `build_assets/ffmpeg.json`), downloading from osxexperts.net (macOS) and BtbN/FFmpeg-Builds (Windows) and checking the SHA256, and detecting new builds (`python -m analyze_common.ffmpeg_release detect`)
- `server.py` — `GuiServer`, the HTTP server both GUIs start, `CACHE_MAX_ENTRIES` and `MAX_TRACKS`, the limits both GUIs share, and `GuiHandler`, the request handling both GUI servers share (the Host and Content-Type checks, `/common/*`, `/browse`, `/save-image`, `/settings`, `/update/*`, JSON and newline-delimited JSON (NDJSON) answers); the consumer's handler extends it with its own state and endpoints
- `window.py` — process setup for one OS: on Windows the AppUserModelID (`set_app_user_model_id()`), so the taskbar shows the EXE's icon; on macOS the atexit functions run on Quit (`run_atexit_on_app_quit()`)
- `tempdirs.py` — `InstanceLock`, which marks a process as a running instance of a program, and `sweep_orphan_tempdirs()`, which removes the temp folders a killed process left behind unless another instance runs
- `network.py` — HTTPS fetching (`urlopen()`, `HTTPSHandler`) whose failed connection names every address it tried with its error. `ffmpeg_release.py`, `update.py` and `build.py` fetch through it
- `build.py` — the consumer's build: downloading the bundled assets (deno, ffmpeg / ffprobe, uPlot), checking uPlot against `checksums.json`, PyInstaller, and the Inno Setup installer / disk image (DMG). The consumer's `build.py` passes its names (`App`) to `main()`
- `icons.py` — `icon.ico`, `icon.png` and `icon.iconset/` from the consumer's `build_assets/icon_draft.svg` (`python -m analyze_common.icons build_assets`; needs resvg-py and Pillow)
- `testing/` — tests the consumers run on their own repository: `release.yaml` and `requirements/*.txt` (`release_workflow`), the GNU General Public License (GPL) texts and their bundling (`third_party_licenses`), yt-dlp-ejs against yt-dlp (`yt_dlp_ejs`), and the font family of canvas text (`chart_font`). The consumer's `tests/conftest.py` calls `testing.configure()`
- `web/__init__.py` — the paths of the `web/` files (`WEB_DIR`, `COMMON_CSS`, `SETTINGS_JS`, `UPDATE_JS`, `I18N_JS`, `BOOT_JS`, `UI_JS`)
- `web/common.css` — CSS variables and component styles shared by both GUIs. Its path is `COMMON_CSS`
- `web/settings.js` — receiving and saving the stored theme and language, shared by both GUIs (`window.analyzeSettings`). Its path is `SETTINGS_JS`
- `web/update.js` — the settings button, the settings dialog and the update check flow, shared by both GUIs. Its path is `UPDATE_JS`
- `web/i18n.js` — the en / ja translation both GUIs share: the GUI's `i18n.js` hands its dictionary to `window.analyzeI18n.install()`, which sets `window.i18n`. Its path is `I18N_JS`
- `web/boot.js` — sets the theme and the language on `<html>` before the CSS paints. Its path is `BOOT_JS`
- `web/ui.js` — UI helpers both GUIs' `main.js` call: the fonts of canvas text (`CHART_FONT_FAMILY`, `CHART_AXIS_FONTS`), the most tracks of a comparison (`MAX_TRACKS`), icons, the theme toggle's drawing, the icons of the input bar's buttons, the rows of the comparison queue, keeping the focus and the scroll position through redraws, the redraw after a change of the window's size, the result title row, tooltips, reserved button widths, the drop overlay's text and the status area's error line. Its path is `UI_JS`
- `installer/auto_update.iss` — an Inno Setup include. The installer launched by auto-update waits for the app to exit, and launches the app after installing

## Usage (as a git submodule)

```bash
git submodule add https://github.com/semnil/py-analyze-common vendor/py-analyze-common
```

The consumer adds `vendor/py-analyze-common/src` to `sys.path` and imports from `analyze_common`.

## Building a consumer

The consumer's `build.py` runs `analyze_common.build` with its names:

```bash
python build.py              # download assets + PyInstaller bundle
python build.py --installer  # + Inno Setup installer (.exe) / DMG (macOS)
```

Prerequisites:

- PyInstaller (`pip install pyinstaller`, or the `dev` extra) and certifi (`pip install -e ".[gui]"`). The build stops without them
- Inno Setup 6 (only when generating the Windows installer)
- create-dmg (only when generating the macOS DMG: `brew install create-dmg`)

`build.py` downloads the following automatically:

- ffmpeg / ffprobe (Windows: BtbN/FFmpeg-Builds, macOS: osxexperts.net. The series and the macOS URL and SHA256 are in `build_assets/ffmpeg.json`)
- deno (the latest GitHub release, needed for yt-dlp's YouTube JavaScript extraction)
- uPlot (jsDelivr CDN)

yt-dlp is managed as a Python dependency (`pyproject.toml`), and PyInstaller bundles it automatically.

uPlot is checked against the SHA256 in `build_assets/checksums.json` (`python build.py --update-checksums` updates that file), and the macOS ffmpeg / ffprobe against the SHA256 in `build_assets/ffmpeg.json`. deno and the Windows ffmpeg / ffprobe are not pinned.

| Flag | Description |
|---|---|
| `--installer` | Also builds the installer (Inno Setup / DMG) |
| `--skip-download` | Skips downloading the assets |
| `--skip-build` | Skips PyInstaller (assumes `dist/` exists) |
| `--update-checksums` | Downloads the assets, updates `build_assets/checksums.json` and stops |
| `--ffmpeg-only` | Downloads only ffmpeg / ffprobe into `build_assets/bin/` and stops |

## Platform notes

- Priority of Linux dark mode detection:
  1. GNOME: `gsettings get org.gnome.desktop.interface color-scheme`
  2. GNOME: `gsettings get org.gnome.desktop.interface gtk-theme`
  3. KDE: `kreadconfig5 --group General --key ColorScheme` (True if the value contains "dark")
- In environments where none of the above is available (XFCE / Cinnamon etc. without kreadconfig5 installed), it falls back to `False`.
- `subprocess_kwargs()` returns a new `dict` on every call. Callers must not cache or reuse it (restoring DYLD_* in a frozen build depends on a snapshot of the environment variables at that moment).
- `probe_info()` runs ffprobe, and `download_audio()` hands yt-dlp ffmpeg (with the ffprobe next to it) and deno, by the absolute path `find_executable()` returns. It searches only the absolute entries of `PATH`, so the current directory is searched only when `PATH` names it by an absolute path; on Windows a bare program name would be looked up in the current directory before `PATH` ([CreateProcessW](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw)). `probe_info()` raises `FileNotFoundError` without ffprobe on `PATH`, and `download_audio()` without ffmpeg; without deno, yt-dlp runs with no JavaScript runtime.

## Compatibility policy

- The public API is defined solely by `__all__` in `src/analyze_common/__init__.py`. Symbols not in `__all__` are internal and may be changed or removed without notice.
- Follows Semantic Versioning:
  - `MINOR` (x.y.z to x.y+1.0) keeps backward compatibility. New APIs are only added.
  - `MAJOR` (x.y.z to x+1.0.0) allows breaking changes. A commit containing a breaking change describes it in the message body.
- See `git log` for the change history.

## License

MIT
