"""Sprint 6 art: things you own and use out in the field.

- Drills with a gold fill bar down their middle, and the asteroids they crack and crumble
- Sentries in three kinds (auto cannon, sniper, missile) and three tiers, and their shots
- Explosive mines and their blast
- Your ship's extras: missiles loaded on the pods, the boost flame at each level, the shield at
  each level and the laser charge-up

Same colour jobs as the rest of the art: drab grey hardware with a light outline, cyan light,
gold for ore. Nothing here is gameplay; sizes and timings that matter live in the data files.
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from . import effects as E, pix, sprites as S
from .palette import rgba

OUTLINE = "hull_outline"


# ---------------------------------------------------------------- drills

DRILL_ROWS = pix.mirror([
    ".....i",
    "....dh",
    "...dmm",
    "..dfTT",
    "..dfTT",
    ".dmfTT",
    ".dmfTT",
    "..dfTT",
    "..dfTT",
    "..dfTT",
    "..dfTT",
    ".ddmmm",
    ".d..dl",
    "d....l",
    "d....n",
])
TUBE_TOP, TUBE_ROWS = 3, 8          # the gold bar fills these rows, from the bottom up
TUBE_COLS = (4, 5, 6)


def drill_interior(fill: float = 0.0, frame: int = 0) -> Image.Image:
    """The drill without its outline. `fill` 0 to 1 is how full its hold is.

    The bar down its middle lights up gold from the bottom. While it works, the tip light
    blinks cyan. Once it's full it stops: the tip light turns gold and the bar pulses.
    """
    full = fill >= 0.999
    status = "ore_hi" if full else ("ion_hi" if frame % 2 == 0 else "ion_dark")
    legend = {"d": "hull_dark", "m": "hull_mid", "l": "hull_light", "h": "hull_hi", "n": "hull_black",
              "f": "hull_light", "T": "hull_black", "i": status}
    img = pix.from_grid(DRILL_ROWS, legend)
    px = img.load()
    for y in range(TUBE_TOP, TUBE_TOP + TUBE_ROWS):     # right-hand side of the tube frame in shade
        px[7, y] = rgba("hull_mid")
    lit = 0 if fill <= 0 else max(1, int(round(fill * TUBE_ROWS)))
    for j in range(lit):
        y = TUBE_TOP + TUBE_ROWS - 1 - j
        if full and frame % 2 == 1:
            tones = ("ore_hi", "ore_hi", "ore_hi")
        elif j == lit - 1:
            tones = ("ore_hi", "ore_hi", "ore")          # the bright top edge of the gold
        else:
            tones = ("ore_hi", "ore", "ore_dark")
        for x, t in zip(TUBE_COLS, tones):
            px[x, y] = rgba(t)
    return img


def drill(fill: float = 0.0, frame: int = 0, angle: float = 0.0) -> Image.Image:
    return S._finish(drill_interior(fill, frame), OUTLINE, angle)


def struct_bar(width: int, health: float) -> Image.Image:
    """Health over your own hardware (drills, sentries): cyan, turning pink when it's nearly gone."""
    img = Image.new("RGBA", (width, 4), rgba("console_black"))
    d = ImageDraw.Draw(img)
    d.rectangle([1, 1, width - 2, 2], fill=rgba("console_mid"))
    n = int(round((width - 2) * max(0.0, min(1.0, health))))
    if n:
        low = health < 0.3
        d.line([(1, 1), (n, 1)], fill=rgba("danger_pink_hi" if low else "ion_hi"))
        d.line([(1, 2), (n, 2)], fill=rgba("danger_pink" if low else "ion"))
    return img


# ---------------------------------------------------------------- asteroids running dry

CRACK_SHOW = (0.0, 0.34, 0.68, 1.0)        # share of each crack shown at stages 0 to 3
ORE_KEEP = (1.0, 0.6, 0.3, 0.08)           # share of the gold flecks still showing


def rim_point(rock: Image.Image, angle_deg: float) -> tuple[int, int]:
    """The outermost solid pixel of a rock along a direction (0 = up, clockwise)."""
    a = np.array(rock)[:, :, 3] > 0
    h, w = a.shape
    cx, cy = (w - 1) / 2, (h - 1) / 2
    ux, uy = math.sin(math.radians(angle_deg)), -math.cos(math.radians(angle_deg))
    last = (int(round(cx)), int(round(cy)))
    r = 0.0
    while True:
        x, y = int(round(cx + ux * r)), int(round(cy + uy * r))
        if not (0 <= x < w and 0 <= y < h):
            break
        if a[y, x]:
            last = (x, y)
        r += 0.5
    return last


