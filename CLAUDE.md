# py-analyze-common

A utility library shared by analyze-loudness / analyze-spectrum.

## Documentation language

- **Override of the global CLAUDE.md's 「ドキュメント」 language rule**: this file is written entirely in English, and the README is maintained in both English and Japanese (`README.md` and `README.ja.md`, kept section for section)

## Project structure

```
py-analyze-common/
├── .github/dependabot.yml       # version updates every day at 00:00 JST of the SHA-pinned actions (github-actions) and of the yt-dlp pin in pyproject.toml (uv)
├── .github/tests/
│   └── dependabot-auto-merge-test.sh # test that dependabot-auto-merge.yml runs on every PR, with only its steps limited to Dependabot PRs, and of which updates and commits (their authors, how many, whether the last is the head, who committed it, whether its signature is verified) its step schedules or turns off an auto-merge for, with a fake gh
├── .github/workflows/
│   ├── ci.yml                   # pytest with coverage on PRs and on pushes to main, uploading coverage.xml to Codecov (required check test of main)
│   ├── dependabot-auto-merge-test.yml # runs .github/tests/dependabot-auto-merge-test.sh on PRs and pushes to main that change it or dependabot-auto-merge.yml
│   └── dependabot-auto-merge.yml # enables auto-merge on a Dependabot PR that is one commit at the head, written by Dependabot alone, committed by GitHub (web-flow) and with a verified signature, for an update of the Python dependencies (uv) or of a submodule, and for a semver patch or minor update of a GitHub Action (required check auto-merge of main)
├── CLAUDE.md
├── README.md             # English
├── README.ja.md          # Japanese
├── pyproject.toml
├── src/analyze_common/
│   ├── __init__.py       # public API (__all__), __version__
│   ├── platform.py       # IS_WINDOWS/IS_MAC/IS_LINUX/IS_FROZEN, subprocess_kwargs(), find_executable()
│   ├── theme.py          # is_dark_mode() — OS-native dark mode detection
│   ├── ffmpeg.py         # ffmpeg_kwargs(), probe_info()
│   ├── download.py       # download_audio(), sanitize_filename(), compute_middle(), is_url()
│   ├── json_util.py      # json_safe()
│   ├── update.py         # auto-update client (UpdateConfig, Updater, hold_instance_mutex)
│   ├── ed25519.py        # Ed25519 signature verification (RFC 8032, pure Python)
│   ├── update_manifest.py # for CI: creating and signing latest.json (python -m analyze_common.update_manifest)
│   ├── ffmpeg_release.py # for build.py: reading, writing and fetching the bundled ffmpeg pin (build_assets/ffmpeg.json), detecting new builds (python -m analyze_common.ffmpeg_release)
│   ├── network.py        # HTTPS fetching whose failed connection names every address it tried (for ffmpeg_release and update)
│   ├── settings.py       # SettingsStore, settings_dir() — per-OS user settings file (JSON)
│   ├── ui_settings.py    # UiSettings — theme and language settings (value validation, window background color, script handed to the page), show_window_color_until_paint()
│   └── web/
│       ├── __init__.py   # WEB_DIR, COMMON_CSS, UPDATE_JS, SETTINGS_JS
│       ├── common.css    # CSS shared by both GUIs (shared variables + shared components)
│       ├── settings.js   # shared by both GUIs: receiving and saving the stored theme and language (window.analyzeSettings)
│       └── update.js     # shared by both GUIs: settings button, settings dialog, update check flow
├── installer/
│   └── auto_update.iss   # Inno Setup include (waiting and relaunching for an installer started by auto-update)
└── tests/
    ├── conftest.py       # Ed25519 test signer, local HTTP server, executable files for find_executable(), faked name resolution and connecting
    ├── test_download.py
    ├── test_ed25519.py
    ├── test_ffmpeg.py
    ├── test_json_util.py
    ├── test_platform.py
    ├── test_settings.py
    ├── test_theme.py
    ├── test_ui_settings.py
    ├── test_update.py
    ├── test_update_manifest.py  # needs openssl (skipped without it)
    ├── test_ffmpeg_release.py   # the osxexperts.net page and the BtbN listing are fixtures, zips come from a local HTTP server
    ├── test_network.py   # also checks that no other module calls urllib's urlopen / urlretrieve / HTTPSHandler or http.client's HTTPSConnection directly
    └── test_web.py
```

