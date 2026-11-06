"""Hit shapes: each ship's exact silhouette (plus its one-pixel outline), for pixel-perfect hits.

A point is turned into the sprite's own pixel grid (undoing its rotation) and looked up in the
mask, so shots hit what you can see, not a box around it.
"""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

from art import sprites as S


def _mask(img) -> np.ndarray:
    a = np.pad(np.array(img)[:, :, 3] > 0, 1)    # room for the outline
    grown = a.copy()                              # one pixel all round, like the outline
    grown[1:, :] |= a[:-1, :]
    grown[:-1, :] |= a[1:, :]
    grown[:, 1:] |= a[:, :-1]
    grown[:, :-1] |= a[:, 1:]
    return grown


@lru_cache(maxsize=None)
def enemy_mask(kind: str, ram: int = 0) -> np.ndarray:
    if kind == "infantry":
        img = S.infantry_interior(0)
    elif kind == "rapid":
        img = S.rapid_assault_interior(0)
    elif kind == "guard":
        img = S.guard_interior(0, ram)
    elif kind == "tank":
        img = S.tank_interior(0)
    elif kind == "mothership":
        img = S.mothership(0, outlined=False)
    else:
        raise KeyError(kind)
    return _mask(img)


@lru_cache(maxsize=None)
def ship_mask() -> np.ndarray:
    return _mask(S.player_interior())


def radius_of(mask: np.ndarray) -> float:
    """Half the diagonal: no hit can land farther than this from the centre."""
    h, w = mask.shape
    return math.hypot(w, h) / 2


def hits(mask: np.ndarray, cx: float, cy: float, sprite_angle: float, px: float, py: float,
         pad: float = 0.0) -> bool:
    """Does world point (px, py) land on the sprite centred at (cx, cy), turned `sprite_angle`
    degrees clockwise? `pad` widens the test for shots that are more than a pixel across."""
    h, w = mask.shape
    dx, dy = px - cx, py - cy
    if dx * dx + dy * dy > (radius_of(mask) + pad) ** 2:
        return False
    a = math.radians(sprite_angle)
    # Undo the clockwise turn: local x to the sprite's right, local y toward its top.
    lx = dx * math.cos(a) - dy * math.sin(a)
    ly = dx * math.sin(a) + dy * math.cos(a)
    r = int(math.ceil(pad))
    col0 = lx + w / 2
    row0 = h / 2 - ly
    for oy in range(-r, r + 1):
        for ox in range(-r, r + 1):
            col, row = int(math.floor(col0 + ox)), int(math.floor(row0 + oy))
            if 0 <= col < w and 0 <= row < h and mask[row, col]:
                return True
    return False


@lru_cache(maxsize=None)
def _points(key) -> np.ndarray:
    mask = ship_mask() if key == ("ship",) else enemy_mask(*key)
    h, w = mask.shape
    rows, cols = np.nonzero(mask)
    # Pixel centres as (right, up) offsets from the sprite's centre.
    return np.stack([cols + 0.5 - w / 2, h / 2 - rows - 0.5], axis=1)


def mask_points(kind: str | None = None, ram: int = 0) -> np.ndarray:
    """Every solid pixel of a hull (yours when `kind` is None) as (right, up) offsets from its centre."""
    return _points(("ship",) if kind is None else (kind, ram))


@lru_cache(maxsize=None)
def _reach(key) -> float:
    p = _points(key)
    return float(np.sqrt((p ** 2).sum(axis=1)).max()) + 0.71


def reach(kind: str | None = None, ram: int = 0) -> float:
    """How far the hull's farthest pixel corner sits from its centre: no contact happens beyond it."""
    return _reach(("ship",) if kind is None else (kind, ram))


def hits_many(mask: np.ndarray, cx: float, cy: float, sprite_angle: float, px: np.ndarray,
              py: np.ndarray) -> np.ndarray:
    """`hits` for many world points at once, with no padding. Returns a boolean array."""
    h, w = mask.shape
    a = math.radians(sprite_angle)
    dx, dy = px - cx, py - cy
    lx = dx * math.cos(a) - dy * math.sin(a)
    ly = dx * math.sin(a) + dy * math.cos(a)
    col = np.floor(lx + w / 2).astype(int)
    row = np.floor(h / 2 - ly).astype(int)
    ok = (col >= 0) & (col < w) & (row >= 0) & (row < h)
    out = np.zeros(len(px), dtype=bool)
    out[ok] = mask[row[ok], col[ok]]
    return out
