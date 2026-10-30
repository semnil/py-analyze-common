# py-analyze-common

[![Test coverage](https://codecov.io/gh/semnil/py-analyze-common/branch/main/graph/badge.svg)](https://codecov.io/gh/semnil/py-analyze-common)

> 日本語版は [README.ja.md](README.ja.md) を参照してください.

A utility library shared by analyze-loudness / analyze-spectrum.
It provides platform abstraction, an ffmpeg/ffprobe wrapper, yt-dlp downloads, JSON sanitization, app auto-update, and storage of the theme and language settings.

## Modules

- `platform.py` — OS detection, subprocess kwargs, frozen build detection, `find_executable()` (absolute path of a program on PATH)
- `theme.py` — dark mode detection (Windows registry / macOS `defaults` / Linux `gsettings` + `kreadconfig5`)
- `ffmpeg.py` — `ffmpeg_kwargs()` (subprocess kwargs with LC_ALL=C), `probe_info()` (ffprobe JSON parsing)
- `download.py` — `download_audio()` (yt-dlp), `sanitize_filename()`, `compute_middle()`, `is_url()`
- `json_util.py` — `json_safe()` (NaN/Infinity → None conversion)
- `update.py` — the auto-update client (`UpdateConfig`, `Updater`, `hold_instance_mutex()`). It checks `latest.json` of the latest GitHub Release, downloads the installer, verifies its Ed25519 signature, and applies it with the installer on Windows and by swapping the `.app` on macOS
- `settings.py` — reading and writing the per-product user settings file (JSON) (`SettingsStore`, `settings_dir()`). Holds the auto-update "Check at launch" setting, the theme and the language
- `ui_settings.py` — the theme and language settings (`UiSettings`): value validation, the pywebview window's background color, and the script that hands the stored values to the page. `show_window_color_until_paint()` shows the window's background color on macOS until the page paints
- `ed25519.py` — Ed25519 signature verification (RFC 8032, pure Python, verification only)
- `update_manifest.py` — a CLI that creates and signs `latest.json` in CI (`python -m analyze_common.update_manifest sign | public-key`). Signing uses `openssl pkeyutl -rawin`
- `ffmpeg_release.py` — reading and writing the pin of the bundled ffmpeg / ffprobe (the consumer's `build_assets/ffmpeg.json`), downloading from osxexperts.net (macOS) and BtbN/FFmpeg-Builds (Windows) and checking the SHA256, and detecting new builds (`python -m analyze_common.ffmpeg_release detect`)
- `server.py` — `GuiHandler`, the request handling both GUI servers share (the Host and Content-Type checks, `/common/*`, `/browse`, `/save-image`, `/settings`, `/update/*`, JSON and NDJSON answers); the consumer's handler extends it with its own state and endpoints
- `window.py` — Windows-only process setup: the AppUserModelID (`set_app_user_model_id()`), so the taskbar shows the EXE's icon
- `network.py` — HTTPS fetching (`urlopen()`, `HTTPSHandler`) whose failed connection names every address it tried with its error. `ffmpeg_release.py` and `update.py` fetch through it
- `web/common.css` — CSS variables and component styles shared by both GUIs. Its path is `COMMON_CSS`
- `web/settings.js` — receiving and saving the stored theme and language, shared by both GUIs (`window.analyzeSettings`). Its path is `SETTINGS_JS`
- `web/update.js` — the settings button, the settings dialog and the update check flow, shared by both GUIs. Its path is `UPDATE_JS`
- `web/i18n.js` — the en / ja translation both GUIs share: the GUI's `i18n.js` hands its dictionary to `window.analyzeI18n.install()`, which sets `window.i18n`. Its path is `I18N_JS`
- `web/boot.js` — sets the theme and the language on `<html>` before the CSS paints. Its path is `BOOT_JS`
- `web/ui.js` — UI helpers both GUIs' `main.js` call: icons, the theme toggle's drawing, tooltips, reserved button widths, the drop overlay's text and the status area's error line. Its path is `UI_JS`
- `installer/auto_update.iss` — an Inno Setup include. The installer launched by auto-update waits for the app to exit, and launches the app after installing

## Usage (as git submodule)

```
git submodule add https://github.com/semnil/py-analyze-common vendor/py-analyze-common
```

Consumer adds `vendor/py-analyze-common/src` to `sys.path` and imports from `analyze_common`.

## Platform Notes

- Priority of Linux dark mode detection:
  1. GNOME: `gsettings get org.gnome.desktop.interface color-scheme`
  2. GNOME: `gsettings get org.gnome.desktop.interface gtk-theme`
  3. KDE: `kreadconfig5 --group General --key ColorScheme` (True if the value contains "dark")
- In environments where none of the above is available (XFCE / Cinnamon etc. without kreadconfig5 installed), it falls back to `False`.
- `subprocess_kwargs()` returns a new `dict` on every call. Callers must not cache or reuse it (restoring DYLD_* in a frozen build depends on a snapshot of the environment variables at that moment).
- `probe_info()` runs ffprobe, and `download_audio()` hands yt-dlp ffmpeg (with the ffprobe next to it) and deno, by the absolute path `find_executable()` returns. It searches only the absolute entries of `PATH`, so the current directory is searched only when `PATH` names it by an absolute path; on Windows a bare program name would be looked up in the current directory before `PATH` ([CreateProcessW](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw)). `probe_info()` raises `FileNotFoundError` without ffprobe on `PATH`, and `download_audio()` without ffmpeg; without deno, yt-dlp runs with no JavaScript runtime.

## Compatibility Policy

- The public API is defined solely by `__all__` in `analyze_common/__init__.py`. Symbols not in `__all__` are internal and may be changed or removed without notice.
- Follows Semantic Versioning:
  - `MINOR` (0.x.y → 0.x+1.0) keeps backward compatibility. New APIs are only added.
  - `MAJOR` (0.x → 1.0, 1.x → 2.x) allows breaking changes. A commit containing a breaking change describes it in the message body.
- See `git log` for the change history.

## License

MIT
