# py-analyze-common

A utility library shared by analyze-loudness / analyze-spectrum. What the two apps have in common as desktop apps is in `docs/architecture.md`, and their security measures and accepted risks in `docs/security-model.md`.

## Documentation languages

- **Override of the global CLAUDE.md's 「ドキュメント」 language rule**: this file is written entirely in English, `LICENSE` is English only, and the README and the documents under `docs/` are maintained in both English and Japanese (`README.md` and `README.ja.md`, `docs/auto-update.md` and `docs/auto-update.ja.md`, `docs/development.md` and `docs/development.ja.md`, `docs/architecture.md` and `docs/architecture.ja.md`, `docs/security-model.md` and `docs/security-model.ja.md`, and the decision records `docs/decisions/<subject>.md` and `docs/decisions/<subject>.ja.md`, kept section for section, with the Japanese file under the same headings as the English one)

## Project structure

The map of every file (workflows, documents, modules of `src/analyze_common/`, `web/`, `installer/`, tests) with what each holds is in `docs/architecture.md`, section "Project structure". Read it before adding, moving or looking for a file.

## Public API

`__all__` in `src/analyze_common/__init__.py` is the single source; only the names in it are public. Before adding, removing or changing a public name, read the table of every public name, its module and what it does in `docs/architecture.md`, section "Public API".

## Usage

Placed at `vendor/py-analyze-common` as a git submodule. The consumer's `__init__.py` does `sys.path.insert(0, vendor/py-analyze-common/src)` and imports it. Not listed in pyproject.toml.

## Tests

```bash
python3 -m venv .venv
.venv/bin/pip install -e . pytest pytest-cov
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -q --cov --cov-report=term-missing  # with line and branch coverage of src/analyze_common, without testing/, which the consumers' tests run ([tool.coverage.run] in pyproject.toml)
```

