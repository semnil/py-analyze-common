# py-analyze-common

analyze-loudness / analyze-spectrum で共有するユーティリティライブラリ。

## Project structure

```
py-analyze-common/
├── CLAUDE.md
├── README.md
├── pyproject.toml
├── src/analyze_common/
│   ├── __init__.py       # 公開 API (__all__), __version__
│   ├── platform.py       # IS_WINDOWS/IS_MAC/IS_LINUX/IS_FROZEN, subprocess_kwargs()
│   ├── theme.py          # is_dark_mode() — OS ネイティブダークモード検出
│   ├── ffmpeg.py         # ffmpeg_kwargs(), probe_info()
│   ├── download.py       # download_audio(), sanitize_filename(), compute_middle(), is_url()
│   ├── json_util.py      # json_safe()
│   ├── update.py         # 自動更新のクライアント (UpdateConfig, Updater, hold_instance_mutex)
│   ├── ed25519.py        # Ed25519 署名の検証 (RFC 8032、純 Python)
│   ├── update_manifest.py # CI 用: latest.json の作成と署名 (python -m analyze_common.update_manifest)
│   ├── settings.py       # SettingsStore, settings_dir() — OS ごとのユーザー設定ファイル (JSON)
│   ├── ui_settings.py    # UiSettings — テーマと言語の設定 (値の検証、ウィンドウの背景色、ページへ渡すスクリプト)
│   └── web/
│       ├── __init__.py   # WEB_DIR, COMMON_CSS, UPDATE_JS, SETTINGS_JS
│       ├── common.css    # 両 GUI 共通の CSS (共通変数 + 共通部品)
│       ├── settings.js   # 両 GUI 共通: 保存したテーマと言語の受け取りと保存 (window.analyzeSettings)
│       └── update.js     # 両 GUI 共通の設定ボタン・設定ダイアログ・更新の確認の流れ
├── installer/
│   └── auto_update.iss   # Inno Setup の include (自動更新で起動されたインストーラーの待ちと再起動)
└── tests/
    ├── conftest.py       # Ed25519 のテスト用署名器、ローカル HTTP サーバー
    ├── test_download.py
    ├── test_ed25519.py
    ├── test_json_util.py
    ├── test_platform.py
    ├── test_settings.py
    ├── test_theme.py
    ├── test_ui_settings.py
    ├── test_update.py
    ├── test_update_manifest.py  # openssl が要る (無ければ skip)
    └── test_web.py
```

## 公開 API

`__all__` が唯一のソース。以下のみが公開:

| Symbol | Module | Description |
|--------|--------|-------------|
| `IS_WINDOWS` | platform | `sys.platform == "win32"` |
| `IS_MAC` | platform | `sys.platform == "darwin"` |
| `IS_LINUX` | platform | `sys.platform == "linux"` |
| `IS_FROZEN` | platform | PyInstaller frozen ビルド判定 |
| `subprocess_kwargs()` | platform | OS 別 subprocess 引数 dict (Windows: コンソール非表示, macOS frozen: DYLD_* 復元) |
| `SettingsStore` | settings | 1 つの JSON ファイルに置く設定の読み書き (壊れたファイルは警告して既定値、書き込みは一時ファイルからの置き換え) |
| `settings_dir()` | settings | 製品ごとのユーザー設定フォルダ (Windows: `%APPDATA%`、macOS: `~/Library/Application Support`、他: `$XDG_CONFIG_HOME` か `~/.config`) |
| `UiSettings` | ui_settings | `SettingsStore` に置くテーマ (`theme`) と言語 (`lang`) の読み書き (`values()` / `update()`)、ウィンドウの背景色 (`background_color()`)、`/common/settings.js` の本体 (`script()`) |
| `is_dark_mode()` | theme | OS ダークモード検出 (Win: レジストリ, macOS: defaults, Linux: gsettings/kreadconfig5) |
| `ffmpeg_kwargs()` | ffmpeg | subprocess_kwargs() + LC_ALL=C (ffmpeg/ffprobe 用) |
| `probe_info()` | ffmpeg | ffprobe で (channels, duration_sec) を取得 |
| `download_audio()` | download | yt-dlp Python API で音声ダウンロード |
| `sanitize_filename()` | download | ファイル名安全化 (制御文字 + Windows 予約名) |
| `compute_middle()` | download | 中盤抽出の開始点・長さ計算 |
| `is_url()` | download | HTTP(S) URL 判定 |
| `json_safe()` | json_util | NaN/Infinity → None 再帰変換 |
| `UpdateConfig` | update | アプリごとの自動更新の識別 (製品名・リポジトリ・現在の版・公開鍵・一時ディレクトリの接頭辞・mutex 名) |
| `Updater` | update | `status()` / `check()` / `install(version)`。`install` は `Handoff` を返す |
| `Handoff` | update | 適用後のアプリの終わり方 (`exit_mode`: `"close"` / `"immediate"` / `None`) |
| `UpdateError` | update | 確認・取得・検証・適用の失敗 |
| `hold_instance_mutex()` | update | Windows: インストーラーが待つ名前付き mutex を保持する |
| `COMMON_CSS` | web | 両 GUI が `style.css` より先に読み込む共通 CSS のパス |
| `UPDATE_JS` | web | 両 GUI が `/common/update.js` で配信する、設定ダイアログと更新の確認の UI のパス |
| `SETTINGS_JS` | web | `UiSettings.script()` が保存値の後ろに付ける、テーマと言語の受け取りと保存のスクリプトのパス |
| `__version__` | — | SemVer 文字列 |