def _walk(mask, x, y, ang, length, rng, depth, t0, out, branch_p):
    """A crack running from (x, y) in short straight runs with sharp kinks, like split stone.
    Records (x, y, t, depth) with t the distance from its source."""
    h, w = mask.shape
    want = ang
    t = t0
    travelled = 0.0
    while travelled < length:
        run = rng.uniform(3, 7)
        ang = want + rng.uniform(-0.65, 0.65)
        for _ in range(int(run)):
            x += math.cos(ang)
            y += math.sin(ang)
            xi, yi = int(round(x)), int(round(y))
            if not (0 <= xi < w and 0 <= yi < h) or not mask[yi, xi]:
                return
            t += 1
            travelled += 1
            out.append((xi, yi, t, depth))
        if depth < 1 and travelled > 4 and rng.random() < branch_p:
            side = rng.choice((-1, 1))
            _walk(mask, x, y, want + side * rng.uniform(0.7, 1.2), length * rng.uniform(0.25, 0.45), rng,
                  depth + 1, t, out, 0.0)


def crack_points(rock: Image.Image, sites: list[tuple[int, int]], seed: int) -> list[tuple[int, int, float, int]]:
    """Every crack pixel as (x, y, share, depth), where share 0 to 1 says when it appears."""
    a = np.array(rock)[:, :, 3] > 0
    h, w = a.shape
    cx, cy = (w - 1) / 2, (h - 1) / 2
    rng = pix.seeded(seed)
    pts: list = []
    for sx, sy in sites:
        base = math.atan2(cy - sy, cx - sx)
        n_main = 2 if w >= 40 else 1
        for i in range(n_main):
            ang = base + (i - (n_main - 1) / 2) * 0.7 + rng.uniform(-0.15, 0.15)
            _walk(a, sx, sy, ang, w * rng.uniform(0.7, 0.95), rng, 0, 0, pts, 0.25)
    if not pts:
        return []
    tmax = max(p[2] for p in pts)
    # A few hairlines from the rim join in late, so the whole rock looks tired, not just the drill site.
    late: list = []
    for _ in range(max(1, w // 32)):
        ang = rng.uniform(0, 360)
        rx, ry = rim_point(rock, ang)
        _walk(a, rx, ry, math.atan2(cy - ry, cx - rx) + rng.uniform(-0.4, 0.4), w * 0.35, rng, 2, 0, late, 0.0)
    out = [(x, y, t / tmax, d) for x, y, t, d in pts]
    out += [(x, y, 0.55 + 0.45 * min(1.0, t / max(1, w * 0.35)), 2) for x, y, t, d in late]
    return out


def crack_overlay(rock: Image.Image, cracks, stage: int) -> Image.Image:
    """Dark cracks with a lit lower edge, drawn over a rock. Stage 0 (full) has none."""
    a = np.array(rock)
    solid = a[:, :, 3] > 0
    h, w = solid.shape
    out = np.zeros_like(a)
    show = CRACK_SHOW[stage]
    if show <= 0:
        return Image.fromarray(out)
    hit = np.zeros((h, w), dtype=bool)
    for x, y, s, d in cracks:
        if s <= show:
            hit[y, x] = True
            if stage == 3 and d == 0 and s < 0.7 and x + 1 < w and solid[y, x + 1]:
                hit[y, x + 1] = True        # the main cracks open up at the last stage
    lit = np.zeros_like(hit)
    lit[1:, 1:] = hit[:-1, :-1]
    lit &= solid & ~hit
    out[lit] = rgba("rock_light")
    out[hit] = rgba("rock_shadow")
    return Image.fromarray(out)


def drained_rock(diameter: int, seed: int, ore: int, stage: int) -> Image.Image:
    """The rock with some of its gold flecks gone (they fade as the ore runs out)."""
    rich = np.array(S.asteroid(diameter, seed, ore))
    bare = np.array(S.asteroid(diameter, seed, 0))
    diff = np.argwhere(np.any(rich != bare, axis=2))
    rng = pix.seeded(seed + 7)
    order = list(range(len(diff)))
    rng.shuffle(order)
    keep = set(order[:int(round(len(order) * ORE_KEEP[stage]))])
    out = bare.copy()
    for i, (y, x) in enumerate(diff):
        if i in keep:
            out[y, x] = rich[y, x]
    return Image.fromarray(out)


def shatter(img: Image.Image, frames: int, pieces: int, seed: int, speed: float = 1.0,
            start: int = 0) -> list[Image.Image]:
    """Break a sprite into chunks that drift apart and crumble into dust.

    Returns `frames` images on a larger canvas, centred on the original's centre.
    """
    a = np.array(img)
    h, w = a.shape[:2]
    solid = a[:, :, 3] > 0
    pts = np.argwhere(solid)
    rng = np.random.default_rng(seed)
    seeds = pts[rng.choice(len(pts), size=min(pieces, len(pts)), replace=False)].astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    jag = (pix.value_noise(w, h, 3, seed) - 0.5) * 5
    dist = np.stack([np.hypot(yy - sy, xx - sx) + jag * (1 if i % 2 else -1) for i, (sy, sx) in enumerate(seeds)])
    label = np.argmin(dist, axis=0)
    cy, cx = pts.mean(axis=0)
    # Each chunk wears away from its edges inward, so it shrinks instead of turning to static.
    depth = np.zeros((h, w), dtype=np.float32)
    deepest = np.ones((h, w), dtype=np.float32)
    for i in range(len(seeds)):
        m = solid & (label == i)
        step = 0
        cells = m.copy()
        while m.any():
            inner = m.copy()
            inner[1:, :] &= m[:-1, :]
            inner[:-1, :] &= m[1:, :]
            inner[:, 1:] &= m[:, :-1]
            inner[:, :-1] &= m[:, 1:]
            depth[m & ~inner] = step
            m = inner
            step += 1
        deepest[cells] = max(1, step)
    order = np.clip(depth / deepest + (pix.value_noise(w, h, 2, seed + 1) - 0.5) * 0.25, 0, 1)
    m = int(max(w, h) * 0.55 * speed) + 6
    W, H = w + 2 * m, h + 2 * m
    vel = []
    for i, (sy, sx) in enumerate(seeds):
        sel = solid & (label == i)
        if not sel.any():
            vel.append((0.0, 0.0))
            continue
        py, px = np.argwhere(sel).mean(axis=0)
        dx, dy = px - cx, py - cy
        n = math.hypot(dx, dy) or 1.0
        sp = speed * rng.uniform(0.7, 1.3) * (0.6 + 0.4 * min(1.0, n / (w / 3)))
        vel.append((dx / n * sp + rng.uniform(-0.2, 0.2), dy / n * sp + rng.uniform(-0.2, 0.2)))
    dust_tones = [rgba("rock_light"), rgba("rock_mid"), rgba("rock_dark")]
    out = []
    for f in range(frames):
        canvas = np.zeros((H, W, 4), dtype=np.uint8)
        g = max(0, f - start)
        gone = float(np.clip((g - 1.5) / max(1, frames - start - 2.5), 0, 1)) ** 1.6 if g > 1 else 0.0
        for i in range(len(seeds)):
            vx, vy = vel[i]
            ox, oy = vx * g ** 1.25, vy * g ** 1.25
            sel = solid & (label == i)
            keep = sel & (order >= gone)
            ys, xs = np.nonzero(keep)
            tx, ty = np.round(xs + ox + m).astype(int), np.round(ys + oy + m).astype(int)
            ok = (tx >= 0) & (tx < W) & (ty >= 0) & (ty < H)
            canvas[ty[ok], tx[ok]] = a[ys[ok], xs[ok]]
            # Dust: the pixels that just crumbled, thrown a little further out.
            dust = sel & (order < gone) & (order >= gone - 0.25) & ((xx * 7 + yy * 13) % 7 == 0)
            ys, xs = np.nonzero(dust)
            k = 1.35 + 0.2 * (f % 2)
            tx, ty = np.round(xs + ox * k + m).astype(int), np.round(ys + oy * k + m).astype(int)
            ok = (tx >= 0) & (tx < W) & (ty >= 0) & (ty < H)
            tone = dust_tones[min(2, int(gone * 3))]
            canvas[ty[ok], tx[ok]] = tone
        out.append(Image.fromarray(canvas))
    return out


# ---------------------------------------------------------------- sentries

SENTRY_KINDS = ("auto", "sniper", "missile")
SENTRY_NAMES = {"auto": "AUTO CANNON", "sniper": "SNIPER", "missile": "MISSILE"}
_BASE_SIZE = {1: 13, 2: 15, 3: 17}
TURRET_CANVAS = (11, 21)                    # turrets turn about the centre of this canvas


def sentry_base(tier: int = 1, frame: int = 0) -> Image.Image:
    """The fixed platform a sentry turret sits on, darker than the turret so the turret reads.
    Bigger and more armored at each tier, with one light per tier along its front edge."""
    s = _BASE_SIZE[tier]
    c = (s - 1) / 2
    yy, xx = np.mgrid[0:s, 0:s]
    cut = 3 + (tier - 1)
    octagon = (np.abs(xx - c) + np.abs(yy - c)) <= 2 * c - cut + 0.5
    out = np.zeros((s, s, 4), dtype=np.uint8)
    plate = pix.bevel(octagon, "hull_mid", "hull_dark", "hull_black")
    out[octagon] = plate[octagon]
    if tier >= 2:
        # Armor blocks on the four diagonal faces.
        for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            bx, by = c + sx * (c - cut / 2 - 0.5), c + sy * (c - cut / 2 - 0.5)
            blk = (np.abs(xx - bx) <= 1) & (np.abs(yy - by) <= 1) & octagon
            sh = pix.bevel(blk, "hull_light", "hull_mid", "hull_dark")
            out[blk] = sh[blk]
    if tier >= 3:
        # A riveted outer band.
        band = octagon & ((np.abs(xx - c) + np.abs(yy - c)) >= 2 * c - cut - 1.5)
        out[band & ((xx + yy) % 3 == 0)] = rgba("hull_light")
    r = np.hypot(xx - c, yy - c)
    out[r <= 4.2] = rgba("hull_black")       # the turret ring
    lit = "ion_hi" if frame % 2 == 0 else "ion"
    for i in range(tier):
        x = int(round(c + (i - (tier - 1) / 2) * 3))
        out[s - 2, x] = rgba(lit)
    return pix.outline(Image.fromarray(out), OUTLINE)


def turret_interior(kind: str, firing: bool = False, loaded: int = 4) -> Image.Image:
    """A sentry's turret without its outline, facing up, on an 11x21 canvas that turns about its
    centre. Twin short barrels for the auto cannon, one long barrel for the sniper, and two
    launcher pods for the missile sentry."""
    w, h = TURRET_CANVAS
    cx, cy = w // 2, h // 2
    yy, xx = np.mgrid[0:h, 0:w]
    out = np.zeros((h, w, 4), dtype=np.uint8)
    tip = "ion_white" if firing else "hull_hi"

    def put(mask, tones):
        sh = pix.bevel(mask, *tones)
        out[mask] = sh[mask]

    if kind == "missile":
        for px0 in (cx - 5, cx + 2):
            pod = (xx >= px0) & (xx <= px0 + 3) & (yy >= cy - 5) & (yy <= cy + 4)
            put(pod, ("hull_hi", "hull_light", "hull_mid"))
        for i, (tx, ty) in enumerate(((cx - 4, cy - 4), (cx + 3, cy - 4), (cx - 4, cy), (cx + 3, cy))):
            out[ty:ty + 3, tx:tx + 2] = rgba("hull_black")
            if i < loaded:
                out[ty, tx:tx + 2] = rgba("ion_white" if (firing and i == 0) else "hull_hi")
    body = np.hypot(xx - cx, yy - cy) <= 3.4
    put(body, ("hull_hi", "hull_light", "hull_mid"))
    if kind == "auto":
        for bx in (cx - 2, cx + 2):
            out[cy - 7:cy - 2, bx] = rgba("hull_light")
            out[cy - 7, bx] = rgba(tip)
        out[cy - 3, cx - 2:cx + 3] = rgba("hull_mid")        # the bar joining the twin barrels
    elif kind == "sniper":
        out[cy - 10:cy - 2, cx] = rgba("hull_light")
        out[cy - 8, cx - 1:cx + 2] = rgba("hull_mid")       # muzzle brake
        out[cy - 10, cx] = rgba(tip)
        out[cy - 3:cy, cx - 1:cx + 2] = rgba("hull_mid")    # breech
    out[cy, cx] = rgba("canopy_hi" if firing else "canopy")
    return Image.fromarray(out)


def sentry(kind: str, tier: int = 1, angle: float = 0.0, frame: int = 0, firing: bool = False) -> Image.Image:
    """A whole sentry, base and turret, for boards and icons (the game turns the turret on its own)."""
    base = sentry_base(tier, frame)
    tur = S._finish(turret_interior(kind, firing), OUTLINE, angle)
    size = max(base.width, tur.width) + 2, max(base.height, tur.height) + 2
    out = pix.pad(base, size)
    out.alpha_composite(pix.pad(tur, size))
    return out


SENTRY_HEALTH_BAR = {1: 11, 2: 15, 3: 19}       # wider bar, more health


# Sentry shots: the same cyan as yours (they're on your side), in their own shapes.
def sentry_shot(kind: str, frame: int = 0, style: str = "shape") -> Image.Image:
    """`style` "shape" keeps your cyan with new shapes; "blue" keeps your shapes in a deeper blue."""
    if style == "blue":
        mapping = {"ion_white": "sentry_white", "ion_hi": "sentry_hi", "ion": "sentry", "ion_dark": "sentry_dark",
                   "hull_hi": "sentry_hi", "hull_light": "sentry", "hull_mid": "sentry_dark", "hull_dark": "sentry_dark"}
        src = {"auto": S.shot_auto(), "sniper": S.shot_sniper(), "missile": S.missile_player(frame)}[kind]
        return pix.recolor(src, mapping)
    legend = {"w": "ion_white", "h": "ion_hi", "i": "ion", "j": "ion_dark",
              "L": "hull_hi", "m": "hull_mid", "d": "hull_dark"}
    if kind == "auto":
        rows = [".w.", "whw", ".h.", ".j."]                       # a round pellet, not a streak
    elif kind == "sniper":
        rows = [".w.", "w.w", ".w.", ".h.", "...", ".h.", ".i.", "...", ".i.", ".j.", "...", ".j."]   # ring head, dashed tail
    else:
        rows = [".i.", "ihi", "jLj", "jLj", "j.j", ".w." if frame % 2 == 0 else ".h.", ".j." if frame % 2 == 0 else "..."]
    return pix.from_grid(rows, legend)


# ---------------------------------------------------------------- explosive mines

def mine(frame: int = 0, state: str = "armed") -> Image.Image:
    """A small spiked mine. States: laid (not armed yet, dark), armed (slow cyan blink) and
    triggered (an enemy is right over it: fast white flash)."""
    s = 11
    c = 5
    yy, xx = np.mgrid[0:s, 0:s]
    r = np.hypot(xx - c, yy - c)
    body = r <= 3.3
    out = np.zeros((s, s, 4), dtype=np.uint8)
    for dx, dy in ((0, -5), (5, 0), (0, 5), (-5, 0), (0, -4), (4, 0), (0, 4), (-4, 0),
                   (-4, -4), (4, -4), (-4, 4), (4, 4)):
        out[c + dy, c + dx] = rgba("hull_light" if abs(dx) + abs(dy) == 4 else "hull_mid")
    sh = pix.bevel(body, "hull_light", "hull_mid", "hull_dark")
    out[body] = sh[body]
    out[(r <= 1.5)] = rgba("hull_black")
    if state == "armed":
        light = "ion_hi" if frame % 4 == 0 else ("ion" if frame % 4 == 1 else "ion_dark")
    elif state == "triggered":
        light = "ion_white" if frame % 2 == 0 else "ion_hi"
    else:
        light = "hull_dark"
    out[c, c] = rgba(light)
    return pix.outline(Image.fromarray(out), OUTLINE)


BLAST_TONES = ["ion_dark", "ion", "ion_hi", "ion_white"]


def mine_blast(frame: int, radius: int = 48, seed: int = 5) -> Image.Image:
    """Seven frames: flash, swell, full blast, ring out, fade, smoke and embers.

    The full-blast frame shows the damage falloff: white in the middle, fading evenly to dark
    blue at the edge, the way damage drops off with distance.
    """
    R = radius
    size = 2 * R + 13
    c = (size - 1) / 2
    yy, xx = np.mgrid[0:size, 0:size]
    rr = np.hypot(xx - c, yy - c)
    noise = (pix.value_noise(size, size, 4, seed + frame) - 0.5)
    out = np.zeros((size, size, 4), dtype=np.uint8)

    def falloff(extent: float, strength: float, hollow: float = 0.0) -> None:
        v = np.clip(1 - rr / extent + noise * 0.12, 0, 1) * strength
        lv = pix.dither_levels(v, 5)
        inside = (rr <= extent) & (rr >= hollow)
        for i, tone in enumerate(BLAST_TONES, start=1):
            out[inside & (lv == i)] = rgba(tone)

    def ring(radius_: float, tone: str, width: float = 0.8, broken: bool = False) -> None:
        m = np.abs(rr - radius_) <= width
        if broken:
            ang = np.arctan2(yy - c, xx - c)
            m &= (np.sin(ang * 9 + frame) > -0.2)
        out[m] = rgba(tone)

    if frame == 0:
        falloff(R * 0.28, 1.0)
        for k in range(8):
            a = math.tau * k / 8
            for t in range(int(R * 0.28), int(R * 0.45)):
                out[int(round(c + t * math.sin(a))), int(round(c + t * math.cos(a)))] = rgba("ion_hi")
    elif frame == 1:
        falloff(R * 0.68, 1.0)
        ring(R * 0.68, "ion_hi")
    elif frame == 2:
        falloff(R, 1.0)
        ring(R, "ion_white")
    elif frame == 3:
        falloff(R * 0.95, 0.72)
        ring(R + 2, "ion_hi")
    elif frame == 4:
        falloff(R * 0.85, 0.42, hollow=R * 0.3)
        ring(R + 4, "ion", broken=True)
    elif frame == 5:
        ring(R + 5, "ion_dark", broken=True)
        smoke = (rr <= R * 0.8) & (noise > 0.22) & ((xx + yy) % 2 == 0)
        out[smoke] = rgba("hull_mid")
    rng = pix.seeded(seed)
    if frame >= 1:
        for _ in range(26):
            a = rng.uniform(0, math.tau)
            d = R * min(1.15, rng.uniform(0.3, 0.7) + frame * 0.14)
            x, y = int(round(c + d * math.cos(a))), int(round(c + d * math.sin(a)))
            if 0 <= x < size and 0 <= y < size and frame <= 6:
                out[y, x] = rgba(["ion_white", "ion_hi", "ion_hi", "ion", "ion", "ion_dark", "ion_dark"][frame])
    return Image.fromarray(out)


def blast_ramp(width: int = 120) -> Image.Image:
    """The blast's damage falloff drawn as a strip: full damage on the left, none on the right."""
    h = 9
    xs = np.linspace(1, 0, width)
    v = np.tile(xs, (h, 1))
    lv = pix.dither_levels(v, 5)
    out = np.zeros((h, width, 4), dtype=np.uint8)
    for i, tone in enumerate(BLAST_TONES, start=1):
        out[lv == i] = rgba(tone)
    out[lv == 0] = rgba("console_dark")
    return Image.fromarray(out)


# ---------------------------------------------------------------- your ship's extras

POD_TIPS = {"L": [(1, 6), (2, 6), (3, 6)], "R": [(13, 6), (12, 6), (11, 6)]}   # outermost first


def pods_split(missiles: int) -> tuple[int, int]:
    """How the next six missiles sit on the pods. They launch left, right, left..., so the left pod
    empties first."""
    n = max(0, min(6, missiles))
    return n // 2, n - n // 2


def player_interior_loaded(missiles: int) -> Image.Image:
    """The ship with its missiles showing: a cyan nose at the front of each pod per missile loaded,
    three a side. Empty slots go dark."""
    img = S.player_interior()
    px = img.load()
    left, right = pods_split(missiles)
    for side, count in (("L", left), ("R", right)):
        tips = POD_TIPS[side]
        for i, (x, y) in enumerate(tips):
            loaded = i >= 3 - count
            px[x, y] = rgba("ion_hi" if loaded else "hull_black")
    return img


BOOST_CANVAS = 45
_BOOST_OFFSET = (BOOST_CANVAS - 15) // 2
BOOST_LENGTH = {1: 7, 2: 10, 3: 14}


def boost_flame(level: int, frame: int = 0) -> Image.Image:
    """The main engine on boost, longer and hotter at each level. Level 3 also trails speed lines."""
    img = Image.new("RGBA", (BOOST_CANVAS, BOOST_CANVAS), pix.CLEAR)
    px = img.load()
    o = _BOOST_OFFSET
    L = BOOST_LENGTH[level] + (1 if frame % 2 == 0 else 0)
    cols = {7: [(0.55, "ion_white"), (0.8, "ion_hi"), (0.95, "ion"), (1.01, "ion_dark")],
            6: [(0.35, "ion_hi"), (0.6, "ion"), (0.78, "ion_dark")],
            8: [(0.35, "ion_hi"), (0.6, "ion"), (0.78, "ion_dark")]}
    if level >= 2:
        cols[6] = [(0.25, "ion_white"), (0.5, "ion_hi"), (0.7, "ion"), (0.85, "ion_dark")]
        cols[8] = cols[6]
        cols[5] = [(0.22, "ion"), (0.4, "ion_dark")]
        cols[9] = cols[5]
    if level >= 3:
        cols[5] = [(0.2, "ion_hi"), (0.4, "ion"), (0.55, "ion_dark")]
        cols[9] = cols[5]
        cols[4] = [(0.15, "ion_dark")]
        cols[10] = cols[4]
    for x, bands in cols.items():
        for j in range(L):
            share = (j + 0.5) / L
            for limit, tone in bands:
                if share <= limit:
                    px[x + o, 15 + j + o] = rgba(tone)
                    break
    if level >= 3:
        # Speed lines trailing from the pods.
        for x in (1, 13):
            for j in range(3, 13):
                if (j + frame) % 3 != 0:
                    px[x + o, 12 + j + o] = rgba("ion_dark")
    return img


def boost_parts(level: int, frame: int = 0, missiles: int = 6) -> tuple[Image.Image, Image.Image]:
    """The ship and its boost flame on matching canvases, for smooth turning."""
    body = pix.pad(player_interior_loaded(missiles), (BOOST_CANVAS, BOOST_CANVAS))
    return body, boost_flame(level, frame)


def shield_bubble(level: int, radius: int = 14, frame: int = 0) -> Image.Image:
    """The shield shown for a moment after a hit. Level 1 is a thin, broken ring that looks fragile;
    level 2 is the dashed ring from the combat sprint; level 3 is a solid double ring."""
    size = radius * 2 + 3
    img = Image.new("RGBA", (size, size), pix.CLEAR)
    d = ImageDraw.Draw(img)
    c = size // 2

    def points(r):
        steps = max(16, int(2 * math.pi * r * 1.5))
        seen = []
        for i in range(steps):
            a = 2 * math.pi * i / steps
            p = (int(round(c + r * math.cos(a))), int(round(c + r * math.sin(a))))
            if p not in seen:
                seen.append(p)
        return seen

    if level == 1:
        for i, p in enumerate(points(radius)):
            if (i + frame) % 7 < 2:
                d.point(p, fill=rgba("ion_dark"))
            elif (i + frame) % 7 == 2:
                d.point(p, fill=rgba("ion"))
    elif level == 2:
        return E.shield_bubble(radius, frame)
    else:
        for i, p in enumerate(points(radius)):
            d.point(p, fill=rgba("ion_hi" if (i + frame * 2) % 9 == 0 else "ion"))
        for i, p in enumerate(points(radius - 2)):
            if (i - frame) % 4 < 2:
                d.point(p, fill=rgba("ion_dark"))
    return img


# ---------------------------------------------------------------- laser charge-up

LASER_CHARGE_TIME = 2.0      # shown here for the art only; the game reads it from weapons.json


def draw_laser_charge(scene: pix.Scene, x: float, y: float, angle: float, t: float, frame: int,
                      seed: int = 3, cancel: float = 0.0) -> None:
    """Energy drawn in from all around the ship to its nose while the laser charges.

    `t` goes from 0 to 1 over the 2 second charge. A ring round the ship fills like a clock so
    you can see when it's ready. `cancel` 0 to 1 plays the energy scattering back out when you let
    go early.
    """
    rng = pix.seeded(seed)
    a = math.radians(angle)
    nose = (x + math.sin(a) * 9, y - math.cos(a) * 9)
    d = ImageDraw.Draw(scene.base)
    motes = 30
    for i in range(motes):
        th = rng.uniform(0, math.tau)
        r0 = rng.uniform(26, 40)
        phase = rng.random()
        spd = rng.uniform(1.6, 2.4)
        if cancel <= 0 and i > motes * min(1.0, 0.35 + t * 0.9):
            continue
        u = (t * spd + phase) % 1.0
        if cancel > 0:
            u = max(0.0, u - cancel * 1.4)
        r = r0 * (1 - u) ** 1.4 + 1
        ang = th + u * 1.4
        mx, my = nose[0] + r * math.cos(ang), nose[1] + r * math.sin(ang)
        tone = "ion_dark" if u < 0.35 else ("ion" if u < 0.65 else ("ion_hi" if u < 0.88 else "ion_white"))
        if cancel > 0:
            tone = ["ion_hi", "ion", "ion_dark", "ion_dark"][min(3, int(cancel * 4))]
            if cancel > 0.8 and i % 2:
                continue
        back = 0.1 if cancel <= 0 else 0.04
        r2 = r0 * (1 - max(0.0, u - back)) ** 1.4 + 1
        ang2 = th + max(0.0, u - back) * 1.4
        tx, ty = nose[0] + r2 * math.cos(ang2), nose[1] + r2 * math.sin(ang2)
        trail = {"ion_white": "ion_hi", "ion_hi": "ion", "ion": "ion_dark"}.get(tone, "ion_dark")
        d.line([(tx, ty), (mx, my)], fill=rgba(trail))
        d.point((round(mx), round(my)), fill=rgba(tone))
        if u > 0.5 and cancel <= 0:
            d.point((round(mx) + 1, round(my)), fill=rgba(tone))
        scene.light[int(round(my)) % scene.h, int(round(mx)) % scene.w] = np.array(rgba(tone)[:3]) / 255 * 0.6
    # The orb gathering at the nose.
    if cancel <= 0:
        orb = 0.6 + 3.4 * t
        for rad, tone in ((orb, "ion_dark"), (orb - 1, "ion"), (orb - 2, "ion_hi"), (orb - 3, "ion_white")):
            if rad > 0.4:
                d.ellipse([nose[0] - rad, nose[1] - rad, nose[0] + rad, nose[1] + rad], fill=rgba(tone))
        _add_glow(scene, nose, orb + 2, 0.4 + 0.6 * t)
    # The charge clock: a ring that fills clockwise from the nose.
    ring_r = 16
    full = t >= 0.999 and cancel <= 0
    steps = 90
    for k in range(steps):
        share = k / steps
        if share > t and not full:
            if k % 6 == 0 and cancel <= 0:
                pa = a + share * math.tau
                d.point((round(x + ring_r * math.sin(pa)), round(y - ring_r * math.cos(pa))), fill=rgba("console_edge"))
            continue
        if cancel > 0 and (k + int(cancel * 10)) % 3:
            continue
        pa = a + share * math.tau
        p = (round(x + ring_r * math.sin(pa)), round(y - ring_r * math.cos(pa)))
        tone = "ion_white" if full and frame % 2 == 0 else ("ion_hi" if share > t - 0.06 else "ion")
        if cancel > 0:
            tone = "ion_dark"
        d.point(p, fill=rgba(tone))


def _add_glow(scene: pix.Scene, p, r: float, strength: float) -> None:
    x0, y0 = int(p[0] - r), int(p[1] - r)
    for yy in range(y0, int(p[1] + r) + 1):
        for xx in range(x0, int(p[0] + r) + 1):
            if 0 <= xx < scene.w and 0 <= yy < scene.h and math.hypot(xx - p[0], yy - p[1]) <= r:
                scene.light[yy, xx] = np.maximum(scene.light[yy, xx], np.array(rgba("ion_hi")[:3]) / 255 * strength)


def laser_burst(length: int, frame: int) -> Image.Image:
    """The moment the charged laser lets go: the beam starts extra wide, then settles to its usual
    width (frame 2 on)."""
    beam = S.laser_player(length, frame)
    if frame >= 2:
        return beam
    w = beam.width + (6 if frame == 0 else 3)
    wide = beam.resize((w, length), Image.NEAREST)
    a = np.array(wide)
    if frame == 0:
        a[:, 2:-2][a[:, 2:-2, 3] > 0] = rgba("ion_white")
    return Image.fromarray(a)
