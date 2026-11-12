# Security model of the analyze apps

> 日本語版は [security-model.ja.md](security-model.ja.md) を参照してください。

The entry points analyze-loudness and analyze-spectrum share, the measures both apps take and where each is implemented, and the risks that are accepted with their reasons. `gui.py` and `cli.py` below are each app's `src/<package>/gui.py` and `src/<package>/cli.py`; `analyze_common/...` is this library. How the apps are put together is in [architecture.md](architecture.md).

## Entry points

| Entry point | Reached through | What is checked |
|---|---|---|
| Command-line arguments | The local shell | argparse with a validator per argument type |
| GUI HTTP server | `127.0.0.1` only | The Host header, the Content-Type, the URL or path, the parameters, the JSON body |
| Frontend | pywebview | Static files; nothing is rendered on the server |
| File dialogs | The operating system's own dialogs | The user picks the file (pywebview's `SAVE_DIALOG` / `OPEN_DIALOG`) |
| Update check and download | HTTPS to github.com, outbound | An Ed25519 signature over the product name, the version, the OS and the SHA-256; URLs under the repository's releases only; redirects that stay on https; limits on size and time ([auto-update.md](auto-update.md), "What is verified") |

## Measures

| ID | Area | Measure | Where |
|---|---|---|---|
| CM-01 | Network | The server binds to `127.0.0.1` on a port the operating system picks | `gui.py` (`_HTTPServer(("127.0.0.1", 0), AnalyzeHandler)`) |
| CM-02 | Network | A request whose Host header is not `127.0.0.1` or `localhost` is refused (`_check_host()`), which stops a page that resolves another name to the loopback address | `analyze_common/server.py` (`do_GET`), the start of `do_POST` in `gui.py` |
| CM-03 | Injection | Subprocesses get their arguments as a list, with no shell | `analyze_common/ffmpeg.py`, analyze-loudness's `analysis.py`, analyze-spectrum's `pcm.py` |
| CM-04 | Cross-site scripting | Text reaches the page through `textContent`; no user string goes into `innerHTML` | Each `main.js`, `analyze_common/web/` |
| CM-05 | Input validation | A URL has to start with `http://` or `https://` (`is_url()`) | `analyze_common/download.py`, `gui.py` |
| CM-06 | Input validation | A number is checked with `isinstance(..., bool)` first and `math.isfinite()` after it | `gui.py` |
| CM-07 | Input validation | A body that cannot be read as JSON gives `None`, and the caller answers 400 | `analyze_common/server.py` (`_read_json_body()`) |
| CM-08 | Files | Saving, and loading a JSON, go through a native dialog only | `/save` and `/load` in `gui.py`, `/save-image` in `analyze_common/server.py` |
| CM-09 | Files | `sanitize_filename()` replaces `[\\/:*?"<>|\x00-\x1f]` and avoids the names Windows reserves | `analyze_common/download.py` |
| CM-10 | Temp files | A work folder is a `TemporaryDirectory` in a `with` block; the cache and upload folders are made with `mkdtemp()` and removed by an `atexit` function | `gui.py`, `cli.py` |
| CM-11 | Temp files | At exit, temp folders a killed process left are removed only when they have not changed for an hour and no other instance runs; the app's own cache and upload folders are left out | `analyze_common/tempdirs.py` (`sweep_orphan_tempdirs()`), `gui.py` |
| CM-12 | JSON | `json.dumps(allow_nan=False)`, with `json_safe()` replacing NaN and Infinity | `analyze_common/server.py` (`_json_response()`, `_send_event()`), `analyze_common/json_util.py` |
| CM-13 | JSON | A loaded JSON that holds NaN or Infinity is answered through the same `_json_response()`, which falls back to `json_safe()` | `analyze_common/server.py` |
| CM-14 | HTTP | JSON answers carry `Content-Length`; an NDJSON stream is closed with `Connection: close` | `analyze_common/server.py`, `gui.py` |
| CM-15 | HTTP | `do_POST` catches what a handler raises, answers 500 with a JSON body and writes the traceback to stderr | `gui.py` |
| CM-16 | Binaries | SHA256 checks: uPlot against `build_assets/checksums.json`, the macOS ffmpeg / ffprobe against `build_assets/ffmpeg.json` | `analyze_common/build.py`, `analyze_common/ffmpeg_release.py` |
| CM-17 | Subprocess | A frozen Windows build starts programs with `STARTF_USESHOWWINDOW`, so no console window appears | `analyze_common/platform.py` (`subprocess_kwargs()`) |
| CM-18 | Subprocess | ffmpeg and ffprobe run with `LC_ALL=C` and `LANG=C`, so their output is parsed in one language | `analyze_common/ffmpeg.py` (`ffmpeg_kwargs()`) |
| CM-19 | Subprocess | Of a failed tool's stderr, the last 200 characters are shown. One path shows more: when analyze-loudness finds no loudness data in ffmpeg's output, its error carries the last 30 lines of that output | `gui.py`, `analyze_common/ffmpeg.py`; the 30 lines: analyze-loudness's `analysis.py` |
| CM-20 | Threads | A `ThreadingHTTPServer`, with the shared state under `threading.Lock` | `analyze_common/server.py` (`GuiServer`), `gui.py` |
| CM-21 | File size | `/load` refuses a file by its size before reading it (`_MAX_LOAD_BYTES`, a value per app) | `gui.py` |
| CM-22 | Auto-update | A downloaded installer is applied only after its Ed25519 signature verifies against the public key built into the app | `analyze_common/update.py`, each app's `update.py` and `release.yaml` |

## Accepted risks

| ID | Risk | Why it is accepted |
|---|---|---|
| CA-01 | Other processes on the same host | The local server has no authentication. The random port and the Host and Content-Type checks (CM-01, CM-02, and `_check_content_type()`, which a page of another origin cannot pass without a preflight the server does not answer) keep web pages out. A process on the same host that finds the port can still call what the page calls: run an analysis, or change the "Check at launch" setting |
| CA-02 | Internal details in error messages | A message can hold a local path or the end of a tool's output (CM-19). It is sent to the page on `127.0.0.1` only |
| CA-03 | Work that goes on after Cancel | Cancel ends the request on the page; the server notices at its next event, and a program it started runs until then. The work folder is a `TemporaryDirectory` and is removed. What a killed process leaves is removed at a later exit under the conditions of CM-11 |
| CA-04 | File operations of `/save` and `/load` | They go through a native dialog on the local machine, so the user has to act |

## Data and network

- The theme, the language and "Check at launch" are kept in the user's settings file (`settings.json`). The result JSON and the images a user saves stay where they were saved (CM-08). When temp files go away is in CM-10 and CM-11
- There are no authentication tokens and no cookies: the local endpoints have no authentication, only the Host and Content-Type checks
- Nothing listens on an external network interface
- The only outbound connection the app makes by itself is the update check at launch (`latest.json` on github.com), which the setting turns off
- The licenses of the bundled software are in `THIRD_PARTY_LICENSES.txt`, which the installer carries

## Using the list in an audit

A new audit starts by confirming that every measure in the table above is still implemented where the table says.
