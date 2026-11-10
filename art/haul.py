"""Sprint 9 art: hauling. The lasso's tow beam and the collector ring.

- The lasso: a force beam of fixed length from the back of your ship to the asteroid it holds, in
  two looks (a steady beam, or a chain of energy links), thicker at each of its 3 levels. A grip
  ring locks round the rock, and brackets show which rock you'd grab (or that it's too heavy).
- Thrown rocks trail speed lines while they're fast enough to hurt.
- The collector ring: a big hoop in home base's style. Four mounts on the outside for sentries
  (top, right, bottom, left), four collector nodes on the inside that light gold as drills sell,
  a holding field round the inside, and battle damage as its health drops.

Same colour jobs as the rest of the art: drab grey hardware with a light outline, cyan light,
gold for ore. Sizes here are the art's; how far the beam reaches and how much the ring holds
live in the data files.
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from . import items as I, pix, pixfont, sprites as S
from .palette import rgba

OUTLINE = I.OUTLINE

# ---------------------------------------------------------------- the collector ring

R_IN, R_OUT = 130, 140              # the hoop's band, in game pixels from its centre
PAD_R = R_OUT + 7                   # sentry mounts sit just outside the band
PAD_HALF = 7                        # 15x15 mount pads
NODE_R = R_IN - 4                   # collector nodes sit just inside it
FIELD_R = R_IN - 10                 # the holding field
MARGIN = 10
RING_SIZE = 2 * (PAD_R + PAD_HALF + MARGIN) + 1
MOUNT_ANGLES = (-90, 0, 90, 180)    # screen degrees (0 = right, 90 = down): top, right, bottom, left
NODE_ANGLES = (-45, 45, 135, 225)
SLOT_R = 70                         # where held rocks settle, on the diagonals (four 96 px rocks fit)


def _polar(c: float, r: float, deg: float) -> tuple[float, float]:
    a = math.radians(deg)
    return c + r * math.cos(a), c + r * math.sin(a)


def ring_centre() -> float:
    return (RING_SIZE - 1) / 2


def mount_point(centre: tuple[float, float], i: int) -> tuple[float, float]:
    """Where mount i (0 top, 1 right, 2 bottom, 3 left) sits on screen for a ring centred at `centre`."""
    a = math.radians(MOUNT_ANGLES[i])
    return centre[0] + PAD_R * math.cos(a), centre[1] + PAD_R * math.sin(a)


def node_point(centre: tuple[float, float], i: int) -> tuple[float, float]:
    a = math.radians(NODE_ANGLES[i])
    return centre[0] + NODE_R * math.cos(a), centre[1] + NODE_R * math.sin(a)


def slot_point(centre: tuple[float, float], i: int) -> tuple[float, float]:
    a = math.radians(NODE_ANGLES[i])
    return centre[0] + SLOT_R * math.cos(a), centre[1] + SLOT_R * math.sin(a)


def collector_ring(frame: int = 0, health: float = 1.0, lit_nodes: tuple[int, ...] = (), seed: int = 3) -> Image.Image:
    """The ring itself, without its field. `health` below 1 scorches and breaks panels; nodes in
    `lit_nodes` glow gold (a drill has just sold into them)."""
    s = RING_SIZE
    c = ring_centre()
    yy, xx = np.mgrid[0:s, 0:s]
    r = np.hypot(xx - c, yy - c)
    ang = (np.degrees(np.arctan2(yy - c, xx - c)) + 360) % 360
    band = (r >= R_IN) & (r <= R_OUT)
    lip = (r >= R_OUT - 2) & (r <= R_OUT) & band          # a raised outer lip, like the base's ring
    pads = np.zeros_like(band)
    stems = np.zeros_like(band)
    pad_centres = []
    for deg in MOUNT_ANGLES:
        px_, py_ = _polar(c, PAD_R, deg)
        pad_centres.append((px_, py_))
        pads |= (np.abs(xx - px_) <= PAD_HALF) & (np.abs(yy - py_) <= PAD_HALF)
        # A short strut tying the pad to the band.
        a = math.radians(deg)
        along = (xx - c) * math.cos(a) + (yy - c) * math.sin(a)
        across = -(xx - c) * math.sin(a) + (yy - c) * math.cos(a)
        stems |= (np.abs(across) <= 3.5) & (along >= R_OUT - 1) & (along <= PAD_R)
    nodes = np.zeros_like(band)
    node_centres = []
    for deg in NODE_ANGLES:
        nx_, ny_ = _polar(c, NODE_R, deg)
        node_centres.append((nx_, ny_))
        nodes |= np.hypot(xx - nx_, yy - ny_) <= 4.2
    out = np.zeros((s, s, 4), dtype=np.uint8)
    for mask, tones in ((stems & ~pads, ("hull_mid", "hull_dark", "hull_black")),
                        (band, ("hull_light", "hull_mid", "hull_dark")),
                        (lip, ("hull_hi", "hull_light", "hull_mid")),
                        (nodes, ("hull_light", "hull_mid", "hull_dark")),
                        (pads, ("hull_mid", "hull_dark", "hull_black"))):
        shaded = pix.bevel(mask, *tones)
        out[mask] = shaded[mask]
    # Panel seams every 10 degrees across the band, skipping the pads' struts.
    for deg in range(5, 360, 10):
        for rr in range(R_IN + 1, R_OUT - 2):
            x, y = (int(round(v)) for v in _polar(c, rr, deg))
            if band[y, x] and not stems[y, x]:
                out[y, x] = rgba("hull_dark")
    # Running lights round the lip: every 30 degrees, chasing with the frame.
    for i, deg in enumerate(range(15, 360, 30)):
        x, y = (int(round(v)) for v in _polar(c, R_OUT - 1, deg))
        on = (i + frame) % 3 == 0
        out[y, x] = rgba("ion_hi" if on else "ion_dark")
    # Battle damage: broken panels turn black with jagged edges, worst first, plus scorch marks.
    if health < 1.0:
        rng = np.random.default_rng(seed)
        segs = list(range(36))
        rng.shuffle(segs)
        broken = segs[:int(round((1.0 - health) * 14))]
        noise = pix.value_noise(s, s, 3, seed)
        for k, seg in enumerate(broken):
            lo, hi = seg * 10 + 1, seg * 10 + 9
            within = (ang >= lo) & (ang <= hi) & band & ~stems
            hole = within & (noise > 0.45 - 0.1 * (k % 3))
            out[hole] = rgba("hull_black")
            edge = within & ~hole & (noise > 0.32)
            out[edge] = rgba("rock_dark")
    # Node lights: cyan when idle, gold when a drill has just sold into them.
    for i, (nx_, ny_) in enumerate(node_centres):
        m = np.hypot(xx - nx_, yy - ny_) <= 1.6
        out[m] = rgba("ore_hi" if i in lit_nodes else "ion")
    img = Image.fromarray(out)
    d = ImageDraw.Draw(img)
    lit = "ion_hi" if frame % 2 == 0 else "ion"
    for px_, py_ in pad_centres:
        d.rectangle([px_ - 3, py_ - 3, px_ + 3, py_ + 3], fill=rgba("hull_black"))    # the turret socket
        for ox_, oy_ in ((-5, -5), (5, -5), (-5, 5), (5, 5)):
            d.point((round(px_ + ox_), round(py_ + oy_)), fill=rgba(lit))
    return pix.outline(img, "hull_outline")


def ring_field(frame: int = 0, alpha: float = 1.0) -> Image.Image:
    """The faint holding field just inside the ring. Its dashes creep round with the frame."""
    s = RING_SIZE
    c = ring_centre()
    img = Image.new("RGBA", (s, s), pix.CLEAR)
    d = ImageDraw.Draw(img)
    dashed_circle(d, c, c, FIELD_R, rgba("ion_dark"), 3, 5, phase=frame)
    dashed_circle(d, c, c, FIELD_R - 3, rgba("console_edge"), 1, 9, phase=-frame)
    if alpha < 1:
        a = np.array(img)
        a[:, :, 3] = (a[:, :, 3] * alpha).astype(np.uint8)
        img = Image.fromarray(a)
    return img


def rock_hold(diameter: int, frame: int = 0) -> Image.Image:
    """The small field the ring wraps round each rock it holds: four short arcs."""
    rad = diameter / 2 + 3
    size = int(rad * 2) + 5
    img = Image.new("RGBA", (size, size), pix.CLEAR)
    d = ImageDraw.Draw(img)
    c = (size - 1) / 2
    for q in range(4):
        start = q * 90 + 20 + frame * 6
        for deg in range(start, start + 30, 2):
            x, y = _polar(c, rad, deg)
            d.point((round(x), round(y)), fill=rgba("ion_dark"))
    return img


def placement_ghost(ok: bool, frame: int = 0) -> Image.Image:
    """Where the ring will go when you place it: a dashed outline with its four mounts. Cyan when
    there's room, pink when rocks are in the way."""
    s = RING_SIZE
    c = ring_centre()
    img = Image.new("RGBA", (s, s), pix.CLEAR)
    d = ImageDraw.Draw(img)
    tone = rgba("ion" if ok else "danger_pink")
    dashed_circle(d, c, c, R_OUT, tone, 4, 4, phase=frame)
    dashed_circle(d, c, c, R_IN, tone, 4, 4, phase=-frame)
    for deg in MOUNT_ANGLES:
        px_, py_ = _polar(c, PAD_R, deg)
        d.rectangle([px_ - PAD_HALF, py_ - PAD_HALF, px_ + PAD_HALF, py_ + PAD_HALF], outline=tone)
    return img


