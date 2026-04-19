# py-desktop-app-common

analyze-spectrum / analyze-loudness などの pywebview ベースのデスクトップツールで共有するプラットフォーム抽象化レイヤー。

## Modules

- `platform.py` — OS 判定、subprocess kwargs、frozen build 検出
- `theme.py` — ダークモード検出 (Windows レジストリ / macOS `defaults` / Linux `gsettings` + `kreadconfig5`)

## Usage (as git submodule)

```
git submodule add https://github.com/semnil/py-desktop-app-common vendor/py-desktop-app-common
```

Consumer adds `vendor/py-desktop-app-common/src` to `sys.path` and imports from `desktop_app_common`.

## Platform Notes

- Linux ダークモード検出の優先順位:
  1. GNOME: `gsettings get org.gnome.desktop.interface color-scheme`
  2. GNOME: `gsettings get org.gnome.desktop.interface gtk-theme`
  3. KDE: `kreadconfig5 --group General --key ColorScheme` (値に "dark" を含めば True)
- 上記いずれも利用できない環境 (XFCE / Cinnamon 等で kreadconfig5 未インストール) では `False` フォールバック。
- `subprocess_kwargs()` の戻り値は呼び出しごとに新規 `dict` を生成する。呼び出し側でキャッシュ・再利用しないこと (frozen ビルドの DYLD_* 復元は環境変数の現時点スナップショットに依存する)。

## Compatibility Policy

- 公開 API は `desktop_app_common/__init__.py` の `__all__` が唯一のソース。`__all__` に無いシンボルは internal 扱いで予告なく変更・削除される可能性がある。
- Semantic Versioning に準ずる:
  - `MINOR` (0.x.y → 0.x+1.0) では後方互換を保つ。新規 API 追加のみ。
  - `MAJOR` (0.x → 1.0, 1.x → 2.x) で破壊的変更を許可。変更内容は CHANGELOG に明記する。
- 変更履歴は [CHANGELOG.md](CHANGELOG.md) を参照。

## License

MIT
