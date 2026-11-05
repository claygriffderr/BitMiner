"""Small effect sprites for the weapon gallery: muzzle flashes, impact flares, shockwave rings,
the shield bubble and flying debris. Same palette and colour jobs as the rest of the art:
cyan and white for your weapons, pink and red for anything that hurts you, green and purple
for enemy hulls, steel for the guards' scoops.
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from . import pix
from .palette import rgba

# Tones from brightest to darkest for each owner.
TONES = {
    "player": ["ion_white", "ion_hi", "ion", "ion_dark"],
    "danger": ["danger_white", "danger_pink_hi", "danger_pink", "danger_red"],
    "enemy": ["alien_eye", "alien_green_hi", "alien_purple_hi", "alien_purple"],
    "steel": ["steel_hi", "steel_light", "steel_mid", "steel_dark"],
}


def muzzle_flash(kind: str, frame: int = 0) -> Image.Image:
    """The flash at the gun, pointing up (forward). `kind` is auto, sniper or missile."""
    if kind == "auto":
        rows = [".w.", "whw", ".h."] if frame == 0 else ["...", ".h.", "..."]
    elif kind == "sniper":
        rows = [
            "...w...",
            "...w...",
            "..hwh..",
            "h.hwh.h",
            ".hwwwh.",
            "..hhh..",
        ] if frame == 0 else [
            ".......",
            "...h...",
            "...h...",
            "..ihi..",
            "..hhh..",
            ".......",
        ]
    else:  # missile launch: a puff out of the pod
        rows = [".h.", "hwh", ".h."] if frame == 0 else [".i.", "i.i", ".i."]
    return pix.from_grid(rows, {"w": "ion_white", "h": "ion_hi", "i": "ion"})


def flare(owner: str = "player", frame: int = 0) -> Image.Image:
    """A bright star where a shot lands. Frame 0 is the big flash, frame 1 its afterglow."""
    t = TONES[owner]
    if frame == 0:
        rows = ["..b..", ".bab.", "babab", ".bab.", "..b.."]
        legend = {"a": t[0], "b": t[1]}
    else:
        rows = [".....", "..c..", ".cbc.", "..c..", "....."]
        legend = {"b": t[1], "c": t[2]}
    return pix.from_grid(rows, legend)


def beam_contact(owner: str = "player", frame: int = 0) -> Image.Image:
    """Where a laser touches a hull: a flickering 7x7 burst."""
    t = TONES[owner]
    if frame % 2 == 0:
        rows = ["...c...", ".c.b.c.", "..bab..", "cbaaabc", "..bab..", ".c.b.c.", "...c..."]
    else:
        rows = [".......", "..c.c..", ".cbab..", "..aaab.", ".babc..", "..c.c..", "......."]
    return pix.from_grid(rows, {"a": t[0], "b": t[1], "c": t[2]})


def ring(radius: int, owner: str = "player", tone: int = 0, dash: int = 0) -> Image.Image:
    """A crisp one-pixel ring, used for shockwaves (tone fades as it grows) and the shield bubble."""
    size = radius * 2 + 3
    img = Image.new("RGBA", (size, size), pix.CLEAR)
    d = ImageDraw.Draw(img)
    c = size // 2
    pix.pixel_circle(d, c, c, radius, rgba(TONES[owner][min(3, tone)]), dash=dash, gap=dash)
    return img


def shockwave(radius: int, owner: str, age: float) -> Image.Image:
    """A ring that fades from white to dark as `age` goes from 0 to 1, with a broken trailing edge."""
    tone = min(3, int(age * 4))
    img = ring(radius, owner, tone)
    if radius >= 6 and age < 0.6:
        inner = ring(radius - 2, owner, min(3, tone + 1), dash=2)
        img.alpha_composite(pix.pad(inner, img.size))
    return img


def shield_bubble(radius: int, frame: int = 0) -> Image.Image:
    """The shield shown for a moment after a hit: a dashed cyan circle that crawls round."""
    size = radius * 2 + 3
    img = Image.new("RGBA", (size, size), pix.CLEAR)
    d = ImageDraw.Draw(img)
    c = size // 2
    steps = max(16, int(2 * math.pi * radius * 1.5))
    seen = []
    for i in range(steps):
        a = 2 * math.pi * i / steps
        p = (int(round(c + radius * math.cos(a))), int(round(c + radius * math.sin(a))))
        if p not in seen:
            seen.append(p)
    for i, p in enumerate(seen):
        if (i + frame) % 5 < 3:
            d.point(p, fill=rgba("ion_dark"))
        elif (i + frame) % 5 == 3:
            d.point(p, fill=rgba("ion"))
    return img


def shield_break(radius: int, frame: int) -> Image.Image:
    """The shield shattering: the bubble splits into arcs that fly apart over four frames."""
    r = radius + frame * 3
    size = r * 2 + 3
    img = Image.new("RGBA", (size, size), pix.CLEAR)
    d = ImageDraw.Draw(img)
    c = size // 2
    tone = ["ion_white", "ion_hi", "ion", "ion_dark"][min(3, frame)]
    steps = max(16, int(2 * math.pi * r * 1.5))
    for i in range(steps):
        a = 2 * math.pi * i / steps
        if (a * 6 / math.tau + frame * 0.3) % 1 < 0.55 - frame * 0.08:
            d.point((int(round(c + r * math.cos(a))), int(round(c + r * math.sin(a)))), fill=rgba(tone))
    return img


def debris(kind: str, variant: int = 0) -> Image.Image:
    """A small chunk of hull for explosions to throw. Kinds: enemy, steel, player."""
    shapes = [
        ["ab", "bc"],
        ["abb", ".bc"],
        ["a.", "bb", ".c"],
        ["abc"],
    ]
    rows = shapes[variant % len(shapes)]
    legend = {
        "enemy": {"a": "alien_purple_hi", "b": "alien_purple", "c": "alien_purple_dark"},
        "steel": {"a": "steel_hi", "b": "steel_light", "c": "steel_mid"},
        "player": {"a": "hull_hi", "b": "hull_mid", "c": "hull_dark"},
    }[kind]
    return pix.from_grid(rows, legend)


def health_bar(width: int, fraction: float) -> Image.Image:
    """A thin bar shown over a damaged enemy: dark track, green fill."""
    img = Image.new("RGBA", (width, 3), rgba("alien_purple_black"))
    a = np.array(img)
    fill = int(round((width - 2) * max(0.0, min(1.0, fraction))))
    if fill:
        a[1, 1:1 + fill] = rgba("alien_green_hi")
    return Image.fromarray(a)