## Public API

`__all__` is the single source. Only the following are public:

| Symbol | Module | Description |
|--------|--------|-------------|
| `IS_WINDOWS` | platform | `sys.platform == "win32"` |
| `IS_MAC` | platform | `sys.platform == "darwin"` |
| `IS_LINUX` | platform | `sys.platform == "linux"` |
| `IS_FROZEN` | platform | PyInstaller frozen build detection |
| `subprocess_kwargs()` | platform | per-OS subprocess argument dict (Windows: hidden console, macOS frozen: DYLD_* restored) |
| `find_executable()` | platform | absolute path of a program found in the absolute entries of PATH (Windows: `name.exe`, others: an executable `name`), or `None` |
| `SettingsStore` | settings | reading and writing settings kept in one JSON file (a broken file is read as the defaults with a warning, a write replaces the file from a temporary file) |
| `settings_dir()` | settings | per-product user settings folder (Windows: `%APPDATA%`, macOS: `~/Library/Application Support`, others: `$XDG_CONFIG_HOME` or `~/.config`) |
| `UiSettings` | ui_settings | reading and writing the theme (`theme`) and language (`lang`) kept in `SettingsStore` (`values()` / `update()`), the window's background color (`background_color()`), the body of `/common/settings.js` (`script()`) |
| `show_window_color_until_paint()` | ui_settings | macOS: shows the pywebview window's `background_color` until the page paints (removes WKWebView's white background) |
| `is_dark_mode()` | theme | OS dark mode detection (Win: registry, macOS: defaults, Linux: gsettings/kreadconfig5) |
| `ffmpeg_kwargs()` | ffmpeg | subprocess_kwargs() + LC_ALL=C (for ffmpeg/ffprobe) |
| `probe_info()` | ffmpeg | gets (channels, duration_sec) with ffprobe (started by the path `find_executable()` gives) |
| `download_audio()` | download | audio download with the yt-dlp Python API (ffmpeg and deno passed to yt-dlp by the paths `find_executable()` gives) |
| `sanitize_filename()` | download | file name sanitization (control characters + Windows reserved names) |
| `compute_middle()` | download | computes the start point and length of the middle extraction |
| `is_url()` | download | HTTP(S) URL check |
| `json_safe()` | json_util | recursive NaN/Infinity → None conversion |
| `UpdateConfig` | update | per-app auto-update identity (product name, repository, current version, public key, temporary directory prefix, mutex name) |
| `Updater` | update | `status()` / `check()` / `install(version)`. `install` returns a `Handoff` |
| `Handoff` | update | how the app ends after the update is applied (`exit_mode`: `"close"` / `"immediate"` / `None`) |
| `UpdateError` | update | a failure to check, download, verify or apply |
| `hold_instance_mutex()` | update | Windows: holds the named mutex the installer waits for |
| `COMMON_CSS` | web | path of the shared CSS that both GUIs load before `style.css` |
| `UPDATE_JS` | web | path of the settings dialog and update check UI that both GUIs serve as `/common/update.js` |
| `SETTINGS_JS` | web | path of the script that receives and saves the theme and language, which `UiSettings.script()` appends after the stored values |
| `__version__` | — | SemVer string |

## Usage

Placed at `vendor/py-analyze-common` as a git submodule. The consumer's `__init__.py` does `sys.path.insert(0, vendor/py-analyze-common/src)` and imports it. Not listed in pyproject.toml.

## Tests

```bash
python3 -m venv .venv
.venv/bin/pip install -e . pytest pytest-cov
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -q --cov --cov-report=term-missing  # with line and branch coverage of src/analyze_common ([tool.coverage.run] in pyproject.toml)
```

