"""Generate icon.ico, icon.png rasters, and icon.iconset/ from icon_draft.svg in a consumer's build_assets/.

    PYTHONPATH=vendor/py-analyze-common/src python -m analyze_common.icons build_assets

Output:
  build_assets/icon.ico              — Windows ico (16-256)
  build_assets/icon.png              — 1024x1024 master PNG
  build_assets/icon.iconset/         — macOS iconset dir (input for iconutil)

On macOS (CI), `iconutil -c icns build_assets/icon.iconset` produces icon.icns.
Rendering needs resvg-py and Pillow (pip install resvg-py pillow).
"""

import sys
from pathlib import Path

# (filename, size) for macOS iconset naming convention
ICONSET_SIZES = [
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
]

ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def render_png(svg: Path, size: int, dest: Path) -> None:
    import resvg_py
    data = resvg_py.svg_to_bytes(svg_path=str(svg), width=size, height=size)
    dest.write_bytes(bytes(data))


def build_ico(assets: Path) -> None:
    from PIL import Image
    # Render each size independently from the SVG (not scaled from a single raster)
    # so low-res sizes use sharper source geometry instead of resampled pixels.
    biggest = max(ICO_SIZES)
    tmp_big = assets / f"_tmp_{biggest}.png"
    render_png(assets / "icon_draft.svg", biggest, tmp_big)
    base = Image.open(tmp_big)
    base.load()
    base.save(assets / "icon.ico", format="ICO", sizes=[(s, s) for s in ICO_SIZES])
    base.close()
    tmp_big.unlink(missing_ok=True)
    print(f"  -> {assets / 'icon.ico'}")


def build_iconset(assets: Path) -> None:
    iconset = assets / "icon.iconset"
    iconset.mkdir(exist_ok=True)
    for name, size in ICONSET_SIZES:
        render_png(assets / "icon_draft.svg", size, iconset / name)
    print(f"  -> {iconset}/ ({len(ICONSET_SIZES)} files)")


def build_master(assets: Path) -> None:
    render_png(assets / "icon_draft.svg", 1024, assets / "icon.png")
    print(f"  -> {assets / 'icon.png'}")


def main(argv=None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        raise SystemExit("usage: python -m analyze_common.icons <build_assets dir>")
    assets = Path(args[0]).resolve()
    svg = assets / "icon_draft.svg"
    if not svg.exists():
        raise SystemExit(f"Source SVG not found: {svg}")
    print("Rendering icons from", svg.name)
    build_master(assets)
    build_ico(assets)
    build_iconset(assets)
    print("Done.")


if __name__ == "__main__":
    main()
