"""Pictures the game needs beyond the sprite sheets, drawn with Pillow and numpy only.

Nothing here touches the graphics card, so the self-test can build all of it without a window.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from art import pix, pixfont, sprites as S
from art.palette import rgba

TILE = 960   # Backdrop tile size. Every noise cell size below divides it, so the tiles repeat cleanly.


def light_twin(img: Image.Image) -> Image.Image | None:
    """Only the glowing pixels, already multiplied by their glow strength. None if nothing glows."""
    em = pix.emissive(img)
    lit = em.max(axis=2) > 0
    if not lit.any():
        return None
    out = np.zeros((img.height, img.width, 4), dtype=np.uint8)
    out[..., :3] = np.clip(em * 255 + 0.5, 0, 255).astype(np.uint8)
    out[..., 3] = lit * 255
    return Image.fromarray(out)


def silhouette(img: Image.Image, color=(255, 255, 255, 255)) -> Image.Image:
    a = np.array(img.convert("RGBA"))
    out = np.zeros_like(a)
    out[a[..., 3] > 0] = color
    return Image.fromarray(out)


def rock_image(size: int, variant: int, ore: bool) -> Image.Image:
    seed = 7000 + size * 10 + variant + (50 if ore else 0)
    return S.asteroid(size, seed, ore=max(1, size // 5) if ore else 0)

def glyph(ch: str) -> Image.Image:
    """One white character of the HUD font, trimmed like the font trims narrow characters."""
    cols = pixfont._columns(ch)
    img = Image.new("RGBA", (len(cols), 7), (0, 0, 0, 0))
    px = img.load()
    for y, row in enumerate(pixfont.GLYPHS[ch]):
        for i, x in enumerate(cols):
            if row[x] == "#":
                px[i, y] = (255, 255, 255, 255)
    return img


def crosshair() -> Image.Image:
    rows = [
        "....w....",
        "....h....",
        "....i....",
        ".........",
        "whi.d.ihw",
        ".........",
        "....i....",
        "....h....",
        "....w....",
    ]
    return pix.from_grid(rows, {"w": "ion_white", "h": "ion_hi", "i": "ion", "d": "ion_hi"})


def pointer() -> Image.Image:
    rows = [
        "k.......",
        "kk......",
        "kwk.....",
        "kwwk....",
        "kwwwk...",
        "kwwwwk..",
        "kwwwwwk.",
        "kwwwkkkk",
        "kwkwk...",
        "kk.kwk..",
        "k...kk..",
    ]
    return pix.from_grid(rows, {"k": "console_black", "w": "hud_text"})


def tile_noise(size: int, cell: int, seed: int) -> np.ndarray:
    """Smooth 0..1 noise that repeats every `size` pixels in both directions."""
    n = size // cell
    rng = np.random.default_rng(seed)
    grid = rng.random((n, n)).astype(np.float32)
    big = np.tile(grid, (3, 3))
    img = Image.fromarray((big * 255).astype(np.uint8)).resize((3 * size, 3 * size), Image.BICUBIC)
    return np.array(img)[size:2 * size, size:2 * size].astype(np.float32) / 255.0


def nebula_tile(seed: int = 7) -> Image.Image:
    s = TILE
    out = np.zeros((s, s, 4), dtype=np.uint8)
    out[:] = rgba("space")
    violet = tile_noise(s, 64, seed) * 0.65 + tile_noise(s, 24, seed + 1) * 0.35
    teal = tile_noise(s, 80, seed + 2) * 0.7 + tile_noise(s, 24, seed + 3) * 0.3
    vl = pix.dither_levels(np.clip((violet - 0.56) * 3.0, 0, 1), 3)
    tl = pix.dither_levels(np.clip((teal - 0.6) * 3.2, 0, 1), 3)
    out[tl == 1] = rgba("nebula_teal")
    out[tl == 2] = rgba("nebula_teal_hi")
    out[vl == 1] = rgba("nebula_violet")
    out[vl == 2] = rgba("nebula_violet_hi")
    rng = pix.seeded(seed)
    for _ in range(s * s // 260):
        out[rng.randrange(s), rng.randrange(s)] = rgba("star_dim")
    return Image.fromarray(out)


def star_tile(seed: int, mid: int, bright: int) -> Image.Image:
    s = TILE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    px = img.load()
    rng = pix.seeded(seed)
    for _ in range(mid):
        px[rng.randrange(s), rng.randrange(s)] = rgba("star_mid")
    for _ in range(bright):
        x, y = rng.randrange(s), rng.randrange(s)
        px[x, y] = rgba("star_bright")
        if rng.random() < 0.5:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                px[(x + dx) % s, (y + dy) % s] = rgba("star_mid")
    return img