`tests/` reads `analyze_common` with a normal import, so `pip install -e .` (or `PYTHONPATH=src`) is needed. `test_update_manifest.py` skips when the `openssl` on PATH cannot create Ed25519 keys (the LibreSSL 3.3 that ships with macOS cannot; put Homebrew's `openssl@3` first on PATH). macOS-only tests (`hdiutil` / `renamex_np` / `ps`) skip on other OSes, and the tests of a real `terminate:` in `test_window.py` and `test_programs.py` also skip without `pyobjc-framework-Cocoa`, which CI installs on macOS.

The procedures the consumers share with this library (testing a consumer from a worktree, test runs for each commit of a pull request, probing the real app on macOS) are in `docs/development.md` (Japanese: `docs/development.ja.md`).

CI (`.github/workflows/ci.yml`) runs on PRs and on pushes to main. The checks `test` (Ubuntu), `test-macos` and `codecov/project` are required checks of main; `test-tempdirs-windows` and `codecov/patch` are not. Before changing `ci.yml` or `.github/codecov.yml`, or re-running a failed `coverage` job, read `docs/development.md`, section "CI of this library".

## Design decisions

The sections below say how the library works today. What was chosen, why, what was rejected and what happened on the way are recorded in `docs/decisions/`.

How the modules below work is in `docs/architecture.md`, under "How the modules work" (Japanese: `docs/architecture.ja.md`). Before changing one of them, read its section there:

- `subprocess_kwargs()`: "subprocess_kwargs() returns a new dict every time"
- `programs.py`, `run_ffmpeg()` and the programs yt-dlp starts: "ffmpeg ends with the app (run_ffmpeg)"
- `is_dark_mode()` on Linux: "Dark mode detection priority (Linux)"
- `sanitize_filename()`: "sanitize_filename() adopts the spectrum version (the strict version)"
- `compute_middle()`: "compute_middle()"
- `server.py` (`GuiHandler`) and `window.py`: "GUI server (server)"
- `web/` (the order a page loads the shared scripts in, what each function of `ui.js` does, what `common.css` styles): "Shared frontend scripts (web)"
- `network.py`: "Fetching over HTTPS (network)". Every HTTPS connection of the package goes through `network`; `tests/test_network.py` fails on a direct call of urllib or `http.client`
- `testing/`: "Tests the consumers share (testing)"

### Programs start by absolute path (find_executable)

On Windows, `subprocess` hands a bare program name to `CreateProcess`, which searches the directory of the executable, then the current directory, then the system directories, and `PATH` last ([CreateProcessW](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw)). yt-dlp's lookup of deno on Windows also checks the current directory before `PATH` (`yt_dlp/utils/_jsruntime.py` `_find_exe()`).

- `find_executable(name)` searches only the absolute entries of `PATH`, in order. On Windows it matches `name + ".exe"` only (the extension `CreateProcess` appends to a bare name; `.bat` / `.cmd` would run through `cmd.exe`); elsewhere the file must be executable
- `probe_info()` runs that path for ffprobe. `download_audio()` passes it to yt-dlp as `ffmpeg_location` (yt-dlp takes the ffprobe in the same folder) and as `js_runtimes={"deno": {"path": ...}}`
- ffprobe not found: `probe_info()` raises `FileNotFoundError` without starting a process. ffmpeg not found: `download_audio()` raises `FileNotFoundError` without calling yt-dlp. deno not found: `js_runtimes={}` (yt-dlp runs with no JavaScript runtime)

### Temp folders a killed process left behind (tempdirs)

A process that is killed leaves its temp folders. The consumer's GUI removes them when it ends, with `sweep_orphan_tempdirs(prefix, lock, keep)` in an atexit function, where `keep` holds its own folders. The consumer's GUI holds an `InstanceLock(prefix)` while it runs, and its CLI holds one while its work folder exists.

- While another instance runs the sweep removes nothing; without one it removes only `prefix*` folders that have not changed for an hour
- How the lock works, when a lock file counts as running and what the sweep does on a file system without locks are in `docs/architecture.md`, under the same heading. Read it before changing `tempdirs.py`

### Auto-update

How an update runs, what the user sees, what is verified, how each OS applies it and the signing key are in `docs/auto-update.md` (Japanese: `docs/auto-update.ja.md`). The consumers' documents point there. The decisions about the settings dialog's focus and the result of the real-device checks are in `docs/decisions/auto-update.md`.

The consumer puts `PUBLIC_KEY` and `UPDATE_CONFIG` in `src/<pkg>/update.py`, gets `/update/status` / `/update/settings` / `/update/check` / `/update/install` on the GUI server from `GuiHandler`, and `window.analyzeUpdate.init({appName, isBusy, setBusy, setStatus, showError})` in the frontend. Its `main()` holds `hold_instance_mutex(UPDATE_CONFIG.mutex_name)`, and its `exit_for_update(exit_mode)` ends the app for the `Handoff`.

- `launch_check()` / `set_launch_check()` read and write the "Check at launch" setting, and `status()` returns it as `launch_check`
- The strings of `web/update.js` (en / ja) are held by update.js and follow `window.i18n.lang()` and `onChange`. They are not put in the dictionary of the consumer's i18n.js

### Window icon

PyInstaller's `EXE(icon=...)` is only the icon of the EXE file itself (shown in Explorer). The pywebview window icon (title bar and taskbar) needs an explicit `webview.start(icon=...)` (moved from `create_window` to `start` in pywebview 6.x). The consumer bundles `build_assets/icon.ico` through PyInstaller's `datas` and resolves it through `_ICON_PATH`.

The `icon=` argument is passed only on Windows (`sys.platform == "win32"`). On macOS the Dock/app icon comes from the `.app` bundle (`CFBundleIconFile` = `icon.icns`); passing `icon=` there makes pywebview's Cocoa backend call `NSApplication.setApplicationIconImage_`, which overrides the bundle icon with the raw `icon.ico` bitmap. That bitmap carries no icon-grid inset, so on macOS 26 the Dock renders it edge-to-edge (oversized) instead of at the system-masked size the bundle icon gets.

The Windows taskbar groups processes by AppUserModelID. When it is not set, the Python runtime's default ID is used and the icon embedded in the EXE does not show on the taskbar. The consumer's `main()` sets its own ID with `set_app_user_model_id()`.

### Theme and language settings

The consumer creates exactly one `SettingsStore` and passes it to both `Updater(config, store)` and `UiSettings(store)`, so both read and write the same file under the same lock. The GUI server returns `UiSettings.script()` for GET `/common/settings.js` with `Cache-Control: no-store`, and calls `UiSettings.update()` for POST `/settings` (`ValueError` is 400, `OSError` is 500). pywebview's `background_color` gets `UiSettings.background_color()`. The page loads `common/settings.js` in the `<head>` of `index.html` before `common/i18n.js` and its own `i18n.js`, starts drawing with `window.analyzeSettings.theme` / `.lang`, and saves with `window.analyzeSettings.save(name, value)` on every switch. The consumer owns how a failed save is shown.

- Keys: `theme` (`light` / `dark` / `auto`; `auto` when missing or for any other value) and `lang` (`en` / `ja`; `null` when missing or for any other value, and the page follows the OS language). `update()` accepts only one at a time
- `script()` prepends `window.analyzeSettingsStored = {...};` to `web/settings.js`. Only values that passed the read validation are included, so rewriting the settings file does not deliver arbitrary strings to the page
- `save()` waits for the previous save's response before sending the next one. The consumer's server (`ThreadingHTTPServer`) handles requests concurrently, so when they are sent back to back, a value chosen later can be written first and then be overwritten by the earlier value
- `BG_LIGHT` / `BG_DARK` mirror `--bg` in `web/common.css` (`:root` and `[data-theme="dark"]`), and `tests/test_ui_settings.py` checks that they match
- The consumer calls `show_window_color_until_paint(window)` right after `webview.create_window()`. pywebview (6.2.1) on macOS attaches WKWebView to the window when the first load finishes, and WKWebView draws a white background until its first paint. `background_color` applies only to the window, so `drawsBackground` of WKWebView is turned off in `events.before_show`, and the window's color shows until the page paints. Windows' WebView2 uses `background_color` as its own background (`DefaultBackgroundColor`), so nothing is done there. WKWebView is touched only on pywebview whose `before_show` runs on the main thread (5.4 and later; `Event(self, True)`). On pywebview without `before_show` (before 5.3) it returns without registering, and on pywebview whose handler runs on another thread (5.3) it changes nothing. In both cases, and when it cannot turn the background off, it writes to stderr and the window opens as is (the consumers' `pyproject.toml` also allow pywebview before 5.3)

### Contrast criteria of the GUIs

The UI of both GUIs meets all of the following, in what is added later as well:

- Body text and button labels: WCAG AA, 4.5:1 or more
- Dim text (`--text-secondary` / `--text-muted`): APCA Lc 60 or more as well
- An accent button whose white label on a mid-tone face falls below 4.5:1 gets a light face with a dark label instead. In the dark theme hover makes a face lighter, not darker: darker lowers the dark label's contrast, or sinks the face into the background
- Disabled buttons are outside WCAG's scope. Icon glyphs such as the remove mark are non-text content, 3:1
- Pass or fail is decided by the computed WCAG ratio and the APCA value (0.0.98G), not by eye

The before and after images of a pull request that changes the look are drawn from a harness that puts `common.css` and the consumer's `style.css` into one page, rendered in headless Chrome. The before image uses the `common.css` of the submodule commit before the change and the after image the one after it: `common.css` defines `--danger`, `--danger-fg` and `--error`, so their difference shows only between the two versions of the submodule.

### Building a consumer (build)

The consumer's `build.py` puts `vendor/py-analyze-common/src` on `sys.path`, makes `App(root, package, display_name, uplot_version)` and calls `main(App)`; the command line (`--installer` / `--skip-download` / `--skip-build` / `--update-checksums` / `--ffmpeg-only`) is the same for both consumers, and their workflows call `python build.py`.

- `App` derives every per-app name from the package and the display name: the spec and the PyInstaller COLLECT directory (`analyze-loudness`), the `.app` and the DMG volume (`Loudness Analyzer`), the DMG file (`Loudness-Analyzer.dmg`)
- `_read_version()` / `_read_mutex_name()` read `__version__` and `UPDATE_CONFIG`'s `mutex_name` from `src/<package>/`; `_build_inno()` passes them to Inno Setup as `/DMyAppVersion=` / `/DMyAppMutex=`
- The bundled ffmpeg is handled by `ffmpeg_release` ([Bundled ffmpeg pin](#bundled-ffmpeg-pin-ffmpeg_release)); uPlot is checked against the consumer's `build_assets/checksums.json`; deno and the Windows ffmpeg are not pinned
- `check_prerequisites()` stops the build without PyInstaller, without certifi (PyInstaller only warns when it is missing) or without the binaries in `build_assets/bin`
- macOS is Apple Silicon (arm64) only (since v1.3.0 of the consumers; Intel Mac support ended with v1.2.0). ffmpeg / ffprobe are osxexperts.net's arm64 native builds. evermeet.cx (x86_64) is not used because (a) an Intel Mach-O in the bundle makes macOS 26 show the warning that support for apps for Intel processors is ending, and (b) connections from the GitHub Actions macos runner time out. To check a built bundle, ``find <app> -type f | while read f; do file "$f" | grep x86_64; done`` prints nothing

### Bundled ffmpeg pin (ffmpeg_release)

The consumer has `build_assets/ffmpeg.json` (`{"series", "macos_arm64": {"ffmpeg" | "ffprobe": {"url", "sha256"}}}`): the series of ffmpeg / ffprobe bundled on both OSes (`series`, e.g. `8.1`), and the URL and SHA256 of the macOS build. `build.py` (`analyze_common.build`, which the consumer's `build.py` runs) calls `load_pin()` / `btbn_asset()` / `fetch_macos_binary()`.

- macOS: `build.py` fetches the osxexperts.net zip and checks the binaries in it against the pinned SHA256 (a mismatch stops the build)
- Windows: the build of the same series in `latest` of BtbN/FFmpeg-Builds. Its contents change daily, so the SHA256 is not pinned. When the series disappears from `latest`, the build stops
- Updates: the consumer's `.github/workflows/ffmpeg-watch.yml` does this daily and carries it through to a patch release ([Patch release for an ffmpeg update](#patch-release-for-an-ffmpeg-update)). The osxexperts.net URL is not derived from the version (`ffmpeg81arm.zip` / `ffmpeg9arm.zip`), so the pin is taken from the page's links. To do it by hand, the following command, run in the consumer, only when the page has a different build, confirms that BtbN has the same series and that both files match the page's SHA256, then writes the new pin to `--candidate`. When `pin_update=true`, copy its contents to `build_assets/ffmpeg.json`

  ```bash
  PYTHONPATH=vendor/py-analyze-common/src .venv/bin/python -m analyze_common.ffmpeg_release detect \
    --pin build_assets/ffmpeg.json --version-file src/<package>/__init__.py --candidate <tmpdir>/ffmpeg.json
  ```

- Verification: the consumer's `tests/test_ffmpeg_binary.py` runs the ffmpeg / ffprobe on PATH through the app's own code; its section "Bundled ffmpeg pin" says what it compares. Given the directory of the bundled binaries in `EXPECT_FFMPEG_DIR`, it confirms the ffmpeg / ffprobe there are found first, with `find_executable()`, and fails instead of skipping when they are not. The release build (`.github/workflows/release.yaml`) runs this test on the copies inside the distributables (on Windows `dist/<app>/_internal/bin` collected by PyInstaller, on macOS `Contents/Frameworks/bin` of the `.app` after signing), and on failure it does not proceed to uploading the artifacts and creating the Draft Release. `analyze_common.testing.release_workflow` checks the position of that step and the directory it passes against the spec and `installer.iss`
- Importing `analyze_common` makes `__init__.py` load yt-dlp, so running the CLI needs the consumer's dependencies (`pip install -e .`)
- What `parse_osxexperts()` reads from the page, which SHA256 the pin holds, the BtbN asset name, and `detect`'s outputs (`bump`, `release_sha`) and exit statuses are in `docs/architecture.md`, under the same heading. Read it before changing `ffmpeg_release.py` or the steps of `ffmpeg-watch.yml` that read `detect`

### yt-dlp version pin

`pyproject.toml` has an exact-match pin `yt-dlp==<version>`. The `pyproject.toml` of the consumers (analyze-loudness / analyze-spectrum) have the same pin, and a manual version bump updates all three at the same time. A Dependabot update of the Python dependencies (the `uv` entry of each repository's `.github/dependabot.yml`, every day at 00:00 JST, for a version released at least three days before) is merged automatically here and in the consumers at any semver level once its required checks pass, unless someone other than Dependabot pushed a commit to its PR (`.github/workflows/dependabot-auto-merge.yml`); each repository merges its own, so the three values may not match until all three have. Dependabot moves yt-dlp and `yt-dlp-ejs` (the challenge solver scripts yt-dlp reads) in one pull request in the consumers (the `yt-dlp` group), and their `tests/test_yt_dlp_ejs.py` fails when the two disagree. In the consumers the checks pass only when the update also keeps `requirements/release.txt` in step with `pyproject.toml` ([Pinned release dependencies](#pinned-release-dependencies)). What goes into a consumer's shipped build is the pin in the consumer's `pyproject.toml`; this `pyproject.toml` is not used by the consumers' builds (the submodule is read through `sys.path` injection).

Why pin: the shipped app has yt-dlp baked into the PYZ by PyInstaller, so it cannot be updated after installation. Leaving it unpinned makes the version depend on the resolution at build time, and the version inside a shipped app cannot be identified afterwards.

Check the pinned version before opening a consumer's version bump PR ([Release procedure](#release-procedure)). A pin changed by a Dependabot auto-merge reached master without this check:

1. In a `.venv` with the version pinned in the consumer's `pyproject.toml`, confirm a **full-length download**. `--test` (fetches only the first 10 KiB) cannot detect a 403:
   `.venv/bin/python -m yt_dlp -f bestaudio -o "<tmpdir>/%(id)s.%(ext)s" "<URL>"`
   Confirm with three kinds: a normal video, a live archive and a Short
2. If it fails, install a candidate version with `pip install -U yt-dlp`, run the same check, and write the version that passes into the three `pyproject.toml` files. Commit py-analyze-common first, then update the submodule pointer. In the consumers, regenerate `requirements/*.txt` in the same commit as the `pyproject.toml` change ([Pinned release dependencies](#pinned-release-dependencies))

- The check runs in a local `.venv`, not in CI: from GitHub's hosted runners a full-length download stops at yt-dlp's `Sign in to confirm you're not a bot` for a version and a URL that download in full from a local machine
- One 403 on one video is not yet a broken version: retry that video, and download another normal video, before concluding
- Whether a build installed the pinned version shows in its CI job log as `Collecting yt-dlp==<version>`
- Write the pin in the form PyPI lists the version in (`2026.8.19`); the module's own `__version__` is zero-padded (`2026.08.19`)

## Changes that span this library and the consumers

A change that needs both this library and a consumer (analyze-loudness / analyze-spectrum) goes in this order:

1. Check it locally, with this library's working branch laid over the consumer's submodule ("Testing a consumer from a worktree" in `docs/development.md`)
2. Open this library's pull request on its own; it is reviewed and merged before anything is opened in a consumer
3. Dependabot's submodule update (`gitsubmodule`) opens in each consumer and is merged by `.github/workflows/dependabot-auto-merge.yml`; wait for it
4. From the consumer's `master` after that merge, open a pull request that holds only the consumer's change and does not move the submodule pointer

- No pull request moves the submodule pointer by hand, unless one is asked for at that time
- A consumer's pull request opened first would point at a commit of this library that is not merged yet. A change here reaches both consumers, so it is reviewed on its own, and the pointer is left to Dependabot and its auto-merge
- The submodule update reaches a consumer's `master` before the consumer's own change does. Before opening this library's pull request, also run each consumer's whole test suite on its `master` with this library's whole branch as `vendor/py-analyze-common`. A check on the consumer's working branch does not see that state: a `const` in `web/ui.js` under a name a consumer's `main.js` still declares makes that whole script a `SyntaxError` with the submodule update alone (the case is in semnil/py-analyze-common#55)
- Before a consumer's pull request is opened, the files laid over its submodule are put back, so the pointer is the one `master` has
- When work goes on in more than one of the repositories at once, the session that needs a change in this library makes it, tells the session working in the other consumer which shared files and which of that consumer's files it will touch, and passes the new API on once this library's pull request exists. Each session changes its own consumer
- GitHub deletes a pull request's head branch when it is merged, in this repository and in both consumers; after `git fetch --prune` no remote branch of a merged pull request is left

## Releasing a consumer

Each consumer's AGENTS.md names only its own files. `master` below is the consumer's default branch.

The required checks of `master`, and of this repository's `main`, do not require a pull request's branch to be up to date, so a pull request whose head is older than `master` can be merged. What it makes together with the commits merged in between is then tested for the first time by the CI run of the push to `master`.

### Release procedure

Before opening the version bump PR, check the pinned yt-dlp version with a full-length download ([yt-dlp version pin](#yt-dlp-version-pin)).

1. Open a PR that raises `__version__` in `src/<package>/__init__.py` (a version bump contains no other change)
2. After the merge, when the CI run of the push to master succeeds, `.github/workflows/tag-release.yml` detects the change of `__version__`, puts a `vX.Y.Z` tag on the merge commit, and starts `.github/workflows/release.yaml` with `workflow_dispatch` on that tag
3. `release.yaml` builds the Windows installer and the macOS DMG and creates the Release (`draft: true`) together with the signed `latest.json` (`docs/auto-update.md`). Before uploading the artifacts, the build runs the ffmpeg / ffprobe inside the distributables through `tests/test_ffmpeg_binary.py` ("Verification" in [Bundled ffmpeg pin](#bundled-ffmpeg-pin-ffmpeg_release))
4. A person publishes the Release. The published Release becomes `releases/latest`, and the update check of installed apps reads its `latest.json` (a prerelease does not become `latest`, so it does not show up)

The merge of the version bump PR is the starting point of a release. `tag-release.yml` does nothing on a push that does not change `__version__`, and does not move a tag of the same name that already exists on another commit. `tag-release.yml`'s `workflow_dispatch` handles the commit of the input `sha`, and tags it only when it is on master and CI succeeded on that commit or on a parent commit with the same tree (the head of a PR merged with the tip of master included). `release.yaml` also builds and releases on a tag push and on a `workflow_dispatch` on a tag (a `workflow_dispatch` on a branch only builds).

### Pinned release dependencies

Dependabot updates `pyobjc-core` and `pyobjc-framework-*` together in the `pyobjc` group of the consumer's `.github/dependabot.yml`.

The release jobs install nothing that is resolved at build time:

- Python packages: `requirements/release.txt` (the dependencies of `pyproject.toml` and its `gui` and `dev` extras), installed with `--require-hashes --no-deps --no-build-isolation` after `requirements/release-build.txt` (the pip that installs it, and the build backends of its source distributions and of the project). The `sign-manifest` job installs only `requirements/sign-manifest.txt` (yt-dlp, which analyze_common imports) as a wheel
- Build tools: Inno Setup (Windows) and create-dmg (macOS) are downloaded from their GitHub releases and checked against the SHA256 in `release.yaml` (`INNOSETUP_SHA256`, `CREATE_DMG_SHA256`)
- Not pinned: deno and the Windows ffmpeg / ffprobe, which `build.py` downloads ([Bundled ffmpeg pin](#bundled-ffmpeg-pin-ffmpeg_release))

`requirements/*.txt` are generated by uv from `pyproject.toml` and `requirements/*.in` (uv is in the `dev` extra of `pyproject.toml`). Run the following from the consumer's root after changing the dependencies of `pyproject.toml` (the yt-dlp pin included); add `--upgrade` to the first command to take newer versions:

```bash
uv pip compile pyproject.toml --extra gui --extra dev --universal --python-version 3.12 --generate-hashes -o requirements/release.txt
uv pip compile requirements/release-build.in -c requirements/release.txt --universal --python-version 3.12 --generate-hashes -o requirements/release-build.txt
uv pip compile requirements/sign-manifest.in -c requirements/release.txt --universal --python-version 3.12 --generate-hashes -o requirements/sign-manifest.txt
```

`--python-version` is the `python-version` of `release.yaml`. The consumer's `tests/test_release_workflow.py` fails when `requirements/release.txt` does not satisfy `pyproject.toml`, when a file was generated with other options, or when uv finds no resolution for the command in a file's header with that file's own pins as constraints (a pin that breaks the requirement of another package in the file) or finds one with a package the file does not pin, or pins under another environment marker (the release jobs install with `--no-deps`, so it would be missing on that platform), or without one the file pins, so a branch that changes `pyproject.toml` without regenerating these files does not pass CI, whoever opened it.

### Patch release for an ffmpeg update

The consumer's `.github/workflows/ffmpeg-watch.yml` does the following daily (and on `workflow_dispatch`), with no human step until the Draft Release is created. The bot merges the PRs without review.

The jobs run in this order: detect (compares the pin with the osxexperts.net page and makes a new pin), smoke (`tests/test_ffmpeg_binary.py` on the fetched binaries, on macOS and Windows), land (opens the pin PR and the bump-only PR, and has GitHub merge each by auto-merge once its runs succeed); then a person publishes the Release (step 4 of the [Release procedure](#release-procedure)). Before changing `ffmpeg-watch.yml` or acting on a failed run, read `docs/development.md`, section "Patch release for an ffmpeg update": what each job does, why these PRs are not opened with GITHUB_TOKEN, when land stops and turns the auto-merge off and how the next run resumes.

- Prerequisite: a GitHub App installed on the consumer's repository with the repository permissions Contents (read and write) and Pull requests (read and write), its client ID in the repository variable `FFMPEG_WATCH_APP_CLIENT_ID`, and its private key (the contents of the `.pem`) in the repository secret `FFMPEG_WATCH_APP_PRIVATE_KEY`. The token land creates carries only those two permissions. Without the variable or the secret, land fails at its first step
- When land fails because an open PR whose head is `ffmpeg-watch/` remains from an earlier run, close or merge that PR, then run again
- When detect exits 3 (no address of a host accepted the connection, [Bundled ffmpeg pin](#bundled-ffmpeg-pin-ffmpeg_release)), the detect job passes with a warning and the job `retry` dispatches `ffmpeg-watch.yml` on master with the input `detect_attempt` one higher, which runs detect on another runner; when attempt 3 exits 3, detect fails the run. A runner that cannot connect to www.osxexperts.net stays unable to for minutes while other runners connect

## Compatibility policy

SemVer. Symbols outside `__all__` are internal. See README.md for details.
