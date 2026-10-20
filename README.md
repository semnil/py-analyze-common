# py-analyze-common

analyze-loudness / analyze-spectrum で共有するユーティリティライブラリ。
プラットフォーム抽象化、ffmpeg/ffprobe ラッパー、yt-dlp ダウンロード、JSON 安全化、アプリの自動更新を提供する。

## Modules

- `platform.py` — OS 判定、subprocess kwargs、frozen build 検出
- `theme.py` — ダークモード検出 (Windows レジストリ / macOS `defaults` / Linux `gsettings` + `kreadconfig5`)
- `ffmpeg.py` — `ffmpeg_kwargs()` (LC_ALL=C 付き subprocess kwargs)、`probe_info()` (ffprobe JSON パース)
- `download.py` — `download_audio()` (yt-dlp)、`sanitize_filename()`、`compute_middle()`、`is_url()`
- `json_util.py` — `json_safe()` (NaN/Infinity → None 変換)
- `update.py` — 自動更新のクライアント (`UpdateConfig`、`Updater`、`hold_instance_mutex()`)。GitHub の最新の Release の `latest.json` を確認し、インストーラーを取得して Ed25519 署名を検証し、Windows はインストーラー、macOS は `.app` の入れ替えで適用する
- `settings.py` — 製品ごとのユーザー設定ファイル (JSON) の読み書き (`SettingsStore`、`settings_dir()`)。自動更新の「起動時に確認」を置く
- `ed25519.py` — Ed25519 署名の検証 (RFC 8032、純 Python。検証のみ)
- `update_manifest.py` — CI で `latest.json` を作って署名する CLI (`python -m analyze_common.update_manifest sign | public-key`)。署名は `openssl pkeyutl -rawin`
- `web/common.css` — 両 GUI 共通の CSS 変数と部品のスタイル。パスは `COMMON_CSS`
- `web/update.js` — 両 GUI 共通の設定ボタン・設定ダイアログ・更新の確認の流れ。パスは `UPDATE_JS`
- `installer/auto_update.iss` — Inno Setup の include。自動更新で起動されたインストーラーがアプリの終了を待ち、インストール後にアプリを起動する

## Usage (as git submodule)

```
git submodule add https://github.com/semnil/py-analyze-common vendor/py-analyze-common
```

Consumer adds `vendor/py-analyze-common/src` to `sys.path` and imports from `analyze_common`.

## Platform Notes

- Linux ダークモード検出の優先順位:
  1. GNOME: `gsettings get org.gnome.desktop.interface color-scheme`
  2. GNOME: `gsettings get org.gnome.desktop.interface gtk-theme`
  3. KDE: `kreadconfig5 --group General --key ColorScheme` (値に "dark" を含めば True)
- 上記いずれも利用できない環境 (XFCE / Cinnamon 等で kreadconfig5 未インストール) では `False` フォールバック。
- `subprocess_kwargs()` の戻り値は呼び出しごとに新規 `dict` を生成する。呼び出し側でキャッシュ・再利用しないこと (frozen ビルドの DYLD_* 復元は環境変数の現時点スナップショットに依存する)。

## Compatibility Policy

- 公開 API は `analyze_common/__init__.py` の `__all__` が唯一のソース。`__all__` に無いシンボルは internal 扱いで予告なく変更・削除される可能性がある。
- Semantic Versioning に準ずる:
  - `MINOR` (0.x.y → 0.x+1.0) では後方互換を保つ。新規 API 追加のみ。
  - `MAJOR` (0.x → 1.0, 1.x → 2.x) で破壊的変更を許可。破壊的変更を含むコミットはメッセージ本文に内容を書く。
- 変更履歴は `git log` を参照。

## License

MIT
