"""Build the Windows (or local) app folder and zip it: `python packaging/build.py`.

Makes dist/BitMiner/ (BitMiner.exe plus its libraries) and dist/BitMiner-LassoAndRing-<platform>.zip.
Needs PyInstaller: `pip install pyinstaller`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

NAME = "BitMiner"
ZIP_NAME = "BitMiner-LassoAndRing-{platform}.zip"


def make_icon(path: Path) -> None:
    """The ship sprite, scaled up in whole pixels for every icon size Windows asks for."""
    from PIL import Image

    from art import pix, sprites as S

    ship = S.player_ship(0.0)
    images = []
    for side in (16, 24, 32, 48, 64, 128, 256):
        k = max(1, side // ship.width)
        art = pix.scale(ship, k) if k > 1 else ship
        if art.width > side:
            art = ship.resize((side, side), Image.NEAREST)
        images.append(pix.pad(art, (side, side)))
    images[-1].save(path, format="ICO", sizes=[im.size for im in images], append_images=images[:-1])


def main() -> int:
    build = ROOT / "build"
    dist = ROOT / "dist"
    build.mkdir(exist_ok=True)
    icon = build / "BitMiner.ico"
    make_icon(icon)
    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", NAME, "--icon", str(icon),
        "--distpath", str(dist), "--workpath", str(build / "pyinstaller"), "--specpath", str(build),
        "--exclude-module", "tkinter", "--exclude-module", "pytest",
        "--add-data", f"{ROOT / 'bitminer' / 'data'}:bitminer/data",   # tuning and weapon numbers
        str(ROOT / "BitMiner.py"),
    ]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)

    app = dist / NAME
    shutil.copy(ROOT / "packaging" / "README.txt", app / "README.txt")
    platform = "windows" if sys.platform == "win32" else sys.platform
    archive = dist / ZIP_NAME.format(platform=platform)
    archive.unlink(missing_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(app.rglob("*")):
            z.write(f, Path(NAME) / f.relative_to(app))
    print(f"Built {archive} ({archive.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
