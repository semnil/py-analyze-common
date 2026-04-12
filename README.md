# py-desktop-app-common

analyze-spectrum / analyze-loudness などの pywebview ベースのデスクトップツールで共有するプラットフォーム抽象化レイヤー。

## Modules

- `platform.py` — OS 判定、subprocess kwargs、frozen build 検出
- `theme.py` — ダークモード検出 (Windows レジストリ / macOS `defaults` / Linux `gsettings`)
- `assets.py` — ffmpeg/ffprobe/yt-dlp の OS 別ダウンロード (URL + SHA256)

## Usage (as git submodule)

```
git submodule add https://github.com/semnil/py-desktop-app-common vendor/py-desktop-app-common
```

Consumer adds `vendor/py-desktop-app-common/src` to `sys.path` and imports from `desktop_app_common`.

## License

MIT
