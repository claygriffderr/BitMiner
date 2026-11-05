"""Small pixel-art toolkit: build sprites from text grids, outline, shade, rotate and scale them,
and compose scenes with a glow pass."""

from __future__ import annotations

import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .palette import GLOW, PALETTE, rgba

CLEAR = (0, 0, 0, 0)


# ---------------------------------------------------------------- building sprites

def mirror(rows: list[str]) -> list[str]:
    """Rows hold the left half including the centre column. Returns full symmetric rows."""
    return [row + row[-2::-1] for row in rows]


def from_grid(rows: list[str], legend: dict[str, str]) -> Image.Image:
    """Turn a text grid into an RGBA image. '.' is transparent; other characters map to palette names."""
    height = len(rows)
    width = max(len(row) for row in rows)
    img = Image.new("RGBA", (width, height), CLEAR)
    px = img.load()
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in (".", " "):
                continue
            px[x, y] = rgba(legend[ch])
    return img


def outline(img: Image.Image, color: str, corners: bool = False, grow: bool = True) -> Image.Image:
    """Draw a 1px outline around the sprite's silhouette, growing the canvas by 1px per side."""
    src = img
    if grow:
        src = Image.new("RGBA", (img.width + 2, img.height + 2), CLEAR)
        src.paste(img, (1, 1))
    a = np.array(src)
    solid = a[:, :, 3] > 0
    ring = np.zeros_like(solid)
    shifts = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    if corners:
        shifts += [(-1, -1), (-1, 1), (1, -1), (1, 1)]
    for dy, dx in shifts:
        ring |= np.roll(np.roll(solid, dy, axis=0), dx, axis=1)
    ring &= ~solid
    a[ring] = rgba(color)
    return Image.fromarray(a)


def bevel(mask: np.ndarray, light: str, mid: str, dark: str, depth: int = 1) -> np.ndarray:
    """Shade a boolean mask like a raised plate lit from the top left."""
    h, w = mask.shape
    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[mask] = rgba(mid)
    for d in range(1, depth + 1):
        up = np.zeros_like(mask)
        up[d:, :] = mask[:-d, :]
        left = np.zeros_like(mask)
        left[:, d:] = mask[:, :-d]
        down = np.zeros_like(mask)
        down[:-d, :] = mask[d:, :]
        right = np.zeros_like(mask)
        right[:, :-d] = mask[:, d:]
        out[mask & (~down | ~right)] = rgba(dark)
        out[mask & (~up | ~left)] = rgba(light)
    return out


def layer(base: Image.Image, top: Image.Image, x: int = 0, y: int = 0) -> Image.Image:
    out = base.copy()
    out.alpha_composite(top, (x, y))
    return out


def recolor(img: Image.Image, mapping: dict[str, str]) -> Image.Image:
    a = np.array(img)
    out = a.copy()
    for src, dst in mapping.items():
        s = np.array(rgba(src), dtype=np.uint8)
        hit = np.all(a == s, axis=2)
        out[hit] = rgba(dst)
    return Image.fromarray(out)


def scale(img: Image.Image, k: int) -> Image.Image:
    return img.resize((img.width * k, img.height * k), Image.NEAREST)


