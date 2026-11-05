"""Every BitMiner sprite, drawn as text grids or built from simple shapes.

Ships face up (the mothership faces down). Rotation happens before the outline is drawn, so
outlines stay unbroken at any angle. The player turns smoothly; enemies snap between eight
directions, and their diagonals are turned the same way as the player's ship (`Scene.blit_smooth`
with the `*_interior` sprites), so their pixels stay square.
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from . import pix
from .palette import rgba


def _finish(interior: Image.Image, outline: str, angle: float = 0.0, extra: Image.Image | None = None) -> Image.Image:
    """Rotate (if asked), then outline, then add any unoutlined overlay such as engine flames."""
    if angle:
        body = pix.rotsprite(interior, angle)
        overlay = pix.rotsprite(extra, angle) if extra is not None else None
        body = pix.outline(body, outline, grow=False)
    else:
        body = pix.outline(interior, outline)
        overlay = pix.pad(extra, body.size) if extra is not None else None
    if overlay is not None:
        body.alpha_composite(pix.pad(overlay, body.size))
    return body


def tight(img: Image.Image) -> Image.Image:
    box = img.getbbox()
    return img.crop(box) if box else img


# ---------------------------------------------------------------- player ship

PLAYER_LEGEND = {
    "d": "hull_dark", "m": "hull_mid", "l": "hull_light", "h": "hull_hi",
    "c": "canopy", "C": "canopy_hi", "n": "hull_black",
}

PLAYER_ROWS = pix.mirror([
    ".......h",
    "......hl",
    "......hl",
    ".....mlc",
    ".....mcC",
    "....dmcc",
    ".ndddmml",
    "dlddmmml",
    "nlllmmml",
    "nlmlmmml",
    "dmmdmdml",
    ".ddddmmm",
    "..dd.dmm",
    ".....dnn",
    "......nn",
])

# Booster flames in interior-grid coordinates (the interior is 15x15).
_FLAMES = {
    # W: main engine at the back.
    "W": [((7, 15), "ion_white"), ((6, 15), "ion_hi"), ((8, 15), "ion_hi"),
          ((7, 16), "ion_white"), ((6, 16), "ion"), ((8, 16), "ion"),
          ((7, 17), "ion_hi"), ((7, 18), "ion")],
    "W+": [((7, 19), "ion_dark")],
    # S: retro thrusters on the front of each pod.
    "S": [((1, 5), "ion_white"), ((1, 4), "ion_hi"), ((1, 3), "ion"),
          ((13, 5), "ion_white"), ((13, 4), "ion_hi"), ((13, 3), "ion")],
    "S+": [((1, 2), "ion_dark"), ((13, 2), "ion_dark")],
    # A: strafe left, so the right-hand thruster fires.
    "A": [((15, 8), "ion_white"), ((15, 9), "ion_white"), ((16, 8), "ion_hi"), ((16, 9), "ion_hi"),
          ((17, 8), "ion"), ((17, 9), "ion")],
    "A+": [((18, 9), "ion_dark")],
    # D: strafe right, so the left-hand thruster fires.
    "D": [((-1, 8), "ion_white"), ((-1, 9), "ion_white"), ((-2, 8), "ion_hi"), ((-2, 9), "ion_hi"),
          ((-3, 8), "ion"), ((-3, 9), "ion")],
    "D+": [((-4, 8), "ion_dark")],
}
_SHIP_CANVAS, _SHIP_OFFSET = 27, 6


def player_interior() -> Image.Image:
    return pix.from_grid(PLAYER_ROWS, PLAYER_LEGEND)


def player_flames(boosters: tuple[str, ...], frame: int = 0) -> Image.Image:
    img = Image.new("RGBA", (_SHIP_CANVAS, _SHIP_CANVAS), pix.CLEAR)
    px = img.load()
    for key in boosters:
        points = list(_FLAMES[key])
        if frame % 2 == 0:
            points += _FLAMES[key + "+"]
        for (x, y), name in points:
            px[x + _SHIP_OFFSET, y + _SHIP_OFFSET] = rgba(name)
    return img


def player_parts(boosters: tuple[str, ...] = (), frame: int = 0) -> tuple[Image.Image, Image.Image]:
    """The un-outlined ship and its flames on matching canvases, for smooth rotation in the game."""
    interior = pix.pad(player_interior(), (_SHIP_CANVAS, _SHIP_CANVAS))
    return interior, player_flames(boosters, frame)


def player_ship(angle: float = 0.0, boosters: tuple[str, ...] = (), frame: int = 0) -> Image.Image:
    """The drab mining ship. Boosters: W (main), S (retro), A and D (side thrusters)."""
    interior = pix.pad(player_interior(), (_SHIP_CANVAS, _SHIP_CANVAS))
    flames = player_flames(boosters, frame) if boosters else None
    return _finish(interior, "hull_outline", angle, flames)


# ---------------------------------------------------------------- player hardware

def sentry_interior(firing: bool = False) -> Image.Image:
    rows = pix.mirror([
        "....i",
        "....l",
        "...dl",
        "..dmh",
        ".dmlh",
        ".mlhc",
        ".dmlh",
        "..dmm",
        ".dd..",
    ])
    legend = {"i": "ion_white" if firing else "ion_hi", "d": "hull_dark", "m": "hull_mid",
              "l": "hull_light", "h": "hull_hi", "c": "canopy"}
    return pix.from_grid(rows, legend)


def sentry(angle: float = 0.0, firing: bool = False) -> Image.Image:
    return _finish(sentry_interior(firing), "hull_outline", angle)


def drill(frame: int = 0) -> Image.Image:
    """A tripod rig that sits on an asteroid. The light blinks while it works; the hopper shows ore."""
    status = "ion_hi" if frame % 2 == 0 else "ion_dark"
    rows = pix.mirror([
        ".....i",
        ".....h",
        "....dm",
        "...dml",
        "..dmOO",
        "..dmOo",
        "..ddmm",
        ".d..dl",
        ".d...l",
        "d....l",
        "d....n",
    ])
    legend = {"d": "hull_dark", "m": "hull_mid", "l": "hull_light", "h": "hull_hi", "i": status,
              "O": "ore", "o": "ore_hi", "n": "hull_black"}
    return _finish(pix.from_grid(rows, legend), "hull_outline")


def home_base(frame: int = 0) -> Image.Image:
    """An 80x64 station: docking ring, four spokes, a lit hub and two solar wings."""
    w, h = 80, 64
    cx, cy = (w - 1) / 2, (h - 1) / 2
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot(xx - cx, yy - cy)
    ring = (r <= 29) & (r >= 23)
    hub = r <= 11
    spokes = ((np.abs(xx - cx) <= 2.5) | (np.abs(yy - cy) <= 2.5)) & (r <= 24)
    arms = (np.abs(yy - cy) <= 1.5) & (np.abs(xx - cx) <= 33) & (r > 28)
    wings = (np.abs(yy - cy) <= 7) & (np.abs(xx - cx) >= 33) & (np.abs(xx - cx) <= 39)
    pads = np.zeros_like(ring)
    pad_centres = []
    for ang in (45, 135, 225, 315):
        px_, py_ = cx + 26 * math.cos(math.radians(ang)), cy + 26 * math.sin(math.radians(ang))
        pad_centres.append((px_, py_))
        pads |= (np.abs(xx - px_) <= 4) & (np.abs(yy - py_) <= 4)
    out = np.zeros((h, w, 4), dtype=np.uint8)
    for mask, tones in ((arms, ("hull_mid", "hull_dark", "hull_black")),
                        (wings, ("hull_mid", "hull_dark", "hull_black")),
                        (ring, ("hull_light", "hull_mid", "hull_dark")),
                        (spokes & ~hub, ("hull_mid", "hull_dark", "hull_black")),
                        (pads, ("hull_hi", "hull_light", "hull_dark")),
                        (hub, ("hull_hi", "hull_light", "hull_dark"))):
        shaded = pix.bevel(mask, *tones)
        out[mask] = shaded[mask]
    # Solar cells: a grid of canopy-blue cells on the wings.
    cells = wings & ((xx.astype(int) % 2) == 0) & ((yy.astype(int) % 3) != 0)
    inner = wings & (np.abs(yy - cy) <= 6) & (np.abs(xx - cx) >= 34) & (np.abs(xx - cx) <= 38)
    out[cells & inner] = rgba("canopy")
    # Ring panel seams.
    for ang in range(0, 360, 30):
        sx = int(round(cx + 26 * math.cos(math.radians(ang + 15))))
        sy = int(round(cy + 26 * math.sin(math.radians(ang + 15))))
        if ring[sy, sx] and not pads[sy, sx]:
            out[sy - 1:sy + 2, sx] = rgba("hull_dark")
    # Hub window ring and core light.
    out[(r <= 7.5) & (r >= 6.2)] = rgba("canopy")
    out[r <= 3.2] = rgba("hull_mid")
    out[r <= 1.6] = rgba("ion_hi")
    img = Image.fromarray(out)
    d = ImageDraw.Draw(img)
    lit = "ion_hi" if frame % 2 == 0 else "ion"
    for px_, py_ in pad_centres:
        for ox_, oy_ in ((-3, -3), (3, -3), (-3, 3), (3, 3)):
            d.point((round(px_ + ox_), round(py_ + oy_)), fill=rgba(lit))
        d.point((round(px_), round(py_)), fill=rgba("hull_dark"))
    return pix.outline(img, "hull_outline")


# ---------------------------------------------------------------- player shots

def shot_auto() -> Image.Image:
    return pix.from_grid(["w", "w", "h", "i", "d"], {"w": "ion_white", "h": "ion_hi", "i": "ion", "d": "ion_dark"})


def shot_sniper() -> Image.Image:
    rows = [".w.", "www", ".w.", ".w.", ".h.", ".h.", ".h.", ".i.", ".i.", ".i.", ".d.", ".d."]
    return pix.from_grid(rows, {"w": "ion_white", "h": "ion_hi", "i": "ion", "d": "ion_dark"})


def missile_player(frame: int = 0) -> Image.Image:
    rows = [
        ".h.",
        "hlh",
        "mlm",
        "mlm",
        "dmd",
        "d.d",
        ".w.",
        ".i." if frame % 2 == 0 else ".h.",
        ".j." if frame % 2 == 0 else "...",
    ]
    legend = {"h": "hull_hi", "l": "hull_light", "m": "hull_mid", "d": "hull_dark",
              "w": "ion_white", "i": "ion", "j": "ion_dark"}
    return pix.from_grid(rows, legend)


def laser_player(length: int = 120, frame: int = 0) -> Image.Image:
    """The sweeping beam, pointing up from its base at the bottom."""
    w = 9
    img = Image.new("RGBA", (w, length), pix.CLEAR)
    d = ImageDraw.Draw(img)
    wobble = frame % 2
    d.rectangle([0 + wobble, 0, w - 1 - wobble, length - 1], fill=rgba("ion_dark"))
    d.rectangle([1, 0, w - 2, length - 1], fill=rgba("ion"))
    d.rectangle([2, 0, w - 3, length - 1], fill=rgba("ion_hi"))
    d.rectangle([3, 0, w - 4, length - 1], fill=rgba("ion_white"))
    a = np.array(img)
    a[:3, :, 3] = 0
    a[3, [0, 1, 7, 8], 3] = 0
    a[4, [0, 8], 3] = 0
    return Image.fromarray(a)


# ---------------------------------------------------------------- enemies

ENEMY_OUTLINE = "alien_purple_black"


def _eye(frame: int) -> str:
    return "alien_eye" if frame % 2 == 0 else "alien_green_hi"


def infantry_interior(frame: int = 0) -> Image.Image:
    rows = pix.mirror([
        ".G...",
        ".gG..",
        "..gg.",
        ".gpgE",
        "gpPpg",
        "gpPpp",
        "Gp.pd",
        "G..d.",
    ])
    legend = {"g": "alien_green", "G": "alien_green_hi", "p": "alien_purple", "P": "alien_purple_hi",
              "d": "alien_purple_dark", "E": _eye(frame)}
    return pix.from_grid(rows, legend)


def infantry(frame: int = 0, angle: float = 0.0) -> Image.Image:
    return _finish(infantry_interior(frame), ENEMY_OUTLINE, angle)


GUARD_ROWS = pix.mirror([
    ".dPPPPP",
    "dPpppPP",
    "dppddpp",
    "dpgggdd",
    "dpgEEEE",
    "dpgggdd",
    "dppddpp",
    "dpppppp",
    ".dpp.pp",
    "..dd.dd",
])

# The ram scoop, seen from above like a bulldozer blade. Stage 1 is folded flat against the nose,
# stage 2 swings the wings out, stage 3 pushes the blade forward on its arms.
SCOOP_STAGES = {
    1: pix.mirror([
        "..MLLLLLL",
        "..DMMMMMM",
    ]),
    2: pix.mirror([
        "LW.......",
        "MLWWWWWWW",
        "DMMMMMMMM",
        ".DLLLLLLL",
        "..DDDDDDD",
    ]),
    3: pix.mirror([
        "W........",
        "LW.......",
        "MLWWWWWWW",
        "DMMMMMMMM",
        ".DLLLLLLL",
        "..DDDDDDD",
        "...DM....",
        "...DM....",
    ]),
}
_SCOOP_DEPTH = max(len(rows) for rows in SCOOP_STAGES.values())
_SCOOP_WIDTH = max(len(rows[0]) for rows in SCOOP_STAGES.values())


def guard_interior(frame: int = 0, ram: int = 0) -> Image.Image:
    """The guard without its outline. `ram` 1 to 3 shows the steel scoop sliding out before a ram.

    With the scoop out, the canvas grows by the same amount front and back, so the guard's body
    stays centred and the sprite still turns around the body.
    """
    eye = "danger_pink_hi" if ram else _eye(frame)
    legend = {"d": "alien_purple_dark", "p": "alien_purple", "P": "alien_purple_hi",
              "g": "alien_green", "E": eye,
              "W": "steel_hi", "L": "steel_light", "M": "steel_mid", "D": "steel_dark"}
    if not ram:
        return pix.from_grid(GUARD_ROWS, legend)
    w = _SCOOP_WIDTH
    scoop = SCOOP_STAGES[ram]
    rows = ["." * w] * (_SCOOP_DEPTH - len(scoop))
    for row in scoop + GUARD_ROWS:
        p = (w - len(row)) // 2
        rows.append("." * p + row + "." * (w - len(row) - p))
    rows += ["." * w] * _SCOOP_DEPTH
    return pix.from_grid(rows, legend)


def guard(frame: int = 0, ram: int = 0, angle: float = 0.0) -> Image.Image:
    return _finish(guard_interior(frame, ram), ENEMY_OUTLINE, angle)


def scoop_reach() -> int:
    """How far the fully deployed scoop's front edge sits ahead of the guard's centre, outline included."""
    return len(GUARD_ROWS) // 2 + _SCOOP_DEPTH + 1


def glint(frame: int = 0) -> Image.Image:
    """A quick sparkle on polished metal, used when the ram scoop locks into place."""
    rows = [".W.", "WwW", ".W."] if frame % 2 == 0 else ["..W..", "..W..", "WWwWW", "..W..", "..W.."]
    return pix.from_grid(rows, {"W": "steel_hi", "w": "star_bright"})


def rapid_assault_interior(frame: int = 0) -> Image.Image:
    rows = pix.mirror([
        "...G",
        "...G",
        "..gG",
        "..gE",
        "..gG",
        ".ggp",
        ".g.p",
        "gg.p",
        "g..d",
        "g...",
    ])
    legend = {"g": "alien_green", "G": "alien_green_hi", "p": "alien_purple", "d": "alien_purple_dark",
              "E": _eye(frame)}
    return pix.from_grid(rows, legend)


def rapid_assault(frame: int = 0, angle: float = 0.0) -> Image.Image:
    return _finish(rapid_assault_interior(frame), ENEMY_OUTLINE, angle)


def _bevel_into(out: np.ndarray, mask: np.ndarray, tones: tuple[str, str, str]) -> None:
    shaded = pix.bevel(mask, *tones)
    out[mask] = shaded[mask]


def tank(frame: int = 0, pods_loaded: bool = True, angle: float = 0.0) -> Image.Image:
    """27x27 boss: a front plow, two missile pods and a big green core."""
    return _finish(tank_interior(frame, pods_loaded), ENEMY_OUTLINE, angle)


def tank_interior(frame: int = 0, pods_loaded: bool = True) -> Image.Image:
    """The tank without its outline."""
    s = 27
    c = (s - 1) / 2
    yy, xx = np.mgrid[0:s, 0:s]
    out = np.zeros((s, s, 4), dtype=np.uint8)

    def rect(x0, y0, x1, y1):
        return (xx >= x0) & (xx <= x1) & (yy >= y0) & (yy <= y1)

    def poly(points):
        m = Image.new("L", (s, s), 0)
        ImageDraw.Draw(m).polygon(points, fill=255)
        return np.array(m) > 0

    body = rect(5, 5, 21, 23) & ~(rect(5, 5, 6, 6) | rect(20, 5, 21, 6) | rect(5, 22, 6, 23) | rect(20, 22, 21, 23))
    _bevel_into(out, body, ("alien_purple", "alien_purple_dark", "alien_purple_black"))
    for side in (0, 1):
        x0 = 0 if side == 0 else 21
        pod = rect(x0, 8, x0 + 5, 19)
        _bevel_into(out, pod, ("alien_purple_hi", "alien_purple", "alien_purple_dark"))
        for tx in (x0 + 1, x0 + 4):
            out[9:18, tx] = rgba("alien_purple_black")
            tip, tip_hi = ("danger_pink", "danger_pink_hi") if pods_loaded else ("alien_purple_dark", "alien_purple_dark")
            out[8, tx] = rgba(tip_hi)
            out[9, tx] = rgba(tip)
    plow = poly([(3, 7), (13, 0), (23, 7), (21, 9), (13, 4), (5, 9)])
    _bevel_into(out, plow, ("alien_purple_hi", "alien_purple", "alien_purple_dark"))
    for side in (0, 1):
        x0 = 8 if side == 0 else 16
        plate = rect(x0, 9, x0 + 2, 20)
        _bevel_into(out, plate, ("alien_purple_hi", "alien_purple", "alien_purple_dark"))
    r = np.hypot(xx - c, yy - 14)
    out[r <= 4.5] = rgba("alien_purple_black")
    out[r <= 3.6] = rgba("alien_green_dark")
    out[r <= 2.8] = rgba("alien_green")
    out[(r <= 1.8)] = rgba("alien_green_hi")
    out[(r <= 0.9)] = rgba(_eye(frame))
    # Rear vents.
    for vx in range(9, 18, 2):
        out[22, vx] = rgba("alien_green_dark" if frame % 2 else "alien_green")
    return Image.fromarray(out)


def mothership(frame: int = 0, laser_charge: float = 0.0, outlined: bool = True) -> Image.Image:
    """A 220x160 carrier: hangar bays, turrets, missile racks and a laser emitter at the nose (facing down).

    `outlined=False` gives the interior, for turning it smoothly and outlining it afterwards.
    """
    w, h = 220, 160
    cx = (w - 1) / 2
    yy, xx = np.mgrid[0:h, 0:w]
    out = np.zeros((h, w, 4), dtype=np.uint8)

    def poly(points):
        img = Image.new("L", (w, h), 0)
        ImageDraw.Draw(img).polygon(points, fill=255)
        return np.array(img) > 0

    def disc(x, y, r):
        return np.hypot(xx - x, yy - y) <= r

    hull = poly([(cx, h - 6), (cx - 40, h - 34), (cx - 100, 70), (cx - 106, 34), (cx - 76, 8),
                 (cx + 76, 8), (cx + 106, 34), (cx + 100, 70), (cx + 40, h - 34)])
    _bevel_into(out, hull, ("alien_purple", "alien_purple_dark", "alien_purple_black"))
    # Panel texture on the bare hull.
    texture = hull & (((xx.astype(int) + (yy.astype(int) // 10) * 6) % 12) == 0) & ((yy.astype(int) % 10) != 0)
    out[texture] = rgba("alien_purple_black")
    rivets = hull & ((xx.astype(int) % 12) == 6) & ((yy.astype(int) % 10) == 5)
    out[rivets] = rgba("alien_purple")
    # Raised armor plates.
    plates = [
        [(cx - 70, 16), (cx - 22, 16), (cx - 22, 48), (cx - 80, 48)],
        [(cx + 70, 16), (cx + 22, 16), (cx + 22, 48), (cx + 80, 48)],
        [(cx - 94, 54), (cx - 62, 54), (cx - 44, 86), (cx - 76, 86)],
        [(cx + 94, 54), (cx + 62, 54), (cx + 44, 86), (cx + 76, 86)],
        [(cx - 16, 12), (cx + 16, 12), (cx + 16, 62), (cx - 16, 62)],
    ]
    for pl in plates:
        m = poly(pl)
        _bevel_into(out, m, ("alien_purple_hi", "alien_purple", "alien_purple_dark"))
        seam = m & ((yy.astype(int) % 8) == 0)
        out[seam] = rgba("alien_purple_dark")
    # Spine with green conduits leading to the emitter.
    spine = poly([(cx - 9, 62), (cx + 9, 62), (cx + 7, h - 30), (cx - 7, h - 30)])
    _bevel_into(out, spine, ("alien_purple", "alien_purple_dark", "alien_purple_black"))
    for y in range(66, h - 32, 5):
        out[y, int(cx) - 3:int(cx) + 5] = rgba("alien_green" if (y // 5 + frame) % 3 else "alien_green_hi")
    # Hangar bays with lit interiors: every wave launches from here.
    for side in (-1, 1):
        bay = poly([(cx + side * 26, 92), (cx + side * 56, 92), (cx + side * 50, 112), (cx + side * 32, 112)])
        out[bay] = rgba("alien_purple_black")
        inner = poly([(cx + side * 30, 96), (cx + side * 52, 96), (cx + side * 48, 108), (cx + side * 34, 108)])
        out[inner & ((yy.astype(int) % 4) == 0)] = rgba("alien_green_dark")
        for t in range(5):
            gx = int(round(cx + side * (31 + t * 5)))
            out[114, gx] = rgba("alien_green_hi" if (t + frame) % 2 == 0 else "alien_green")
            out[90, gx] = rgba("alien_green")
    # Power cores on the shoulders.
    for side in (-1, 1):
        ccx, ccy = cx + side * 46, 32
        out[disc(ccx, ccy, 8)] = rgba("alien_purple_black")
        out[disc(ccx, ccy, 7)] = rgba("alien_green_dark")
        out[disc(ccx, ccy, 5.5)] = rgba("alien_green")
        out[disc(ccx, ccy, 3.5)] = rgba("alien_green_hi")
        out[disc(ccx, ccy, 1.5)] = rgba("alien_eye")
    # Rear vents (top edge).
    for vx in range(int(cx) - 60, int(cx) + 61, 8):
        if vx in range(int(cx) - 18, int(cx) + 19):
            continue
        out[9:11, vx - 2:vx + 3] = rgba("alien_green_dark")
        out[9, vx - 1:vx + 2] = rgba("alien_green")
    # Projectile turrets: four domes with pink muzzles.
    for tx, ty in ((cx - 86, 42), (cx + 86, 42), (cx - 32, 76), (cx + 32, 76)):
        dome = disc(tx, ty, 6)
        out[disc(tx, ty, 7)] = rgba("alien_purple_black")
        _bevel_into(out, dome, ("alien_purple_hi", "alien_purple", "alien_purple_dark"))
        bx = int(round(tx))
        out[int(ty) + 3:int(ty) + 11, bx - 1:bx + 2] = rgba("alien_purple_black")
        out[int(ty) + 3:int(ty) + 10, bx] = rgba("alien_purple_dark")
        out[int(ty) + 10, bx] = rgba("danger_pink")
        out[int(ty), bx] = rgba("alien_purple_hi")
    # Missile racks on the wings.
    for side in (-1, 1):
        rack_x = cx + side * 66
        out[60:72, int(rack_x) - 10:int(rack_x) + 11] = rgba("alien_purple_black")
        for i in range(-2, 3):
            mx = int(round(rack_x + i * 4))
            out[61:71, mx] = rgba("alien_purple_dark")
            out[61, mx] = rgba("danger_pink_hi")
            out[62, mx] = rgba("danger_pink")
    # Laser emitter at the nose, flanked by two prongs.
    ey = h - 24
    for side in (-1, 1):
        prong = poly([(cx + side * 10, ey - 14), (cx + side * 16, ey - 10), (cx + side * 9, ey + 14), (cx + side * 5, ey + 12)])
        _bevel_into(out, prong, ("alien_purple_hi", "alien_purple", "alien_purple_dark"))
    out[disc(cx, ey, 11)] = rgba("alien_purple_black")
    ring = disc(cx, ey, 10) & ~disc(cx, ey, 7)
    _bevel_into(out, ring, ("alien_purple_hi", "alien_purple", "alien_purple_dark"))
    out[disc(cx, ey, 7)] = rgba("alien_purple_black")
    if laser_charge > 0:
        k = 7 * laser_charge
        out[disc(cx, ey, max(1.0, k))] = rgba("danger_red")
        out[disc(cx, ey, max(0.8, k - 2))] = rgba("danger_pink")
        out[disc(cx, ey, max(0.5, k - 4))] = rgba("danger_white")
        # Charging lights on the prongs.
        for side in (-1, 1):
            for j in range(3):
                if j < round(3 * laser_charge):
                    out[ey - 8 + j * 6, int(round(cx + side * 11))] = rgba("danger_pink_hi")
    else:
        out[disc(cx, ey, 2.5)] = rgba("danger_dark")
    # Running lights along the leading edges.
    for t in np.linspace(0.08, 0.92, 9):
        for side in (-1, 1):
            x = cx + side * (40 + t * 60)
            y = (h - 34) + t * (70 - (h - 34))
            out[int(round(y)), int(round(x))] = rgba("alien_green_hi" if frame % 2 == 0 else "alien_green")
    img = Image.fromarray(out)
    return pix.outline(img, ENEMY_OUTLINE) if outlined else img


# The laser emitter's centre, relative to the centre of the mothership sprite.
MOTHERSHIP_EMITTER = (0.0, (160 - 24 + 0.5) - 160 / 2)


# ---------------------------------------------------------------- enemy shots

def shot_infantry(frame: int = 0) -> Image.Image:
    rows = [".ppp.", "pPwPp", "pwwwp", "pPwPp", ".ppp."] if frame % 2 == 0 else \
           [".....", ".pPp.", ".PwP.", ".pPp.", "....."]
    return pix.from_grid(rows, {"p": "danger_pink", "P": "danger_pink_hi", "w": "danger_white"})


def shot_rapid() -> Image.Image:
    return pix.from_grid(["w", "r", "r", "r", "d", "d"], {"w": "danger_white", "r": "danger_red", "d": "danger_dark"})


def missile_enemy(frame: int = 0) -> Image.Image:
    rows = [
        ".r.",
        "rRr",
        "pPp",
        "pPp",
        "d.d",
        ".k." if frame % 2 == 0 else ".K.",
        ".K." if frame % 2 == 0 else "...",
    ]
    legend = {"r": "danger_red", "R": "danger_white", "p": "alien_purple", "P": "alien_purple_hi",
              "d": "alien_purple_dark", "k": "danger_pink_hi", "K": "danger_pink"}
    return pix.outline(pix.from_grid(rows, legend), ENEMY_OUTLINE)


# ---------------------------------------------------------------- friendly faction

POWERUP_ICONS = {
    "shield": ["#######", "#.....#", "#.....#", "#.....#", ".#...#.", "..#.#..", "...#..."],
    "repair": ["..###..", "..###..", "#######", "#######", "#######", "..###..", "..###.."],
    "damage": ["...#...", "..###..", ".#####.", "#######", "..###..", "..###..", "..###.."],
    "speed":  ["#..#...", "##.##..", ".##.##.", "..##.##", ".##.##.", "##.##..", "#..#..."],
}


def powerup(kind: str, frame: int = 0) -> Image.Image:
    """15x15 capsules dropped by the friendly faction. Kinds: shield, repair, damage, speed."""
    edge = "friend_hi" if frame % 2 == 0 else "friend"
    rows = [
        "..EEEEEEEEE..",
        ".EhhhhhhhhhE.",
        "EhOOOOOOOOOdE",
        "EhOOOOOOOOOdE",
        "EhOOOOOOOOOdE",
        "EhOOOOOOOOOdE",
        "EhOOOOOOOOOdE",
        "EhOOOOOOOOOdE",
        "EhOOOOOOOOOdE",
        "EhOOOOOOOOOdE",
        "EhOOOOOOOOOdE",
        ".EdddddddddE.",
        "..EEEEEEEEE..",
    ]
    img = pix.from_grid(rows, {"E": edge, "h": "friend", "O": "friend_dark", "d": "friend"})
    icon = pix.from_grid([r.replace("#", "w") for r in POWERUP_ICONS[kind]], {"w": "friend_white"})
    img.alpha_composite(icon, (3, 3))
    return pix.outline(img, "alien_purple_black")


def safe_zone(radius: int = 44, frame: int = 0) -> Image.Image:
    size = radius * 2 + 3
    img = Image.new("RGBA", (size, size), pix.CLEAR)
    d = ImageDraw.Draw(img)
    c = size // 2
    d.ellipse([c - radius, c - radius, c + radius, c + radius], fill=rgba("friend")[:3] + (16,))
    a = np.array(img)
    # Faint dithered inner band.
    yy, xx = np.mgrid[0:size, 0:size]
    rr = np.hypot(xx - c, yy - c)
    band = (rr <= radius - 1) & (rr > radius - 5) & (((xx + yy) % 2) == 0)
    a[band] = rgba("friend")[:3] + (55,)
    img = Image.fromarray(a)
    d = ImageDraw.Draw(img)
    offset = frame % 8
    steps = int(2 * math.pi * radius * 1.4)
    seen = set()
    pts = []
    for i in range(steps):
        t = 2 * math.pi * i / steps
        p = (int(round(c + radius * math.cos(t))), int(round(c + radius * math.sin(t))))
        if p not in seen:
            seen.add(p)
            pts.append(p)
    for i, p in enumerate(pts):
        if (i + offset) % 8 < 5:
            d.point(p, fill=rgba("friend_hi"))
    return img


# ---------------------------------------------------------------- asteroids

ROCK_TONES = ["rock_shadow", "rock_dark", "rock_mid", "rock_light", "rock_rim"]


def asteroid(diameter: int, seed: int, ore: int = 0) -> Image.Image:
    """A lumpy rock lit from the top left with dithered shading, craters and optional gold ore."""
    rng = pix.seeded(seed)
    size = diameter + 4
    c = (size - 1) / 2
    n = 10 + diameter // 5
    radii = [diameter / 2 * rng.uniform(0.74, 1.0) for _ in range(n)]
    radii = [(radii[i - 1] + 2 * radii[i] + radii[(i + 1) % n]) / 4 for i in range(n)]
    rot = rng.uniform(0, math.tau)
    pts = [(c + r * math.cos(rot + math.tau * i / n), c + r * math.sin(rot + math.tau * i / n))
           for i, r in enumerate(radii)]
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    mask = np.array(m) > 0
    yy, xx = np.mgrid[0:size, 0:size]
    R = diameter / 2
    nx, ny = (xx - c) / R, (yy - c) / R
    nz = np.sqrt(np.clip(1 - nx * nx - ny * ny, 0, 1))
    lx, ly, lz = -0.55, -0.62, 0.56
    light = nx * lx + ny * ly + nz * lz
    bumps = pix.value_noise(size, size, max(3, diameter // 6), seed) - 0.5
    shade = np.clip(0.45 + 0.55 * light + 0.22 * bumps, 0, 1)
    # Craters: darker bowls with a lit lower-right rim.
    for _ in range(max(1, diameter // 10)):
        r = rng.uniform(1.4, max(1.8, diameter / 8))
        ang = rng.uniform(0, math.tau)
        dist = rng.uniform(0, max(0.1, R - r - 2))
        kx, ky = c + dist * math.cos(ang), c + dist * math.sin(ang)
        rr = np.hypot(xx - kx, yy - ky)
        bowl = rr <= r
        shade = np.where(bowl, shade - 0.28 + 0.18 * np.clip(((xx - kx) + (yy - ky)) / (r * 1.4), -1, 1), shade)
        rim = (rr > r) & (rr <= r + 1.2) & ((xx - kx) + (yy - ky) > 0)
        shade = np.where(rim, shade + 0.18, shade)
    # Push values toward the tone centres so dithering only shows in thin bands between tones.
    q = shade * 3
    frac = q - np.floor(q)
    q = np.floor(q) + np.clip((frac - 0.5) * 2.6 + 0.5, 0, 1)
    level = pix.dither_levels(np.clip(q / 3, 0, 1), 4)  # 0..3 into shadow..light
    out = np.zeros((size, size, 4), dtype=np.uint8)
    for i in range(4):
        out[mask & (level == i)] = rgba(ROCK_TONES[i])
    # Rim light on the lit edge so the silhouette reads against space.
    up = np.zeros_like(mask)
    up[1:, :] = mask[:-1, :]
    left = np.zeros_like(mask)
    left[:, 1:] = mask[:, :-1]
    out[mask & (~up | ~left) & (light > 0.05)] = rgba("rock_rim")
    if ore:
        inside = np.argwhere(mask & (light > -0.2))
        for _ in range(ore):
            y, x = inside[rng.randrange(len(inside))]
            out[y, x] = rgba("ore_hi" if rng.random() < 0.3 else "ore")
            if x + 1 < size and mask[y, x + 1] and rng.random() < 0.6:
                out[y, x + 1] = rgba("ore_dark")
            if y + 1 < size and mask[y + 1, x] and rng.random() < 0.4:
                out[y + 1, x] = rgba("ore_dark")
    return Image.fromarray(out)


# ---------------------------------------------------------------- explosions and hits

EXPLOSION_TONES = {
    # Owner colours: enemy ships burst green and purple, enemy weapons pink and red,
    # your own explosives cyan and white.
    "enemy": ["alien_eye", "alien_green_hi", "alien_green", "alien_purple_hi", "alien_purple", "alien_purple_dark"],
    "danger": ["danger_white", "danger_pink_hi", "danger_pink", "danger_red", "danger_dark", "alien_purple_black"],
    "player": ["ion_white", "ion_hi", "ion", "ion_dark", "hull_mid", "hull_dark"],
}


def explosion(frame: int, palette: str = "enemy", size: int = 25, seed: int = 3) -> Image.Image:
    """Six frames: flash, fireball, bloom, break-up, smoke, embers."""
    tones = EXPLOSION_TONES[palette]
    c = (size - 1) / 2
    yy, xx = np.mgrid[0:size, 0:size]
    rr = np.hypot(xx - c, yy - c)
    noise = pix.value_noise(size, size, 3, seed + frame * 17) - 0.5
    out = np.zeros((size, size, 4), dtype=np.uint8)
    R = size / 2 - 1
    plan = [
        # (outer radius share, [(radius share, tone index)...] from outside in)
        (0.22, [(0.22, 1), (0.14, 0)]),
        (0.45, [(0.45, 2), (0.34, 1), (0.2, 0)]),
        (0.7, [(0.7, 3), (0.55, 2), (0.38, 1), (0.18, 0)]),
        (0.86, [(0.86, 4), (0.7, 3), (0.5, 2), (0.3, 1)]),
        (0.95, [(0.95, 5), (0.78, 4), (0.55, 5)]),
        (1.0, []),
    ][frame]
    for share, tone in plan[1]:
        disc = rr + noise * R * 0.45 <= share * R
        out[disc] = rgba(tones[tone])
    if frame >= 3:
        # Hollow out the middle as it breaks up.
        hole = rr + noise * R * 0.25 <= R * (0.18 + 0.14 * (frame - 3))
        out[hole] = 0
    if frame == 0:
        for ang in range(0, 360, 45):
            x = int(round(c + 0.42 * R * math.cos(math.radians(ang))))
            y = int(round(c + 0.42 * R * math.sin(math.radians(ang))))
            out[y, x] = rgba(tones[1])
    # Debris and embers flying outward.
    rng = pix.seeded(seed)
    for i in range(10):
        ang = rng.uniform(0, math.tau)
        speed = rng.uniform(0.55, 1.0)
        dist = R * min(1.0, 0.25 + speed * (frame / 5) * 1.1)
        x = int(round(c + dist * math.cos(ang)))
        y = int(round(c + dist * math.sin(ang)))
        if 0 < frame and 0 <= x < size and 0 <= y < size:
            tone = tones[min(5, 1 + frame)] if i % 3 else tones[min(5, frame)]
            out[y, x] = rgba(tone)
    return Image.fromarray(out)


def shield_hit(frame: int = 0) -> Image.Image:
    """A flash on the shield bubble where a shot lands (hit from above), fading over four frames."""
    size = 33
    c = (size - 1) / 2
    yy, xx = np.mgrid[0:size, 0:size]
    rr = np.hypot(xx - c, yy - c)
    ang = np.degrees(np.arctan2(yy - c, xx - c)) + 90  # 0 = straight up
    ang = (ang + 180) % 360 - 180
    spread = 26 + frame * 9
    r = 13 + frame * 0.5
    arc = (np.abs(rr - r) <= 0.75) & (np.abs(ang) <= spread)
    inner = (np.abs(rr - (r - 2)) <= 0.6) & (np.abs(ang) <= spread * 0.6) & (((xx + yy) % 2) == 0)
    out = np.zeros((size, size, 4), dtype=np.uint8)
    tones = ["ion_white", "ion_hi", "ion", "ion_dark"]
    near = np.abs(ang) / max(1, spread)
    for mask in (arc, inner):
        idx = np.clip((near * 2 + frame * 0.8).astype(int), 0, 3)
        for i in range(4):
            out[mask & (idx == i)] = rgba(tones[i])
    return Image.fromarray(out)


def armor_hit(frame: int = 0) -> Image.Image:
    """Grey and white sparks when a hit gets through to the armor."""
    size = 13
    rng = pix.seeded(11)
    img = Image.new("RGBA", (size, size), pix.CLEAR)
    px = img.load()
    c = size // 2
    if frame == 0:
        for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
            px[c + dx, c + dy] = rgba("hull_outline")
    for _ in range(7):
        ang = rng.uniform(0, math.tau)
        rr = 1.5 + frame * 1.6 + rng.uniform(0, 1.5)
        x, y = int(round(c + rr * math.cos(ang))), int(round(c + rr * math.sin(ang)))
        if 0 <= x < size and 0 <= y < size:
            px[x, y] = rgba(rng.choice(["hull_outline", "hull_hi", "hull_light"]) if frame < 2 else "hull_mid")
    return img


# ---------------------------------------------------------------- warnings

def ram_warning(length: int, frame: int = 0) -> Image.Image:
    """A guard's dash path: a flashing dashed lane with chevrons, pointing up."""
    w = 9
    img = Image.new("RGBA", (w, length), pix.CLEAR)
    d = ImageDraw.Draw(img)
    col = rgba("danger_red" if frame % 2 == 0 else "danger_pink")
    pix.dashed_line(d, (0, length - 1), (0, 0), col, dash=4, gap=3)
    pix.dashed_line(d, (w - 1, length - 1), (w - 1, 0), col, dash=4, gap=3)
    for y in range(4 + (frame % 2) * 3, length - 4, 10):
        for i in range(4):
            d.point((4 - i, y + i), fill=col)
            d.point((4 + i, y + i), fill=col)
    return img


