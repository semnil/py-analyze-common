import sys
import types

import pytest

from analyze_common import icons


def test_renders_every_iconset_size_from_the_given_folder(tmp_path, monkeypatch):
    (tmp_path / "icon_draft.svg").write_text("<svg/>", encoding="utf-8")
    rendered = []
    monkeypatch.setattr(icons, "render_png", lambda svg, size, dest: rendered.append((svg, size, dest)))
    monkeypatch.setattr(icons, "build_ico", lambda assets: rendered.append(("ico", assets)))
    icons.main([str(tmp_path)])
    svg = tmp_path / "icon_draft.svg"
    iconset = [("icon_16x16.png", 16), ("icon_16x16@2x.png", 32), ("icon_32x32.png", 32), ("icon_32x32@2x.png", 64),
               ("icon_128x128.png", 128), ("icon_128x128@2x.png", 256), ("icon_256x256.png", 256),
               ("icon_256x256@2x.png", 512), ("icon_512x512.png", 512), ("icon_512x512@2x.png", 1024)]
    assert rendered[0] == (svg, 1024, tmp_path / "icon.png")
    assert rendered[1] == ("ico", tmp_path)
    assert rendered[2:] == [(svg, size, tmp_path / "icon.iconset" / name) for name, size in iconset]


def test_the_ico_holds_every_windows_size(tmp_path, monkeypatch):
    saved = []

    class FakeImage:
        def load(self):
            pass

        def save(self, dest, format, sizes):
            saved.append((dest, format, sizes))

        def close(self):
            pass

    rendered = []
    monkeypatch.setitem(sys.modules, "PIL", types.SimpleNamespace(Image=types.SimpleNamespace(open=lambda path: FakeImage())))
    monkeypatch.setattr(icons, "render_png", lambda svg, size, dest: rendered.append(size))
    icons.build_ico(tmp_path)
    assert rendered == [256]
    assert saved == [(tmp_path / "icon.ico", "ICO", [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])]


def test_stops_without_the_svg(tmp_path):
    with pytest.raises(SystemExit, match="Source SVG not found"):
        icons.main([str(tmp_path)])


def test_stops_without_exactly_one_folder():
    with pytest.raises(SystemExit, match="usage"):
        icons.main([])