def pad(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    out = Image.new("RGBA", size, CLEAR)
    out.alpha_composite(img, ((size[0] - img.width) // 2, (size[1] - img.height) // 2))
    return out


# ---------------------------------------------------------------- rotation

def _scale2x(a: np.ndarray) -> np.ndarray:
    """EPX / Scale2x on an RGBA array."""
    h, w, _ = a.shape
    p = np.pad(a, ((1, 1), (1, 1), (0, 0)), mode="edge")
    P = p[1:-1, 1:-1]
    A = p[:-2, 1:-1]   # up
    B = p[1:-1, 2:]    # right
    C = p[1:-1, :-2]   # left
    D = p[2:, 1:-1]    # down

    def eq(u, v):
        return np.all(u == v, axis=2)

    e0 = np.where((eq(C, A) & ~eq(C, D) & ~eq(A, B))[..., None], A, P)
    e1 = np.where((eq(A, B) & ~eq(A, C) & ~eq(B, D))[..., None], B, P)
    e2 = np.where((eq(D, C) & ~eq(D, B) & ~eq(C, A))[..., None], C, P)
    e3 = np.where((eq(B, D) & ~eq(B, A) & ~eq(D, C))[..., None], D, P)
    out = np.zeros((h * 2, w * 2, 4), dtype=a.dtype)
    out[0::2, 0::2] = e0
    out[0::2, 1::2] = e1
    out[1::2, 0::2] = e2
    out[1::2, 1::2] = e3
    return out


def rotsprite(img: Image.Image, degrees: float) -> Image.Image:
    """Rotate pixel art clockwise without blurring it (a simplified RotSprite).

    The result is always on a square canvas big enough for any angle, centred on the original
    centre, so sprites rotated by different amounts line up.
    """
    side = int(math.ceil(math.hypot(img.width, img.height))) + 2
    padded = pad(img, (side, side))
    if degrees % 360 == 0:
        return padded
    a = np.array(padded)
    for _ in range(3):
        a = _scale2x(a)
    big = Image.fromarray(a).rotate(-degrees, resample=Image.NEAREST)
    # Nearest sampling at 1/8 picks the centre of each 8x8 block.
    return big.resize((side, side), Image.NEAREST)


def rotate_smooth(img: Image.Image, degrees: float, k: int) -> Image.Image:
    """Rotate at screen resolution: scale up by k first, then rotate, so pixels turn as squares."""
    big = scale(img, k)
    side = int(math.ceil(math.hypot(big.width, big.height))) + 2
    return pad(big, (side, side)).rotate(-degrees, resample=Image.NEAREST)


def dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    """Grow a boolean mask by a disc of the given radius."""
    out = mask.copy()
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy <= radius * radius + 1 and (dx or dy):
                out |= np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
    return out


def rotate_smooth_outlined(interior: Image.Image, degrees: float, k: int, outline_color: str,
                           overlay: Image.Image | None = None) -> Image.Image:
    """Rotate an un-outlined sprite at screen resolution, then draw a k-pixel outline around it.

    This keeps the outline continuous at any angle, matching the 1px outline of upright sprites.
    """
    big = scale(interior, k)
    side = int(math.ceil(math.hypot(big.width, big.height))) + 2 * k + 2
    rot = pad(big, (side, side)).rotate(-degrees, resample=Image.NEAREST)
    a = np.array(rot)
    solid = a[:, :, 3] > 0
    ring = dilate(solid, k) & ~solid
    a[ring] = rgba(outline_color)
    out = Image.fromarray(a)
    if overlay is not None:
        ov = pad(scale(overlay, k), (side, side)).rotate(-degrees, resample=Image.NEAREST)
        out.alpha_composite(ov)
    return out


def value_noise(w: int, h: int, cell: int, seed: int) -> np.ndarray:
    """Smooth noise in 0..1 made by upscaling a small random grid."""
    rng = np.random.default_rng(seed)
    small = rng.random((h // cell + 2, w // cell + 2)).astype(np.float32)
    img = Image.fromarray((small * 255).astype(np.uint8)).resize(((w // cell + 2) * cell, (h // cell + 2) * cell), Image.BICUBIC)
    return np.array(img)[:h, :w].astype(np.float32) / 255.0


BAYER4 = (np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.float32) + 0.5) / 16.0


def dither_levels(value: np.ndarray, levels: int) -> np.ndarray:
    """Quantise 0..1 values into integer levels using a 4x4 ordered dither."""
    h, w = value.shape
    threshold = np.tile(BAYER4, (h // 4 + 1, w // 4 + 1))[:h, :w]
    scaled = np.clip(value, 0, 0.9999) * (levels - 1)
    base = np.floor(scaled)
    frac = scaled - base
    return (base + (frac > threshold)).astype(np.int32)


# ---------------------------------------------------------------- scenes with glow

_GLOW_LOOKUP = {}
for _name, _strength in GLOW.items():
    r, g, b, _ = PALETTE[_name]
    _GLOW_LOOKUP[(r << 16) | (g << 8) | b] = _strength


def emissive(img: Image.Image) -> np.ndarray:
    """Float RGB array of the light a sprite gives off, from the palette's glow table."""
    a = np.array(img).astype(np.int64)
    packed = (a[:, :, 0] << 16) | (a[:, :, 1] << 8) | a[:, :, 2]
    strength = np.zeros(packed.shape, dtype=np.float32)
    for key, s in _GLOW_LOOKUP.items():
        strength[packed == key] = s
    strength *= a[:, :, 3] / 255.0
    return a[:, :, :3].astype(np.float32) / 255.0 * strength[..., None]


class Scene:
    """A low-resolution frame (640x360 by default) with a light layer for bloom.

    Sprites blitted with `blit` sit on the pixel grid. Sprites blitted with `blit_smooth` are rotated
    at screen resolution (k times larger), so they can turn to any angle without breaking up.
    """

    def __init__(self, width: int = 640, height: int = 360, k: int = 3, background=None):
        self.w, self.h, self.k = width, height, k
        self.base = Image.new("RGBA", (width, height), rgba("space") if background is None else background)
        self.light = np.zeros((height, width, 3), dtype=np.float32)
        self.hires = Image.new("RGBA", (width * k, height * k), CLEAR)
        self.hires_light = np.zeros((height * k, width * k, 3), dtype=np.float32)
        self.overlay = Image.new("RGBA", (width, height), CLEAR)  # HUD: drawn after bloom

    def blit(self, sprite: Image.Image, x: float, y: float, center: bool = True,
             alpha: float = 1.0, glow: float = 1.0, hud: bool = False) -> None:
        if center:
            x -= sprite.width / 2
            y -= sprite.height / 2
        x, y = int(round(x)), int(round(y))
        spr = _fade(sprite, alpha)
        target = self.overlay if hud else self.base
        _composite(target, spr, x, y)
        if glow > 0:
            _add_light(self.light, emissive(spr) * glow, x, y)

    def blit_smooth(self, sprite: Image.Image, x: float, y: float, angle: float = 0.0,
                    alpha: float = 1.0, glow: float = 1.0, outline: str | None = None,
                    overlay: Image.Image | None = None) -> None:
        """Rotate at screen resolution and place centred on (x, y) in low-res coordinates.

        With `outline`, the sprite is an un-outlined interior and gets a clean outline after rotating.
        """
        if outline:
            big = rotate_smooth_outlined(sprite, angle, self.k, outline, overlay)
        else:
            big = rotate_smooth(sprite, angle, self.k)
        big = _fade(big, alpha)
        X = int(round(x * self.k - big.width / 2))
        Y = int(round(y * self.k - big.height / 2))
        _composite(self.hires, big, X, Y)
        if glow > 0:
            _add_light(self.hires_light, emissive(big) * glow, X, Y)

    def draw(self) -> ImageDraw.ImageDraw:
        return ImageDraw.Draw(self.base)

    def render(self, bloom: float = 1.0, crt: bool = False) -> Image.Image:
        k = self.k
        W, H = self.w * k, self.h * k
        frame = self.base.convert("RGBA").resize((W, H), Image.NEAREST)
        frame.alpha_composite(self.hires)
        base = np.array(frame.convert("RGB")).astype(np.float32) / 255.0
        if bloom > 0:
            light = np.array(Image.fromarray((np.clip(self.light, 0, 1) * 255).astype(np.uint8)).resize((W, H), Image.NEAREST)).astype(np.float32) / 255.0
            light = np.maximum(light, np.clip(self.hires_light, 0, 1))
            limg = Image.fromarray((light * 255).astype(np.uint8))
            near = np.array(limg.filter(ImageFilter.GaussianBlur(2.2 * k))).astype(np.float32) / 255.0
            far = np.array(limg.filter(ImageFilter.GaussianBlur(7 * k))).astype(np.float32) / 255.0
            glow = near * 0.9 + far * 0.8
            base = 1 - (1 - base) * (1 - np.clip(glow * bloom, 0, 1))  # screen blend
        out = Image.fromarray((np.clip(base, 0, 1) * 255).astype(np.uint8)).convert("RGBA")
        out.alpha_composite(self.overlay.resize((W, H), Image.NEAREST))
        if crt:
            arr = np.array(out.convert("RGB")).astype(np.float32) / 255.0
            out = Image.fromarray((np.clip(_crt(arr, k), 0, 1) * 255).astype(np.uint8))
        return out.convert("RGB")


def _fade(img: Image.Image, alpha: float) -> Image.Image:
    if alpha >= 1.0:
        return img
    a = np.array(img)
    a[:, :, 3] = (a[:, :, 3] * alpha).astype(np.uint8)
    return Image.fromarray(a)


def _composite(target: Image.Image, spr: Image.Image, x: int, y: int) -> None:
    if 0 <= x and 0 <= y and x + spr.width <= target.width and y + spr.height <= target.height:
        target.alpha_composite(spr, (x, y))
    else:
        tmp = Image.new("RGBA", target.size, CLEAR)
        tmp.paste(spr, (x, y))
        target.alpha_composite(tmp)


def _add_light(light: np.ndarray, em: np.ndarray, x: int, y: int) -> None:
    H, W, _ = light.shape
    h, w, _ = em.shape
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    if x0 >= x1 or y0 >= y1:
        return
    light[y0:y1, x0:x1] = np.maximum(light[y0:y1, x0:x1], em[y0 - y:y1 - y, x0 - x:x1 - x])


def _crt(img: np.ndarray, k: int) -> np.ndarray:
    h, w, _ = img.shape
    out = img.copy()
    # Scanlines: darken the last row of every scaled pixel row.
    rows = np.arange(h) % k == k - 1
    out[rows] *= 0.62
    # Slight colour fringing.
    out[:, 1:, 0] = 0.85 * out[:, 1:, 0] + 0.15 * out[:, :-1, 0]
    out[:, :-1, 2] = 0.85 * out[:, :-1, 2] + 0.15 * out[:, 1:, 2]
    # Vignette.
    yy, xx = np.mgrid[0:h, 0:w]
    dx = (xx - w / 2) / (w / 2)
    dy = (yy - h / 2) / (h / 2)
    vig = 1 - 0.28 * np.clip(dx * dx * 0.6 + dy * dy * 0.8, 0, 1.5)
    out *= vig[..., None]
    return out * 1.08


# ---------------------------------------------------------------- primitives

def dashed_line(draw: ImageDraw.ImageDraw, p0, p1, color, dash: int = 4, gap: int = 3, width: int = 1) -> None:
    x0, y0 = p0
    x1, y1 = p1
    length = math.hypot(x1 - x0, y1 - y0)
    if length == 0:
        return
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    t = 0.0
    while t < length:
        t2 = min(t + dash, length)
        draw.line([(x0 + ux * t, y0 + uy * t), (x0 + ux * t2, y0 + uy * t2)], fill=color, width=width)
        t += dash + gap


def pixel_circle(draw: ImageDraw.ImageDraw, cx, cy, r, color, dash: int = 0, gap: int = 0) -> None:
    """A crisp 1px circle, optionally dashed (dash and gap in pixels along the edge)."""
    steps = max(16, int(2 * math.pi * r * 1.5))
    seen = set()
    pts = []
    for i in range(steps):
        t = 2 * math.pi * i / steps
        p = (int(round(cx + r * math.cos(t))), int(round(cy + r * math.sin(t))))
        if p not in seen:
            seen.add(p)
            pts.append(p)
    for i, p in enumerate(pts):
        if dash and (i % (dash + gap)) >= dash:
            continue
        draw.point(p, fill=color)


def seeded(seed: int) -> random.Random:
    return random.Random(seed)
