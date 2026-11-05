"""HUD pieces: the ship console (lower right), the radar (lower left), the top bar and edge arrows.

Everything is drawn at the game's 640x360 resolution.
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from . import pix, pixfont, sprites
from .palette import rgba

# ---------------------------------------------------------------- weapon icons (13x13)

WEAPON_ICONS = {
    "auto": [
        ".............",
        "..w...w...w..",
        "..w...w...w..",
        "..h...h...h..",
        "..i...i...i..",
        ".............",
        "..w...w...w..",
        "..w...w...w..",
        "..h...h...h..",
        "..i...i...i..",
        ".............",
        ".............",
        ".............",
    ],
    "sniper": [
        "......w......",
        "......w......",
        ".....www.....",
        "......w......",
        "......h......",
        "......h......",
        "......h......",
        "......i......",
        "......i......",
        "......i......",
        "......d......",
        "......d......",
        ".............",
    ],
    "explosive": [
        "......h......",
        ".....hlh.....",
        ".....mlm.....",
        ".....mlm.....",
        ".....mlm.....",
        ".....mlm.....",
        "....dmlmd....",
        "...dd.m.dd...",
        "......w......",
        ".....hwh.....",
        "......i......",
        "......d......",
        ".............",
    ],
    "laser": [
        "....dihid....",
        "....dihid....",
        "....dihid....",
        "....dihid....",
        "....dihid....",
        "....dihid....",
        "....dihid....",
        "....dihid....",
        "...dihwhid...",
        "..dihwwwhid..",
        "...dihwhid...",
        ".............",
        ".............",
    ],
}
_ICON_LEGEND = {"w": "ion_white", "h": "ion_hi", "i": "ion", "d": "ion_dark",
                "l": "hull_hi", "m": "hull_light"}
_GREY = {"ion_white": "console_hi", "ion_hi": "console_hi", "ion": "console_edge", "ion_dark": "console_mid",
         "hull_hi": "console_hi", "hull_light": "console_edge"}


def weapon_icon(kind: str, greyed: bool = False) -> Image.Image:
    img = pix.from_grid(WEAPON_ICONS[kind], _ICON_LEGEND)
    return pix.recolor(img, _GREY) if greyed else img


# ---------------------------------------------------------------- panels

def panel(w: int, h: int, fill: str = "console_dark", alpha: int = 235) -> Image.Image:
    """A console plate: dark fill, a lit top-left edge, a shadowed bottom-right edge and corner notches."""
    img = Image.new("RGBA", (w, h), pix.CLEAR)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w - 1, h - 1], fill=rgba(fill)[:3] + (alpha,))
    d.line([(1, 0), (w - 2, 0)], fill=rgba("console_hi"))
    d.line([(0, 1), (0, h - 2)], fill=rgba("console_edge"))
    d.line([(1, h - 1), (w - 2, h - 1)], fill=rgba("console_black"))
    d.line([(w - 1, 1), (w - 1, h - 2)], fill=rgba("console_black"))
    for x, y in ((2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3)):
        d.point((x, y), fill=rgba("console_edge"))
    return img


def bar(w: int, value: float, color: str, dim: str, segments: int = 0, h: int = 4) -> Image.Image:
    img = Image.new("RGBA", (w, h), pix.CLEAR)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w - 1, h - 1], fill=rgba("console_black"))
    filled = int(round((w - 2) * value))
    d.rectangle([1, 1, w - 2, h - 2], fill=rgba(dim))
    if filled > 0:
        d.rectangle([1, 1, filled, h - 2], fill=rgba(color))
        d.line([(1, 1), (filled, 1)], fill=rgba("ion_white") if color.startswith("ion") else rgba(color))
    if segments:
        step = (w - 2) / segments
        for i in range(1, segments):
            x = int(round(1 + i * step))
            d.line([(x, 1), (x, h - 2)], fill=rgba("console_black"))
    return img


def ship_console(shield: float = 0.62, hull: float = 0.8, armor_level: int = 2, armor_max: int = 5,
                 weapon: str = "auto", ammo: float = 1.0, others: tuple[str, ...] = ("sniper", "explosive", "laser"),
                 low_hull: bool = False) -> Image.Image:
    """The lower-right console: weapons on top, then shield, hull and armor, then the ship icon."""
    w, h = 118, 92
    img = Image.new("RGBA", (w, h), pix.CLEAR)
    # Weapon row: current weapon large on the right, others small and grey to its left.
    cur = panel(26, 26)
    fill = Image.new("RGBA", (22, 22), pix.CLEAR)
    fd = ImageDraw.Draw(fill)
    level = int(round(22 * ammo))
    if level:
        fd.rectangle([0, 22 - level, 21, 21], fill=rgba("ion_dark")[:3] + (150,))
        fd.line([(0, 22 - level), (21, 22 - level)], fill=rgba("ion"))
    cur.alpha_composite(fill, (2, 2))
    cur.alpha_composite(weapon_icon(weapon), (6, 6))
    img.alpha_composite(cur, (w - 26, 0))
    x = w - 26 - 4
    for kind in others:
        small = panel(17, 17, "console_black")
        icon = weapon_icon(kind, greyed=True).resize((9, 9), Image.NEAREST)
        small.alpha_composite(icon, (4, 4))
        x -= 17
        img.alpha_composite(small, (x, 9))
        x -= 2
    img.alpha_composite(pixfont.render("WPN", "hud_dim"), (x - 16, 14))
    # Protection block.
    prot = panel(w, 36)
    rows = [("SHLD", bar(70, shield, "ion", "ion_dark")),
            ("HULL", bar(70, hull, "danger_red" if low_hull else "hud_text", "danger_dark" if low_hull else "console_mid")),
            ("ARMR", bar(70, armor_level / armor_max, "hull_hi", "console_mid", segments=armor_max))]
    for i, (label, b) in enumerate(rows):
        y = 4 + i * 10
        prot.alpha_composite(pixfont.render(label, "hud_dim"), (5, y))
        prot.alpha_composite(b, (w - 76, y + 1))
    img.alpha_composite(prot, (0, 30))
    # Ship icon plate at the bottom right.
    plate = panel(26, 24)
    icon = sprites.tight(sprites.player_ship())
    plate.alpha_composite(icon, ((26 - icon.width) // 2, (24 - icon.height) // 2))
    img.alpha_composite(plate, (w - 26, 68))
    lives_lbl = pixfont.render("LIVES", "hud_dim")
    img.alpha_composite(lives_lbl, (w - 26 - 4 - lives_lbl.width - 34, 76))
    for i in range(3):
        pip = Image.new("RGBA", (7, 7), pix.CLEAR)
        pd = ImageDraw.Draw(pip)
        pd.polygon([(3, 0), (6, 6), (0, 6)], fill=rgba("hud_text") if i < 2 else rgba("console_mid"))
        img.alpha_composite(pip, (w - 26 - 4 - 30 + i * 10, 76))
    return img


def boss_bar(name: str = "MOTHERSHIP", health: float = 0.62, recent: float = 0.0, width: int = 236) -> Image.Image:
    """A boss's health, shown at the bottom centre while you're close enough to fight it.

    `recent` is health just knocked off by your hits. It flashes in your pale cyan before draining.
    """
    img = panel(width, 15)
    label = pixfont.render(name, "alien_purple_hi")
    img.alpha_composite(label, (6, 4))
    x0 = 6 + label.width + 7
    bw, bh = width - x0 - 6, 7
    b = Image.new("RGBA", (bw, bh), pix.CLEAR)
    d = ImageDraw.Draw(b)
    d.rectangle([0, 0, bw - 1, bh - 1], fill=rgba("console_black"))
    d.rectangle([1, 1, bw - 2, bh - 2], fill=rgba("alien_purple_black"))
    inner = bw - 2
    filled = int(round(inner * health))
    lost = int(round(inner * min(1.0, health + recent))) - filled
    if filled > 0:
        d.rectangle([1, 1, filled, bh - 2], fill=rgba("alien_purple"))
        d.line([(1, 1), (filled, 1)], fill=rgba("alien_purple_hi"))
        d.line([(1, bh - 2), (filled, bh - 2)], fill=rgba("alien_purple_dark"))
    if lost > 0:
        d.rectangle([filled + 1, 1, filled + lost, bh - 2], fill=rgba("hud_text"))
    for i in range(1, 10):
        x = int(round(1 + i * inner / 10))
        d.line([(x, 1), (x, bh - 2)], fill=rgba("console_black"))
    img.alpha_composite(b, (x0, 4))
    return img


# ---------------------------------------------------------------- radar

def radar(blips: list[tuple[float, float, str]], sweep: float = 35.0, radius: int = 38) -> Image.Image:
    """Round radar. Blips are (dx, dy, kind) in radar pixels from the centre.
    Kinds: enemy, boss, base, drill, danger."""
    size = radius * 2 + 9
    img = Image.new("RGBA", (size, size), pix.CLEAR)
    d = ImageDraw.Draw(img)
    c = size // 2
    d.ellipse([c - radius - 3, c - radius - 3, c + radius + 3, c + radius + 3], fill=rgba("console_mid"))
    d.ellipse([c - radius - 2, c - radius - 2, c + radius + 2, c + radius + 2], fill=rgba("console_edge"))
    d.ellipse([c - radius - 1, c - radius - 1, c + radius + 1, c + radius + 1], fill=rgba("console_black"))
    d.ellipse([c - radius, c - radius, c + radius, c + radius], fill=rgba("console_black")[:3] + (235,))
    for r in (radius * 2 // 3, radius // 3):
        pix.pixel_circle(d, c, c, r, rgba("console_mid"), dash=2, gap=2)
    d.line([(c - radius + 2, c), (c + radius - 2, c)], fill=rgba("console_dark"))
    d.line([(c, c - radius + 2), (c, c + radius - 2)], fill=rgba("console_dark"))
    # Sweep with a fading trail.
    for i in range(12):
        ang = math.radians(sweep - i * 3)
        col = rgba("ion_dark")[:3] + (int(160 * (1 - i / 12)),)
        d.line([(c, c), (c + (radius - 1) * math.cos(ang), c + (radius - 1) * math.sin(ang))], fill=col)
    colors = {"enemy": "alien_green_hi", "boss": "alien_purple_hi", "base": "ion_hi", "drill": "ore", "danger": "danger_pink"}
    for dx, dy, kind in blips:
        x, y = c + dx, c + dy
        if math.hypot(dx, dy) > radius - 2:
            ang = math.atan2(dy, dx)
            x, y = c + (radius - 3) * math.cos(ang), c + (radius - 3) * math.sin(ang)
        x, y = int(round(x)), int(round(y))
        col = rgba(colors[kind])
        if kind == "base":
            d.rectangle([x - 1, y - 1, x + 1, y + 1], outline=col)
        elif kind == "boss":
            d.rectangle([x - 2, y - 1, x + 2, y + 1], fill=col)
        elif kind == "drill":
            d.point((x, y), fill=col)
            d.point((x, y - 1), fill=col)
        else:
            d.point((x, y), fill=col)
            d.point((x + 1, y), fill=col)
    # Player at the centre.
    d.polygon([(c, c - 2), (c + 2, c + 2), (c - 2, c + 2)], fill=rgba("hud_text"))
    lbl = pixfont.render("RADAR", "hud_dim")
    out = Image.new("RGBA", (size, size + 9), pix.CLEAR)
    out.alpha_composite(img, (0, 0))
    out.alpha_composite(lbl, ((size - lbl.width) // 2, size + 1))
    return out


# ---------------------------------------------------------------- top bar

def top_bar(wave: int = 7, next_wave: str = "0:42", credits: int = 1240, ore: tuple[int, int] = (36, 50),
            alert: str | None = None) -> list[tuple[Image.Image, int, int]]:
    """Returns pieces with their positions on a 640x360 screen."""
    pieces = []
    left = panel(116, 15)
    left.alpha_composite(pixfont.render("CR", "hud_dim"), (5, 4))
    left.alpha_composite(pixfont.render(f"{credits:,}", "ore"), (19, 4))
    left.alpha_composite(pixfont.render("ORE", "hud_dim"), (60, 4))
    left.alpha_composite(pixfont.render(f"{ore[0]}/{ore[1]}", "ore"), (80, 4))
    pieces.append((left, 6, 6))
    mid_text = pixfont.render(f"WAVE {wave}", "hud_text")
    nxt = pixfont.render(f"NEXT {next_wave}", "danger_pink_hi")
    mid = panel(mid_text.width + nxt.width + 22, 15)
    mid.alpha_composite(mid_text, (6, 4))
    mid.alpha_composite(nxt, (mid_text.width + 16, 4))
    pieces.append((mid, (640 - mid.width) // 2, 6))
    if alert:
        a = pixfont.render(alert, "danger_pink_hi")
        plate = panel(a.width + 12, 15, "console_black")
        plate.alpha_composite(a, (6, 4))
        pieces.append((plate, (640 - plate.width) // 2, 25))
    return pieces


# ---------------------------------------------------------------- edge arrows

def edge_arrow(angle_deg: float, color: str, size: int = 7) -> Image.Image:
    """A small triangle pointing along angle_deg (0 = right, 90 = down)."""
    s = size * 2 + 3
    img = Image.new("RGBA", (s, s), pix.CLEAR)
    d = ImageDraw.Draw(img)
    c = s / 2
    a = math.radians(angle_deg)
    tip = (c + size * math.cos(a), c + size * math.sin(a))
    l = (c + size * 0.7 * math.cos(a + 2.4), c + size * 0.7 * math.sin(a + 2.4))
    r = (c + size * 0.7 * math.cos(a - 2.4), c + size * 0.7 * math.sin(a - 2.4))
    d.polygon([tip, l, r], fill=rgba(color))
    return img


def place_edge_arrow(scene: pix.Scene, target: tuple[float, float], color: str, label: str | None = None,
                     margin: int = 10, alpha: float = 0.55, centre: tuple[float, float] = (320, 180)) -> None:
    """Point from the screen centre toward an off-screen target, pinned to the nearest edge."""
    cx, cy = centre
    dx, dy = target[0] - cx, target[1] - cy
    ang = math.degrees(math.atan2(dy, dx))
    # Scale the direction so it touches the inset screen rectangle.
    sx = (scene.w / 2 - margin) / abs(dx) if dx else float("inf")
    sy = (scene.h / 2 - margin) / abs(dy) if dy else float("inf")
    k = min(sx, sy)
    x, y = cx + dx * k, cy + dy * k
    scene.blit(edge_arrow(ang, color), x, y, alpha=alpha, glow=0.4)
    if label:
        txt = pixfont.render(label, color)
        lx = x - math.cos(math.radians(ang)) * (txt.width / 2 + 10)
        ly = y - math.sin(math.radians(ang)) * 12
        scene.blit(txt, lx, ly, alpha=min(1.0, alpha + 0.25), glow=0.2)
