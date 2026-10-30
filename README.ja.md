# py-analyze-common

> For the English version, see [README.md](README.md).

analyze-loudness / analyze-spectrum で共有するユーティリティライブラリ。
プラットフォーム抽象化、ffmpeg/ffprobe ラッパー、yt-dlp ダウンロード、JSON 安全化、アプリの自動更新、テーマと言語の設定の保存を提供する。

## Modules

- `platform.py` — OS 判定、subprocess kwargs、frozen build 検出、`find_executable()` (PATH 上のプログラムの絶対パス)
- `theme.py` — ダークモード検出 (Windows レジストリ / macOS `defaults` / Linux `gsettings` + `kreadconfig5`)
- `ffmpeg.py` — `ffmpeg_kwargs()` (LC_ALL=C 付き subprocess kwargs)、`probe_info()` (ffprobe JSON パース)
- `download.py` — `download_audio()` (yt-dlp)、`sanitize_filename()`、`compute_middle()`、`is_url()`
- `json_util.py` — `json_safe()` (NaN/Infinity → None 変換)
- `update.py` — 自動更新のクライアント (`UpdateConfig`、`Updater`、`hold_instance_mutex()`)。GitHub の最新の Release の `latest.json` を確認し、インストーラーを取得して Ed25519 署名を検証し、Windows はインストーラー、macOS は `.app` の入れ替えで適用する
- `settings.py` — 製品ごとのユーザー設定ファイル (JSON) の読み書き (`SettingsStore`、`settings_dir()`)。自動更新の「起動時に確認」と、テーマ・言語を置く
- `ui_settings.py` — テーマと言語の設定 (`UiSettings`)。値の検証、pywebview のウィンドウの背景色、ページへ保存値を渡すスクリプト。`show_window_color_until_paint()` は macOS で、ページが描かれるまでウィンドウの背景色を見せる
- `ed25519.py` — Ed25519 署名の検証 (RFC 8032、純 Python。検証のみ)
- `update_manifest.py` — CI で `latest.json` を作って署名する CLI (`python -m analyze_common.update_manifest sign | public-key`)。署名は `openssl pkeyutl -rawin`
- `ffmpeg_release.py` — 同梱する ffmpeg / ffprobe の固定値 (consumer の `build_assets/ffmpeg.json`) の読み書き、osxexperts.net (macOS) と BtbN/FFmpeg-Builds (Windows) からの取得と SHA256 の照合、新しいビルドの検出 (`python -m analyze_common.ffmpeg_release detect`)
- `network.py` — 接続に失敗したとき、試した全てのアドレスとそれぞれのエラーを示す HTTPS の取得 (`urlopen()`、`HTTPSHandler`)。`ffmpeg_release.py` と `update.py` はこれを通して取得する
- `web/common.css` — 両 GUI 共通の CSS 変数と部品のスタイル。パスは `COMMON_CSS`
- `web/settings.js` — 両 GUI 共通の、保存したテーマと言語の受け取りと保存 (`window.analyzeSettings`)。パスは `SETTINGS_JS`
- `web/update.js` — 両 GUI 共通の設定ボタン・設定ダイアログ・更新の確認の流れ。パスは `UPDATE_JS`
- `installer/auto_update.iss` — Inno Setup の include。自動更新で起動されたインストーラーがアプリの終了を待ち、インストール後にアプリを起動する

## Usage (as git submodule)

```
git submodule add https://github.com/semnil/py-analyze-common vendor/py-analyze-common
```

consumer は `vendor/py-analyze-common/src` を `sys.path` に追加し、`analyze_common` からインポートする。

## Platform Notes

- Linux ダークモード検出の優先順位:
  1. GNOME: `gsettings get org.gnome.desktop.interface color-scheme`
  2. GNOME: `gsettings get org.gnome.desktop.interface gtk-theme`
  3. KDE: `kreadconfig5 --group General --key ColorScheme` (値に "dark" を含めば True)
- 上記いずれも利用できない環境 (XFCE / Cinnamon 等で kreadconfig5 未インストール) では `False` フォールバック。
- `subprocess_kwargs()` の戻り値は呼び出しごとに新規 `dict` を生成する。呼び出し側でキャッシュ・再利用しないこと (frozen ビルドの DYLD_* 復元は環境変数の現時点スナップショットに依存する)。
- `probe_info()` は ffprobe を、`download_audio()` は yt-dlp に渡す ffmpeg (と同じフォルダの ffprobe) と deno を、`find_executable()` が返す絶対パスで起動する。`find_executable()` は `PATH` のうち絶対パスの項目だけを探すので、現在のフォルダを探すのは `PATH` がそのフォルダを絶対パスで挙げているときだけになる。Windows ではパスを付けないプログラム名が `PATH` より先に現在のフォルダから探される ([CreateProcessW](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw))。`PATH` に ffprobe が無いと `probe_info()` が、ffmpeg が無いと `download_audio()` が `FileNotFoundError` を送出する。deno が無いときは yt-dlp を JavaScript の実行環境なしで動かす。

## Compatibility Policy

- 公開 API は `analyze_common/__init__.py` の `__all__` が唯一のソース。`__all__` に無いシンボルは internal 扱いで予告なく変更・削除される可能性がある。
- Semantic Versioning に準ずる:
  - `MINOR` (0.x.y → 0.x+1.0) では後方互換を保つ。新規 API 追加のみ。
  - `MAJOR` (0.x → 1.0, 1.x → 2.x) で破壊的変更を許可。破壊的変更を含むコミットはメッセージ本文に内容を書く。
- 変更履歴は `git log` を参照。

## License

MIT
