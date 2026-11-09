"""Pictures the game needs beyond the sprite sheets, drawn with Pillow and numpy only.

Nothing here touches the graphics card, so the self-test can build all of it without a window.
"""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
from PIL import Image

from art import items as I, pix, pixfont, sprites as S
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
    return S.asteroid(size, rock_seed(size, variant, ore), ore=max(1, size // 5) if ore else 0)

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


# ---------------------------------------------------------------- drilled asteroids

MAX_CRACK_SITES = 2

@lru_cache(maxsize=64)
def _rock(size: int, variant: int, ore: bool) -> Image.Image:
    return rock_image(size, variant, ore)


def rock_seed(size: int, variant: int, ore: bool) -> int:
    return 7000 + size * 10 + variant + (50 if ore else 0)


def rim_distance(size: int, variant: int, ore: bool, heading: float) -> float:
    """How far a rock's picture reaches from its centre in a direction (0 = up, clockwise), to the
    middle of its outermost pixel. A drill stands on that spot."""
    img = _rock(size, variant, ore)
    x, y = I.rim_point(img, heading)
    c = (img.width - 1) / 2
    return math.hypot(x - c, y - c)


def worn_rock(size: int, variant: int, ore: bool, stage: int, sites: tuple[float, ...], seed: int) -> Image.Image:
    """A drilled asteroid at crack stage 0 to 3: its gold flecks fade and cracks spread from where
    its drills stand (`sites`, headings) as the ore runs out."""
    if not ore:
        rock = _rock(size, variant, ore).copy()
    else:
        rock = I.drained_rock(size, rock_seed(size, variant, ore), max(1, size // 5), stage)
    if stage <= 0:
        return rock
    plain = _rock(size, variant, ore)
    # Cracks start from the first two drills set on it; more than that and the rock turns to a web.
    points = [I.rim_point(plain, a) for a in sites[:MAX_CRACK_SITES]] or [I.rim_point(plain, 0.0)]
    cracks = I.crack_points(plain, points, seed)
    rock.alpha_composite(I.crack_overlay(plain, cracks, stage))
    return rock


def crumble_frames(size: int, variant: int, ore: bool, stage: int, sites: tuple[float, ...], seed: int,
                   frames: int) -> list[Image.Image]:
    """A worked-out asteroid breaking up and crumbling to dust."""
    rock = worn_rock(size, variant, ore, stage, sites, seed)
    return I.shatter(rock, frames, max(4, size // 10), seed=seed)


# ---------------------------------------------------------------- the laser charge-up

CHARGE_CANVAS = 104       # the charge-up is drawn round the ship's centre, pointing up
CHARGE_STEPS = 40         # pictures over the whole charge
CANCEL_STEPS = 6


class _Canvas:
    """Just enough of `pix.Scene` for `draw_laser_charge`: a clear picture and a light layer."""

    def __init__(self, size: int) -> None:
        self.w = self.h = size
        self.base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        self.light = np.zeros((size, size, 3), dtype=np.float32)


def laser_charge(step: int, cancel: int = -1) -> tuple[Image.Image, Image.Image | None]:
    """One picture of the laser charging (`step` of CHARGE_STEPS), or of the energy scattering after
    you let go (`cancel` 0 to CANCEL_STEPS - 1), with its light layer."""
    c = _Canvas(CHARGE_CANVAS)
    mid = (CHARGE_CANVAS - 1) / 2
    t = step / CHARGE_STEPS if cancel < 0 else 0.5
    I.draw_laser_charge(c, mid, mid, 0.0, t, step % 2, cancel=0.0 if cancel < 0 else (cancel + 1) / CANCEL_STEPS)
    glow = np.zeros((CHARGE_CANVAS, CHARGE_CANVAS, 4), dtype=np.uint8)
    lit = c.light.max(axis=2) > 0
    glow[..., :3] = np.clip(c.light * 255 + 0.5, 0, 255).astype(np.uint8)
    glow[..., 3] = lit * 255
    twin = light_twin(c.base)
    out = Image.fromarray(glow)
    if twin is not None:
        out = Image.fromarray(np.maximum(np.array(out), np.array(twin)))
    return c.base, (out if np.array(out)[..., 3].any() else None)