def dashed_circle(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, color, dash: int, gap: int,
                  phase: int = 0) -> None:
    steps = max(16, int(2 * math.pi * r * 1.5))
    seen, pts = set(), []
    for i in range(steps):
        t = 2 * math.pi * i / steps
        p = (int(round(cx + r * math.cos(t))), int(round(cy + r * math.sin(t))))
        if p not in seen:
            seen.add(p)
            pts.append(p)
    period = dash + gap
    for i, p in enumerate(pts):
        if (i + phase) % period < dash:
            d.point(p, fill=color)


def mounted_turret(scene: pix.Scene, centre: tuple[float, float], i: int, kind: str, aim: float,
                   firing: bool = False) -> tuple[float, float]:
    """Draw a sentry's turret on mount i of a ring centred at `centre`. No platform and no health bar
    of its own: it's part of the ring."""
    x, y = mount_point(centre, i)
    scene.blit_smooth(I.turret_interior(kind, firing, loaded=3), x, y, angle=aim, outline=OUTLINE)
    return x, y


def ring_sprite(frame: int = 0, health: float = 1.0, lit_nodes: tuple[int, ...] = (),
                turrets: dict[int, tuple[str, float]] | None = None) -> Image.Image:
    """Ring and mounted turrets flattened into one sprite (for breaking it apart)."""
    base = collector_ring(frame, health, lit_nodes)
    out = base.copy()
    c = ring_centre()
    for i, (kind, aim) in (turrets or {}).items():
        x, y = mount_point((c, c), i)
        t = S._finish(I.turret_interior(kind, False, loaded=3), OUTLINE, aim)
        out.alpha_composite(t, (int(round(x - t.width / 2)), int(round(y - t.height / 2))))
    return out