## 利用方式

git submodule として `vendor/py-analyze-common` に配置。consumer 側の `__init__.py` で `sys.path.insert(0, vendor/py-analyze-common/src)` してインポート。pyproject.toml には記載しない。

## テスト

```bash
python3 -m venv .venv
.venv/bin/pip install -e . pytest
.venv/bin/python -m pytest -q
```

`tests/` は `analyze_common` を通常の import で読むため、`pip install -e .` (または `PYTHONPATH=src`) が要る。`test_update_manifest.py` は PATH の `openssl` が Ed25519 の鍵を作れないとき skip する (macOS 標準の LibreSSL 3.3 は作れない。Homebrew の `openssl@3` を PATH の先に置く)。macOS 専用のテスト (`hdiutil` / `renamex_np` / `ps`) は他の OS では skip する。

## Design decisions

### subprocess_kwargs() の戻り値は毎回新規 dict

frozen ビルドの DYLD_* 復元は環境変数の現時点スナップショットに依存するため、キャッシュ不可。

### ダークモード検出の優先順位 (Linux)

1. GNOME `color-scheme` (GNOME 42+)
2. GNOME `gtk-theme` (GNOME <42 フォールバック)
3. KDE `kreadconfig5` (値に "dark" を含めば True)
4. 上記すべて失敗 → `False`

subprocess は `LC_ALL=C` で実行し、ロケール依存の翻訳 ("Dunkel" 等) による substring match 失敗を回避。

### sanitize_filename() は spectrum 版 (厳密版) を採用

制御文字 0x00-0x1F を明示的に除去。loudness 版は `\x00-\x1f` を含まなかったが、yt-dlp のメタデータに制御文字が含まれるケースがあり、`open()` が `ValueError('embedded null byte')` で失敗する問題を防止。

### compute_middle() のメッセージ形式

プレフィックス (`[info]` 等) なしのプレーンテキストを返す。表示形式は各 consumer 側で制御する。

### 自動更新

consumer は `src/<pkg>/update.py` に `PUBLIC_KEY` と `UPDATE_CONFIG` を置き、GUI のサーバーに `/update/status` / `/update/settings` / `/update/check` / `/update/install` を、フロントエンドに `window.analyzeUpdate.init({appName, isBusy, setBusy, setStatus, showError})` を持つ。振る舞いの説明 (設定・確認のタイミング・失敗の扱い) は consumer の CLAUDE.md「自動更新」節が持つ。

