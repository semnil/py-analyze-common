# py-analyze-common

analyze-loudness / analyze-spectrum で共有するユーティリティライブラリ。

## Project structure

```
py-analyze-common/
├── CLAUDE.md
├── README.md
├── CHANGELOG.md
├── pyproject.toml
├── src/analyze_common/
│   ├── __init__.py       # 公開 API (__all__), __version__
│   ├── platform.py       # IS_WINDOWS/IS_MAC/IS_LINUX/IS_FROZEN, subprocess_kwargs()
│   ├── theme.py          # is_dark_mode() — OS ネイティブダークモード検出
│   ├── ffmpeg.py         # ffmpeg_kwargs(), probe_info()
│   ├── download.py       # download_audio(), sanitize_filename(), compute_middle(), is_url()
│   └── json_util.py      # json_safe()
└── tests/
    ├── test_download.py
    ├── test_json_util.py
    ├── test_platform.py
    └── test_theme.py
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
| `is_dark_mode()` | theme | OS ダークモード検出 (Win: レジストリ, macOS: defaults, Linux: gsettings/kreadconfig5) |
| `ffmpeg_kwargs()` | ffmpeg | subprocess_kwargs() + LC_ALL=C (ffmpeg/ffprobe 用) |
| `probe_info()` | ffmpeg | ffprobe で (channels, duration_sec) を取得 |
| `download_audio()` | download | yt-dlp Python API で音声ダウンロード |
| `sanitize_filename()` | download | ファイル名安全化 (制御文字 + Windows 予約名) |
| `compute_middle()` | download | 中盤抽出の開始点・長さ計算 |
| `is_url()` | download | HTTP(S) URL 判定 |
| `json_safe()` | json_util | NaN/Infinity → None 再帰変換 |
| `__version__` | — | SemVer 文字列 |

## 利用方式

git submodule として `vendor/py-analyze-common` に配置。consumer 側の `__init__.py` で `sys.path.insert(0, vendor/py-analyze-common/src)` してインポート。pyproject.toml には記載しない。

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

## Compatibility policy

SemVer 準拠。`__all__` 外のシンボルは internal。詳細は README.md 参照。