# ---------------------------------------------------------------- the lasso

BEAM_LEVEL_WIDTH = {1: 1, 2: 2, 3: 3}


def draw_tow_beam(scene: pix.Scene, p0: tuple[float, float], p1: tuple[float, float], frame: int,
                  style: str = "A", level: int = 1, fade: float = 1.0) -> None:
    """The force beam from your ship (p0) to the rock (p1), drawn on the pixel grid so it glows.

    A, a steady beam: a dark cyan sheath, a bright core, and pulses running down it toward the
    ship (it's pulling). Thicker at each level.
    B, an energy chain: separate glowing links, like a rope of light. Bigger links at each level.
    """
    d = scene.draw()
    x0, y0 = p0
    x1, y1 = p1
    length = math.hypot(x1 - x0, y1 - y0)
    if length < 1:
        return
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    nx, ny = -uy, ux
    w = BEAM_LEVEL_WIDTH[level]
    dim = fade < 0.5
    if style == "A":
        sheath = rgba("ion_dark")
        core = rgba("ion" if dim else "ion_hi")
        for off in range(-w, w + 1):
            if abs(off) == w:
                tone = sheath
            else:
                tone = core if off == 0 or w >= 3 and abs(off) == 1 else rgba("ion")
            d.line([(x0 + nx * off * 0.5, y0 + ny * off * 0.5), (x1 + nx * off * 0.5, y1 + ny * off * 0.5)], fill=tone)
        if not dim:
            # Pulses running from the rock to the ship.
            gap = 14
            for k in range(int(length // gap) + 1):
                t = length - ((k * gap + frame * 4) % length)
                px_, py_ = x0 + ux * t, y0 + uy * t
                d.point((round(px_), round(py_)), fill=rgba("ion_white"))
                if w >= 2:
                    d.point((round(px_ + nx), round(py_ + ny)), fill=rgba("ion_hi"))
    else:
        gap = 4 + w
        n = int(length // gap)
        for k in range(n + 1):
            t = (k * gap + (frame * 2) % gap)
            if t > length:
                break
            cx, cy = x0 + ux * t, y0 + uy * t
            bright = (k + frame) % 3 == 0 and not dim
            tone = rgba("ion_hi" if bright else ("ion_dark" if dim else "ion"))
            rad = w
            # A small diamond link, set across the beam.
            d.line([(cx + nx * rad, cy + ny * rad), (cx - nx * rad, cy - ny * rad)], fill=tone)
            d.line([(cx + ux * rad * 0.7, cy + uy * rad * 0.7), (cx - ux * rad * 0.7, cy - uy * rad * 0.7)], fill=tone)
            if w >= 2:
                for sx in (1, -1):
                    d.point((round(cx + nx * sx * (rad - 1) + ux * 0.5), round(cy + ny * sx * (rad - 1) + uy * 0.5)),
                            fill=rgba("ion_dark"))
    # Emitter spark at the ship's end.
    d.point((round(x0), round(y0)), fill=rgba("ion_white" if not dim else "ion"))


def grip(diameter: int, frame: int = 0, closing: float = 1.0) -> Image.Image:
    """The grip ring that locks round a towed rock. `closing` from 0 to 1 shrinks it onto the rock as
    the beam latches."""
    rad = diameter / 2 + 2 + (1 - closing) * 10
    size = int(rad * 2) + 5
    img = Image.new("RGBA", (size, size), pix.CLEAR)
    d = ImageDraw.Draw(img)
    c = (size - 1) / 2
    dashed_circle(d, c, c, rad, rgba("ion" if closing >= 1 else "ion_hi"), 3, 3, phase=frame)
    return img


def target_brackets(diameter: int, ok: bool = True, frame: int = 0) -> Image.Image:
    """Corner brackets round the rock the lasso would grab. Dim grey when it's too heavy for your level."""
    half = diameter // 2 + 4 + (frame % 2)
    size = half * 2 + 1
    img = Image.new("RGBA", (size, size), pix.CLEAR)
    d = ImageDraw.Draw(img)
    tone = rgba("ion_hi" if ok else "hud_dim")
    arm = max(3, diameter // 6)
    e = size - 1
    for (x, y, sx, sy) in ((0, 0, 1, 1), (e, 0, -1, 1), (0, e, 1, -1), (e, e, -1, -1)):
        d.line([(x, y), (x + sx * arm, y)], fill=tone)
        d.line([(x, y), (x, y + sy * arm)], fill=tone)
    return img


def speed_lines(scene: pix.Scene, pos: tuple[float, float], vel: tuple[float, float], diameter: int,
                strength: float = 1.0) -> None:
    """Pale streaks behind a thrown rock while it's moving fast enough to hurt."""
    sp = math.hypot(*vel)
    if sp < 1e-6 or strength <= 0:
        return
    ux, uy = vel[0] / sp, vel[1] / sp
    nx, ny = -uy, ux
    d = scene.draw()
    rad = diameter / 2
    length = 6 + 14 * strength
    for off, tone in ((-0.55, "rock_rim"), (0.0, "star_mid"), (0.55, "rock_rim")):
        sx = pos[0] - ux * (rad + 1) + nx * off * rad
        sy = pos[1] - uy * (rad + 1) + ny * off * rad
        ln = length * (1.0 if off == 0 else 0.7)
        d.line([(sx, sy), (sx - ux * ln, sy - uy * ln)], fill=rgba(tone))


def gold_pulse(scene: pix.Scene, p0: tuple[float, float], p1: tuple[float, float], t: float) -> None:
    """A spark of gold flying from a drill (p0) to a collector node (p1), `t` from 0 to 1."""
    d = scene.draw()
    tones = ("ore_hi", "ore", "ore", "ore_dark", "ore_dark")
    for k, tone in enumerate(tones):
        tt = t - k * 0.04
        if 0 <= tt <= 1:
            # A slight arc so it reads as flying, not a straight beam.
            mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2 - 10
            x = (1 - tt) ** 2 * p0[0] + 2 * (1 - tt) * tt * mx + tt ** 2 * p1[0]
            y = (1 - tt) ** 2 * p0[1] + 2 * (1 - tt) * tt * my + tt ** 2 * p1[1]
            d.point((round(x), round(y)), fill=rgba(tone))


def credit_pop(amount: int) -> Image.Image:
    return pixfont.render(f"+{amount} CR", "ore")


# ---------------------------------------------------------------- shop icons (13x13)

LASSO_ICON = [
    "...........hh",
    "..........hwh",
    ".........jhh.",
    "........j....",
    ".......i.....",
    "......j......",
    ".....i.......",
    "..rrj........",
    ".rRRrr.......",
    "rRRrrrq......",
    "rRrrrqq......",
    ".rrrqqq......",
    "..qqqq.......",
]
RING_ICON = [
    "......l......",
    "....mmLmm....",
    "...m.....m...",
    "..m.......m..",
    ".m..r..i...m.",
    ".m.rrr.....m.",
    "lL.rrr....iLl",
    ".m.....rr..m.",
    ".m..i.rrr..m.",
    "..m....r..m..",
    "...m.....m...",
    "....mmLmm....",
    "......l......",
]
ICON_LEGEND = {"w": "ion_white", "h": "ion_hi", "i": "ion", "j": "ion_dark",
               "L": "hull_hi", "l": "hull_light", "m": "hull_mid", "d": "hull_dark",
               "R": "rock_rim", "r": "rock_light", "q": "rock_mid", "O": "ore"}


def icon(kind: str) -> Image.Image:
    return pix.from_grid({"lasso": LASSO_ICON, "ring": RING_ICON}[kind], ICON_LEGEND)