`tests/` reads `analyze_common` with a normal import, so `pip install -e .` (or `PYTHONPATH=src`) is needed. `test_update_manifest.py` skips when the `openssl` on PATH cannot create Ed25519 keys (the LibreSSL 3.3 that ships with macOS cannot; put Homebrew's `openssl@3` first on PATH). macOS-only tests (`hdiutil` / `renamex_np` / `ps`) skip on other OSes.

CI (`.github/workflows/ci.yml`) runs on PRs and on pushes to main: it installs `pip install -e . pytest pytest-cov` on Python 3.12, runs `python -m pytest -q --cov --cov-report=xml` and uploads `coverage.xml` to Codecov with `codecov/codecov-action`. The job `test` is a required check of main. The job's `id-token: write` lets the upload authenticate with GitHub's OIDC token (`use_oidc: true`), so the repository holds no Codecov token. The upload has `fail_ci_if_error: false`, so a failed upload does not fail `test`, and Codecov's statuses (`codecov/project`, `codecov/patch`) are not required checks of main.

## Design decisions

### subprocess_kwargs() returns a new dict every time

Restoring DYLD_* in a frozen build depends on a snapshot of the environment variables at that moment, so the result cannot be cached.

### Programs start by absolute path (find_executable)

On Windows, `subprocess` hands a bare program name to `CreateProcess`, which searches the directory of the executable, then the current directory, then the system directories, and `PATH` last ([CreateProcessW](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw)). yt-dlp's lookup of deno on Windows also checks the current directory before `PATH` (`yt_dlp/utils/_jsruntime.py` `_find_exe()`).

- `find_executable(name)` searches only the absolute entries of `PATH`, in order. On Windows it matches `name + ".exe"` only (the extension `CreateProcess` appends to a bare name; `.bat` / `.cmd` would run through `cmd.exe`); elsewhere the file must be executable
- `probe_info()` runs that path for ffprobe. `download_audio()` passes it to yt-dlp as `ffmpeg_location` (yt-dlp takes the ffprobe in the same folder) and as `js_runtimes={"deno": {"path": ...}}`
- ffprobe not found: `probe_info()` raises `FileNotFoundError` without starting a process. ffmpeg not found: `download_audio()` raises `FileNotFoundError` without calling yt-dlp. deno not found: `js_runtimes={}` (yt-dlp runs with no JavaScript runtime)

### Dark mode detection priority (Linux)

1. GNOME `color-scheme` (GNOME 42+)
2. GNOME `gtk-theme` (GNOME <42 fallback)
3. KDE `kreadconfig5` (True if the value contains "dark")
4. All of the above fail → `False`

subprocess runs with `LC_ALL=C`, which avoids substring match failures caused by locale-dependent translations ("Dunkel" etc.).

### sanitize_filename() adopts the spectrum version (the strict version)

Removes the control characters 0x00-0x1F explicitly. The loudness version did not include `\x00-\x1f`, but yt-dlp metadata can contain control characters, and this prevents `open()` from failing with `ValueError('embedded null byte')`.

### compute_middle() message format

Returns plain text without a prefix (`[info]` etc.). Each consumer controls the display format.

### Auto-update

The consumer puts `PUBLIC_KEY` and `UPDATE_CONFIG` in `src/<pkg>/update.py`, has `/update/status` / `/update/settings` / `/update/check` / `/update/install` on the GUI server, and `window.analyzeUpdate.init({appName, isBusy, setBusy, setStatus, showError})` in the frontend. The description of the behavior (the setting, when the check runs, how failures are handled) is held by the "Auto-update" section of the consumer's CLAUDE.md.

- The "Check at launch" setting: `Updater` reads and writes `update_check_at_launch` in `SettingsStore` (default `settings_dir(product)/settings.json`) (`launch_check()` / `set_launch_check()`, `launch_check` in `status()`). It is not kept in the webview's localStorage, because pywebview's private mode and the port changing on every launch keep it from surviving to the next launch
- Manifest: each Release's `latest.json` = `{"version", "platforms": {"windows-x86_64" | "darwin-aarch64": {"url", "signature"}}}`. Fetched from `https://github.com/{repo}/releases/latest/download/latest.json`
- Signature: Ed25519. The signed statement is `analyze-update-v1\n{product}\n{version}\n{platform}\n{sha256}\n` (`statement()`). It includes the version, the OS and the product name, so relabeling a version and reusing a file of another OS / another app fail verification. The private key is the consumer's secret `UPDATE_SIGNING_KEY` (an OpenSSL PEM). `update_manifest.py sign` verifies the signature it made with the consumer's public key, and exits 1 on a mismatch
- Verification is pure Python (`ed25519.py`), because the consumers' specs exclude `cryptography`. The HTTPS CA is certifi (imported inside the function, because creating the manifest in CI does not need it)
- Windows: launches the verified installer with `os.startfile(path, "open", INSTALLER_ARGS)` (UAC is raised by the installer; Inno Setup's loader is `asInvoker`), then `Handoff("close")`. UAC appears after the app has closed, so if it is refused, nothing is installed and the app stays closed. Only with `/UPDATE=1`, `installer/auto_update.iss` waits until the app's mutex disappears, and after installing launches the app with `runasoriginaluser`
- macOS: runs `hdiutil attach` on the DMG, copies the `.app` with `ditto` into a temporary directory on the same volume, checks the identifier, the version and the Team ID, then swaps with `renamex_np(RENAME_SWAP)` (two renames when that is unavailable, osascript's administrator privileges when permission is missing). After the swap it is `Handoff("immediate")`, and the consumer returns the response and then calls `os._exit(0)` (PyInstaller reopens the archive by path on every lazy import, so no import runs after the swap). The restart is done by a `/bin/sh` that waits for this process to end and then runs `open`. It does not swap while another process of the same executable is running
- `PYINSTALLER_RESET_ENVIRONMENT=1` is passed to the restart and to the installer, because the bootloader of PyInstaller 6.9 and later acts as the parent's worker when the inherited `_PYI_ARCHIVE_FILE` is its own
- The strings of `web/update.js` (en / ja) are held by update.js and follow `window.i18n.lang()` and `onChange`. They are not put in the dictionary of the consumer's i18n.js

### Theme and language settings

The consumer creates exactly one `SettingsStore` and passes it to both `Updater(config, store)` and `UiSettings(store)`, so both read and write the same file under the same lock. The GUI server returns `UiSettings.script()` for GET `/common/settings.js` with `Cache-Control: no-store`, and calls `UiSettings.update()` for POST `/settings` (`ValueError` is 400, `OSError` is 500). pywebview's `background_color` gets `UiSettings.background_color()`. The page loads `common/settings.js` in the `<head>` of `index.html` before `i18n.js`, starts drawing with `window.analyzeSettings.theme` / `.lang`, and saves with `window.analyzeSettings.save(name, value)` on every switch. The consumer owns how a failed save is shown.

- Keys: `theme` (`light` / `dark` / `auto`; `auto` when missing or for any other value) and `lang` (`en` / `ja`; `null` when missing or for any other value, and the page follows the OS language). `update()` accepts only one at a time
- `script()` prepends `window.analyzeSettingsStored = {...};` to `web/settings.js`. Only values that passed the read validation are included, so rewriting the settings file does not deliver arbitrary strings to the page
- `save()` waits for the previous save's response before sending the next one. The consumer's server (`ThreadingHTTPServer`) handles requests concurrently, so when they are sent back to back, a value chosen later can be written first and then be overwritten by the earlier value
- `BG_LIGHT` / `BG_DARK` mirror `--bg` in `web/common.css` (`:root` and `[data-theme="dark"]`), and `tests/test_ui_settings.py` checks that they match
- The consumer calls `show_window_color_until_paint(window)` right after `webview.create_window()`. pywebview (6.2.1) on macOS attaches WKWebView to the window when the first load finishes, and WKWebView draws a white background until its first paint. `background_color` applies only to the window, so `drawsBackground` of WKWebView is turned off in `events.before_show`, and the window's color shows until the page paints. Windows' WebView2 uses `background_color` as its own background (`DefaultBackgroundColor`), so nothing is done there. WKWebView is touched only on pywebview whose `before_show` runs on the main thread (5.4 and later; `Event(self, True)`). On pywebview without `before_show` (before 5.3) it returns without registering, and on pywebview whose handler runs on another thread (5.3) it changes nothing. In both cases, and when it cannot turn the background off, it writes to stderr and the window opens as is (the consumers' `pyproject.toml` also allow pywebview before 5.3)

### Fetching over HTTPS (network)

`ffmpeg_release._read()` and `update._open()` make their HTTPS connections through `network` (`urlopen()`, or `HTTPSHandler` in an opener of their own).

- `connect()` tries the host's addresses in the order `getaddrinfo` returns them, each with the fetch's timeout and with the address as `getaddrinfo` gives it (an IPv6 scope id included), as `socket.create_connection` does. When every address fails, it raises an `OSError` that names each address with its own error (`could not connect to HOST port PORT (ADDRESS: ERROR; ...)`); `socket.create_connection` reports the last address's error only. urllib hands it on as the `reason` of a `URLError`
- `HTTPSHandler` is `urllib.request.HTTPSHandler` whose connections connect with `connect()`; TLS still checks the certificate against the host name. Plain `http://` goes through urllib's own handler
- `tests/test_network.py` fails when another module of the package calls `urllib.request.urlopen` / `urlretrieve` / `HTTPSHandler` or `http.client.HTTPSConnection` directly

### Bundled ffmpeg pin (ffmpeg_release)

The consumer has `build_assets/ffmpeg.json` (`{"series", "macos_arm64": {"ffmpeg" | "ffprobe": {"url", "sha256"}}}`), and `build.py` calls `load_pin()` / `btbn_asset()` / `fetch_macos_binary()`. The description of how each OS bundles it is held by the "Bundled ffmpeg pin" section of the consumer's CLAUDE.md.

- The osxexperts.net page (`parse_osxexperts()`): for each "Download ffmpeg X.Y (Apple Silicon)" link, reads the "SHA256 checksum of ... file : <hex>" found before the next download link. Fails unless there is exactly one Apple Silicon build each of ffmpeg / ffprobe, with the same `MAJOR.MINOR`, and the link is a zip under `https://www.osxexperts.net/`. ffplay and the Intel builds are not read
- The SHA256 is the value of the binary inside, not of the zip (the same value the page lists)
- BtbN (`btbn_asset()`): `ffmpeg-n{series}-latest-win64-gpl-{series}.zip` in `releases/tags/latest`. Fails when it is absent (lgpl builds are not used)
- `detect` (CLI): only when the pin and the page differ, it checks the BtbN series, downloads both files, checks them against the page's SHA256, and writes the new pin to `--candidate`. Whether a patch release is needed (`bump`) is `true` when `__version__` equals the latest `vX.Y.Z` tag and either the pin changes this time or the current pin differs from the pin that tag released. The pin a tag released (`released_pin()`) is the pin in the pin file at the tag, or, when the tag has none, the pin of the first commit after the tag that added the file. When neither exists, the latter comparison is not made
- `release_sha` of `detect`: when `__version__` is `MAJOR.MINOR.PATCH` and there is no `v{version}` tag, the commit in HEAD's first-parent history that introduced that version (`pending_release()`). The consumer's `ffmpeg-watch.yml` uses it to resume from the state where the version bump was merged but no tag was created, by passing that commit to `tag-release.yml`. Empty otherwise
- Fetching (`_read()`: the page, the BtbN listing and the downloads) goes through `network.urlopen()` ([Fetching over HTTPS](#fetching-over-https-network))
- Importing `analyze_common` makes `__init__.py` load yt-dlp, so running the CLI needs the consumer's dependencies (`pip install -e .`)

### yt-dlp version pin

`pyproject.toml` has an exact-match pin `yt-dlp==<version>`. The `pyproject.toml` of the consumers (analyze-loudness / analyze-spectrum) have the same pin, and a manual version bump updates all three at the same time. A Dependabot update of the Python dependencies (in this repository the `uv` entry of `.github/dependabot.yml`, every day at 00:00 JST, for a version released at least three days before) is merged automatically here and in the consumers unless someone other than Dependabot pushed a commit to its PR (`.github/workflows/dependabot-auto-merge.yml`); each repository merges its own, so the three values may not match until all three have. What goes into a consumer's shipped build is the pin in the consumer's `pyproject.toml`; this `pyproject.toml` is not used by the consumers' builds. The procedure for checking and updating the pinned version is held by the "yt-dlp version pin" section of the consumer's CLAUDE.md.

## Compatibility policy

SemVer. Symbols outside `__all__` are internal. See README.md for details.