- 「起動時に確認」の設定: `Updater` が `SettingsStore` (既定は `settings_dir(product)/settings.json`) の `update_check_at_launch` に読み書きする (`launch_check()` / `set_launch_check()`、`status()` の `launch_check`)。webview の localStorage は pywebview の private mode と起動ごとのポートの変化で次の起動に残らないため、ここに置かない
- マニフェスト: 各 Release の `latest.json` = `{"version", "platforms": {"windows-x86_64" | "darwin-aarch64": {"url", "signature"}}}`。取得元は `https://github.com/{repo}/releases/latest/download/latest.json`
- 署名: Ed25519。対象は `analyze-update-v1\n{product}\n{version}\n{platform}\n{sha256}\n` (`statement()`)。版・OS・製品名を含むので、版の付け替えと別 OS / 別アプリのファイルの流用は検証で落ちる。秘密鍵は consumer の secret `UPDATE_SIGNING_KEY` (OpenSSL の PEM)。`update_manifest.py sign` は作った署名を consumer の公開鍵で検証し、食い違えば exit 1
- 検証は純 Python (`ed25519.py`)。consumer の spec は `cryptography` を除いているため。HTTPS の CA は certifi (関数の中で import する。CI のマニフェスト作成では要らないため)
- Windows: 検証済みのインストーラーを `os.startfile(path, "open", INSTALLER_ARGS)` で起動し (UAC はインストーラーが出す。Inno Setup の loader は `asInvoker`)、`Handoff("close")`。UAC はアプリが閉じた後に出るので、拒否するとインストールされず、アプリは閉じたままになる。`installer/auto_update.iss` が `/UPDATE=1` のときだけアプリの mutex が消えるまで待ち、インストール後に `runasoriginaluser` でアプリを起動する
- macOS: DMG を `hdiutil attach` し、`.app` を同じボリュームの一時ディレクトリへ `ditto` し、識別子・版・Team ID を確かめてから `renamex_np(RENAME_SWAP)` で入れ替える (使えなければ 2 回の rename、権限が無ければ osascript の管理者権限)。入れ替えの後は `Handoff("immediate")` で、consumer は応答を返してから `os._exit(0)` する (PyInstaller は遅延 import のたびにアーカイブをパスで開き直すので、入れ替えた後に import を走らせない)。再起動はこのプロセスの終了を待って `open` する `/bin/sh` が行う。同じ実行ファイルの別プロセスが動いているときは入れ替えない
- 再起動とインストーラーには `PYINSTALLER_RESET_ENVIRONMENT=1` を渡す。PyInstaller 6.9 以降の bootloader は、継承した `_PYI_ARCHIVE_FILE` が自分と同じなら親の worker として振る舞うため
- `web/update.js` の文言 (en / ja) は update.js が持ち、`window.i18n.lang()` と `onChange` に従う。consumer の i18n.js の辞書には入れない

### テーマと言語の設定

consumer は `SettingsStore` を 1 つだけ作って `Updater(config, store)` と `UiSettings(store)` の両方に渡し、同じファイルを同じロックで読み書きする。GUI のサーバーは GET `/common/settings.js` に `UiSettings.script()` を `Cache-Control: no-store` で返し、POST `/settings` で `UiSettings.update()` を呼ぶ (`ValueError` は 400、`OSError` は 500)。pywebview の `background_color` には `UiSettings.background_color()` を渡す。ページは `index.html` の `<head>` で `common/settings.js` を `i18n.js` より先に読み、`window.analyzeSettings.theme` / `.lang` で描き始め、切り替えのたびに `window.analyzeSettings.save(name, value)` で保存する。保存の失敗の表示は consumer が持つ。

- キー: `theme` (`light` / `dark` / `auto`。無いときと他の値は `auto`) と `lang` (`en` / `ja`。無いときと他の値は `null` で、ページは OS の言語に従う)。`update()` は 1 回に 1 つだけ受け付ける
- `script()` は `window.analyzeSettingsStored = {...};` を `web/settings.js` の前に付ける。載せる値は読み取りの検証を通ったものだけなので、設定ファイルを書き換えても任意の文字列はページに届かない
- `save()` は前の保存の応答を待ってから次を送る。consumer のサーバー (`ThreadingHTTPServer`) は要求を並行に処理するため、続けて送ると後に選んだ値が先に書かれ、前の値で上書きされうる
- `BG_LIGHT` / `BG_DARK` は `web/common.css` の `--bg` (`:root` と `[data-theme="dark"]`) のミラーで、`tests/test_ui_settings.py` が一致を確かめる

### yt-dlp のバージョン固定

`pyproject.toml` は `yt-dlp==<version>` の完全一致ピンを持つ。このピンは consumer (analyze-loudness / analyze-spectrum) の `pyproject.toml` とのミラーで、必ず同時に更新する。更新手順は consumer の CLAUDE.md「yt-dlp のバージョン固定」節が持つ。

## Compatibility policy

SemVer 準拠。`__all__` 外のシンボルは internal。詳細は README.md 参照。
