# py-desktop-app-common

analyze-loudness / analyze-spectrum の pywebview ベースデスクトップツールで共有するプラットフォーム抽象化レイヤー。

## Project structure

```
py-desktop-app-common/
├── CLAUDE.md
├── README.md
├── CHANGELOG.md
├── pyproject.toml
├── src/desktop_app_common/
│   ├── __init__.py       # 公開 API (__all__), __version__
│   ├── platform.py       # IS_WINDOWS/IS_MAC/IS_LINUX/IS_FROZEN, subprocess_kwargs()
│   └── theme.py          # is_dark_mode() — OS ネイティブダークモード検出
└── tests/
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
| `__version__` | — | SemVer 文字列 |

## 利用方式

git submodule として `vendor/py-desktop-app-common` に配置。consumer 側の `__init__.py` で `sys.path.insert(0, vendor/py-desktop-app-common/src)` してインポート。pyproject.toml には記載しない。

## Design decisions

### subprocess_kwargs() の戻り値は毎回新規 dict

frozen ビルドの DYLD_* 復元は環境変数の現時点スナップショットに依存するため、キャッシュ不可。

### ダークモード検出の優先順位 (Linux)

1. GNOME `color-scheme` (GNOME 42+)
2. GNOME `gtk-theme` (GNOME <42 フォールバック)
3. KDE `kreadconfig5` (値に "dark" を含めば True)
4. 上記すべて失敗 → `False`

subprocess は `LC_ALL=C` で実行し、ロケール依存の翻訳 ("Dunkel" 等) による substring match 失敗を回避。

## Compatibility policy

SemVer 準拠。`__all__` 外のシンボルは internal。詳細は README.md 参照。