def laser_warning(length: int, frame: int = 0, locked: bool = False) -> Image.Image:
    """The mothership's laser telegraph, pointing down, marking the beam's width.

    While the mothership is still turning to track you, the edges are dashed and dim. Once the
    laser locks, the lane stops moving, its edges go solid and it flashes hard.
    """
    w = 25
    img = Image.new("RGBA", (w, length), pix.CLEAR)
    d = ImageDraw.Draw(img)
    on = frame % 2 == 0
    if locked:
        col = rgba("danger_pink_hi" if on else "danger_red")
        d.line([(0, 0), (0, length - 1)], fill=col)
        d.line([(w - 1, 0), (w - 1, length - 1)], fill=col)
        d.rectangle([1, 0, w - 2, length - 1], fill=rgba("danger_red")[:3] + (70 if on else 35,))
        mark_col = rgba("danger_white" if on else "danger_pink_hi")
    else:
        col = rgba("danger_red")
        pix.dashed_line(d, (0, 0), (0, length - 1), col, dash=5, gap=4)
        pix.dashed_line(d, (w - 1, 0), (w - 1, length - 1), col, dash=5, gap=4)
        mark_col = rgba("danger_pink")
    for y in range(6, length, 24):
        mark = [(12, y), (11, y + 1), (13, y + 1), (12, y + 2), (12, y + 3), (12, y + 5)]
        for p in mark:
            d.point(p, fill=mark_col)
    return img


def laser_beam(length: int, frame: int = 0) -> Image.Image:
    """The mothership's laser itself, pointing down."""
    w = 25
    img = Image.new("RGBA", (w, length), pix.CLEAR)
    d = ImageDraw.Draw(img)
    j = frame % 2
    d.rectangle([0 + j, 0, w - 1 - j, length - 1], fill=rgba("danger_dark"))
    d.rectangle([2, 0, w - 3, length - 1], fill=rgba("danger_red"))
    d.rectangle([5, 0, w - 6, length - 1], fill=rgba("danger_pink"))
    d.rectangle([8, 0, w - 9, length - 1], fill=rgba("danger_pink_hi"))
    d.rectangle([10, 0, w - 11, length - 1], fill=rgba("danger_white"))
    a = np.array(img)
    rng = pix.seeded(frame)
    for _ in range(length // 6):
        y = rng.randrange(length)
        a[y, rng.choice([0, 1, w - 2, w - 1])] = rgba("danger_pink")
    return Image.fromarray(a)
