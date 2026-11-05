"""Quick contact sheets for checking sprites while drawing them.

    python -m art.preview out.png [scale]
"""

from __future__ import annotations

import sys

from PIL import Image, ImageDraw

from . import pix, sprites
from .palette import rgba


def sheet(items: list[tuple[str, Image.Image]], k: int = 6, cols: int = 6, bg: str = "space") -> Image.Image:
    cell_w = max(i.width for _, i in items) * k + 24
    cell_h = max(i.height for _, i in items) * k + 40
    rows = (len(items) + cols - 1) // cols
    out = Image.new("RGBA", (cell_w * cols, cell_h * rows), rgba(bg))
    d = ImageDraw.Draw(out)
    for n, (name, img) in enumerate(items):
        cx, cy = (n % cols) * cell_w, (n // cols) * cell_h
        big = pix.scale(img, k)
        out.alpha_composite(big, (cx + (cell_w - big.width) // 2, cy + 8 + (cell_h - 40 - big.height) // 2))
        d.text((cx + 8, cy + cell_h - 24), name, fill=(200, 200, 220, 255))
    return out


def default_items() -> list[tuple[str, Image.Image]]:
    return [
        ("player", sprites.player_ship()),
        ("player+main", sprites.player_with_boosters(("main",))),
        ("player+right", sprites.player_with_boosters(("main", "right"), 1)),
        ("player 30deg", sprites.player_with_boosters(("main",), 0, 30)),
        ("sentry", sprites.sentry()),
        ("drill", sprites.drill()),
        ("infantry", sprites.infantry()),
        ("guard", sprites.guard()),
        ("guard charge", sprites.guard(charging=True)),
        ("rapid", sprites.rapid_assault()),
        ("tank", sprites.tank()),
        ("powerup", sprites.powerup("shield")),
    ]


if __name__ == "__main__":
    out = sys.argv[1]
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    sheet(default_items(), k).save(out)
    print("saved", out)
