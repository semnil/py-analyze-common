# Changelog

All notable changes to this project will be documented in this file.

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) に準ずる。
バージョニングは [Semantic Versioning](https://semver.org/lang/ja/) に従う。

## [Unreleased]

### Added
- Linux KDE 環境のダークモード検出 (`kreadconfig5 --group General --key ColorScheme`)。GNOME (`gsettings color-scheme` / `gtk-theme`) が未検出の場合にフォールバックとして試行する。

### Changed
- `theme.py` の `subprocess.run` 呼び出しを `LC_ALL=C` / `LANG=C` 環境で実行するよう変更。ロケール依存の翻訳 ("Dunkel" 等) で substring match "dark" が失敗する問題を回避。
- `_is_dark_mode_windows()` の例外 catch を `Exception` から `(OSError, FileNotFoundError, ImportError)` に絞り込み。予期せぬバグは伝播させて診断可能にする。

## [0.1.1]

### Added
- `subprocess_kwargs()` で macOS frozen ビルド時に PyInstaller が保存した `DYLD_*_ORIG` を復元するロジック。yt-dlp 等の onefile 子プロセスが Python.framework を誤ロードしないようにする。
- `theme.py`: Windows レジストリ / macOS `defaults` / Linux `gsettings` によるダークモード検出。

### Changed
- 初期リリースから `platform.py` の公開 API を安定化。
