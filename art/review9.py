"""Images and animations for the sprint 9 review page (hauling: the lasso and the collector ring).

    python -m art.review9 DIR      # writes DIR/img, DIR/anim, DIR/mock, DIR/meta.json and DIR/index.html
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from PIL import Image

from . import effects as E, haul as Hl, hud, items as I, mockups, pix, pixfont, sprites as S, station
from .review6 import Review, _top, label, place_drill, ship_parts

OUTLINE = I.OUTLINE
TAIL = 12                     # the beam leaves the ship this far behind its centre
SHIP_R = 9


def tail_of(ship: tuple[float, float], angle: float) -> tuple[float, float]:
    return mockups.turn(ship, angle, 0, TAIL)


def draw_ship(sc: pix.Scene, pos, angle: float, f: int, thrust: bool = True, missiles: int = 6) -> None:
    body, fl = ship_parts(missiles, ("W",) if thrust else (), f)
    sc.blit_smooth(body, pos[0], pos[1], angle=angle, outline=OUTLINE, overlay=fl)


class Rope:
    """A rock on a rigid beam of fixed length behind the ship, stepped once per frame. The rock keeps
    its momentum; the beam only stops it getting nearer or further than `length`."""

    def __init__(self, rock: tuple[float, float], length: float, drag: float = 0.985):
        self.cur = list(rock)
        self.prev = list(rock)
        self.length = length
        self.drag = drag
        self.held = False

    def step(self, anchor: tuple[float, float] | None = None) -> tuple[float, float]:
        vx = (self.cur[0] - self.prev[0]) * self.drag
        vy = (self.cur[1] - self.prev[1]) * self.drag
        nxt = [self.cur[0] + vx, self.cur[1] + vy]
        if self.held and anchor is not None:
            dx, dy = nxt[0] - anchor[0], nxt[1] - anchor[1]
            n = math.hypot(dx, dy) or 1.0
            nxt = [anchor[0] + dx / n * self.length, anchor[1] + dy / n * self.length]
        self.prev, self.cur = self.cur, nxt
        return tuple(self.cur)

    @property
    def vel(self) -> tuple[float, float]:
        return self.cur[0] - self.prev[0], self.cur[1] - self.prev[1]


def path_point(pts: list[tuple[float, float]], t: float) -> tuple[float, float]:
    """A point along a smooth path through `pts` (Catmull-Rom), t from 0 to 1."""
    n = len(pts) - 1
    u = min(n - 1e-6, max(0.0, t * n))
    i = int(u)
    s = u - i
    p0 = pts[max(0, i - 1)]
    p1, p2 = pts[i], pts[min(n, i + 1)]
    p3 = pts[min(n, i + 2)]
    out = []
    for k in range(2):
        a = 2 * p1[k]
        b = p2[k] - p0[k]
        c = 2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]
        d = -p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]
        out.append(0.5 * (a + b * s + c * s * s + d * s * s * s))
    return out[0], out[1]


def ring_with_field(sc: pix.Scene, centre, frame: int, health: float = 1.0, lit=(), field: bool = True) -> None:
    if field:
        sc.blit(Hl.ring_field(frame), *centre, glow=0.6)
    sc.blit(Hl.collector_ring(frame, health, lit), *centre)


def bar_over_ring(sc: pix.Scene, centre, health: float) -> None:
    bar = I.struct_bar(64, health)
    sc.blit(bar, centre[0], centre[1] - Hl.PAD_R - Hl.PAD_HALF - 8, glow=0.3)


# ---------------------------------------------------------------- boards

def boards(r: Review) -> None:
    # The ring: empty, holding four rocks, and badly damaged.
    W, H = 3 * 340 + 8, 356
    sc = pix.Scene(W, H, 2)
    rocks = [(96, 515, 14), (64, 4242, 10), (48, 106, 6), (96, 77, 12)]
    for col, (text, health, full) in enumerate((("EMPTY", 1.0, False), ("HOLDING 4", 1.0, True), ("DAMAGED", 0.35, True))):
        c = (4 + 170 + col * 340, 176)
        ring_with_field(sc, c, col, health, lit=(1,) if col == 1 else ())
        if full:
            for i, (d, seed, ore) in enumerate(rocks):
                p = Hl.slot_point(c, i)
                rock = I.drained_rock(d, seed, ore, 1 if col == 2 else 0)
                sc.blit(Hl.rock_hold(d, col), *p, glow=0.5)
                sc.blit(rock, *p)
                place_drill(sc, rock, p, (i * 90 + 200) % 360, 0.4 + 0.15 * i, i)
        if col == 2:
            bar_over_ring(sc, c, health)
        label(sc, text, c[0], H - 10)
    r.save("ring_states", sc)

    # Mounts: an empty one, then each sentry kind mounted. No platform and no health bar of their own.
    ring = Hl.collector_ring(0)
    rc = Hl.ring_centre()
    crop = ring.crop((int(rc - 44), 0, int(rc + 45), 46))
    cell = 96
    sc = pix.Scene(cell * 4, 70, 4)
    for col, kind in enumerate((None, "auto", "sniper", "missile")):
        x = col * cell + cell / 2
        sc.blit(crop, x, 8 + crop.height / 2 - 1)
        mx, my = x, 8 + (Hl.MARGIN + Hl.PAD_HALF)
        if kind:
            sc.blit_smooth(I.turret_interior(kind, loaded=3), mx, my, angle=-20 + col * 20, outline=OUTLINE)
        label(sc, "EMPTY MOUNT" if kind is None else I.SENTRY_NAMES[kind], x, 58)
    r.save("mounts", sc)

    # The beam at its three levels, in each look.
    for style in ("A", "B"):
        sc = pix.Scene(3 * 76, 150, 4)
        for lv in (1, 2, 3):
            x = 38 + (lv - 1) * 76
            ship = (x, 24)
            d = (24, 40, 64)[lv - 1]
            rock = S.asteroid(d, 300 + lv, 4)
            tail = tail_of(ship, 0)
            rp = (x, 24 + 46 + d / 2 - 12)
            Hl.draw_tow_beam(sc, tail, (rp[0], rp[1] - d / 2 - 1), 2, style, lv)
            sc.blit(rock, *rp)
            sc.blit(Hl.grip(d, 2), *rp, glow=0.5)
            draw_ship(sc, ship, 0, 0)
            label(sc, f"LV{lv}", x, 2)
        r.save(f"beam_{style.lower()}", sc)

    # Picking a rock: bright brackets when you can tow it, dim with a note when it's too heavy.
    sc = pix.Scene(220, 132, 4)
    for x, d, ok, text in ((60, 32, True, "Q TO GRAB"), (160, 96, False, "NEEDS LV3")):
        rock = S.asteroid(d, 50 + d, 6)
        sc.blit(rock, x, 56)
        sc.blit(Hl.target_brackets(d, ok), x, 56, glow=0.6 if ok else 0, hud=not ok)
        label(sc, text, x, 56 + d / 2 + 8 if d < 60 else 122, "ion_hi" if ok else "hud_dim")
    draw_ship(sc, (60, 14), 180, 0, thrust=False)
    r.save("targeting", sc)

    # Thrown: speed lines only while it's fast enough to hurt.
    sc = pix.Scene(240, 80, 4)
    rock = S.asteroid(40, 9, 5)
    sc.blit(rock, 60, 38)
    label(sc, "SLOW: JUST BUMPS", 60, 66)
    Hl.speed_lines(sc, (180, 38), (6, 0), 40, 1.0)
    sc.blit(rock, 180, 38)
    label(sc, "FAST: HURTS", 180, 66, "hud_text")
    r.save("throw_speed", sc)

    # Placing the ring: room to place it, and rocks in the way.
    W, H = 2 * 340, 350
    sc = pix.Scene(W, H, 2)
    for col, ok in enumerate((True, False)):
        c = (170 + col * 340, 168)
        if not ok:
            for (dx, dy, d, seed) in ((-40, -30, 48, 11), (70, 50, 32, 12), (10, 90, 24, 13)):
                sc.blit(S.asteroid(d, seed, 0), c[0] + dx, c[1] + dy)
        sc.blit(Hl.placement_ghost(ok, col), *c, glow=0.5)
        draw_ship(sc, c, 30, 0, thrust=False)
        label(sc, "T TO PLACE" if ok else "ROCKS IN THE WAY", c[0], H - 10, "ion_hi" if ok else "danger_pink_hi")
    r.save("placing", sc)

    r.board("shop_icons", [("LASSO", hud.item_icon("lasso")), ("RING", hud.item_icon("ring"))], 6, gap=12, zoom=2)


# ---------------------------------------------------------------- animations

def tow_anim(r: Review, style: str) -> None:
    """Fly up, pick the rock, the beam latches, then swing it round a turn. Its drill keeps going."""
    k = 3
    W, H = 280, 190
    d, seed, ore = 40, 4242, 8
    rock_img = S.asteroid(d, seed, ore)
    L = 34 + d / 2
    rope = Rope((168, 122), L)
    frames, times = [], []
    approach = [(276, 40), (240, 58), (210, 78)]
    tour = [(210, 78), (190, 62), (150, 52), (112, 62), (96, 92), (110, 124), (148, 134), (184, 118), (200, 92)]
    fill = 0.2
    total = 6 + 6 + 44
    prev_ship = approach[0]
    for f in range(total):
        sc = pix.Scene(W, H, k)
        if f < 6:
            ship = path_point(approach, f / 5)
            text, color = "FLY CLOSE", "hud_dim"
            ang = mockups.heading(prev_ship, ship) if f else 230
            thrust = True
        elif f < 12:
            ship = approach[-1]
            ang = mockups.heading(ship, rope.cur) + 180
            text, color = "Q: GRAB", "ion_hi"
            thrust = False
        else:
            ship = path_point(tour, (f - 12) / (total - 13))
            ang = mockups.heading(prev_ship, ship)
            text, color = "TOWING", "hud_text"
            thrust = True
            rope.held = True
        anchor = tail_of(ship, ang)
        rp = rope.step(anchor if rope.held else None)
        prev_ship = ship
        if f < 6:
            sc.blit(Hl.target_brackets(d, True, f), *rp, glow=0.6)
        elif f < 12:
            closing = (f - 6) / 5
            Hl.draw_tow_beam(sc, anchor, (rp[0], rp[1]), f, style, 2, fade=closing)
            sc.blit(Hl.grip(d, f, closing), *rp, glow=0.5)
        else:
            dx, dy = rp[0] - anchor[0], rp[1] - anchor[1]
            n = math.hypot(dx, dy) or 1
            Hl.draw_tow_beam(sc, anchor, (rp[0] - dx / n * (d / 2 + 1), rp[1] - dy / n * (d / 2 + 1)), f, style, 2)
            sc.blit(Hl.grip(d, f), *rp, glow=0.5)
        sc.blit(rock_img, *rp)
        fill = min(1.0, fill + 0.012)
        place_drill(sc, rock_img, rp, 200, fill, f)
        draw_ship(sc, ship, ang, f, thrust)
        label(sc, text, W / 2, H - 10, color)
        frames.append(sc.render()); times.append(100)
    r.anim(f"tow_{style.lower()}", frames, times, (W * k, H * k))


def throw_anim(r: Review) -> None:
    """Swing round, let go at the top, and the rock flies on into a raid. It only hurts while it's
    fast: after the hit it's slowed down and just drifts."""
    k = 3
    W, H = 300, 180
    d = 32
    rock_img = S.asteroid(d, 9, 5)
    L = 34 + d / 2
    centre = (78, 112)
    rs = 14                              # the ship's circle; the rock swings round outside it
    R = rs + L
    step = 9.0                           # degrees a frame
    release = 20
    th_rel = 270.0
    th0 = th_rel - step * release
    rel_pos = (centre[0] + R * math.cos(math.radians(th_rel)), centre[1] + R * math.sin(math.radians(th_rel)))
    speed = R * math.radians(step)
    raiders = [(rel_pos[0] + 150, rel_pos[1] + 2), (rel_pos[0] + 170, rel_pos[1] - 18), (rel_pos[0] + 176, rel_pos[1] + 22)]
    alive = [True] * 3
    boom: dict[int, int] = {}
    rp = rel_pos
    vel = (speed, 0.0)
    frames, times = [], []
    for f in range(46):
        sc = pix.Scene(W, H, k)
        if f <= release:
            th = math.radians(th0 + step * f)
            ship = (centre[0] + rs * math.cos(th), centre[1] + rs * math.sin(th))
            rp = (centre[0] + R * math.cos(th), centre[1] + R * math.sin(th))
            # The tail points out along the beam at the rock.
            ang = mockups.heading(ship, rp) + 180
            held = True
        else:
            held = False
            g = f - release
            ship = (ship_rel[0] - 1.6 * g, ship_rel[1] + 2.2 * g)
            ang = 215
            rp = (rp[0] + vel[0], rp[1] + vel[1])
            vel = (vel[0] * 0.97, vel[1] * 0.97)
            for i, (ex, ey) in enumerate(raiders):
                if alive[i] and math.hypot(rp[0] - ex, rp[1] - ey) < d / 2 + 5:
                    sp = math.hypot(*vel)
                    if sp > 2.0:
                        alive[i] = False
                        boom[i] = f
                        vel = (-0.25 * vel[0] + 0.3, 0.25 * abs(vel[0]) * (1 if i != 1 else -1))
        if f == release:
            ship_rel = ship
        sp = math.hypot(*vel)
        fast = (not held) and sp > 2.0
        for i, (ex, ey) in enumerate(raiders):
            if alive[i]:
                sc.blit(S.infantry(f % 2, angle=mockups.heading((ex, ey), ship)), ex, ey)
            elif f - boom[i] < 6:
                sc.blit(S.explosion(f - boom[i], "enemy", seed=i + 3), ex, ey)
        if fast:
            Hl.speed_lines(sc, rp, vel, d, min(1.0, (sp - 2.0) / 4.0))
        if held:
            anchor = tail_of(ship, ang)
            dx, dy = rp[0] - anchor[0], rp[1] - anchor[1]
            n = math.hypot(dx, dy) or 1
            Hl.draw_tow_beam(sc, anchor, (rp[0] - dx / n * (d / 2 + 1), rp[1] - dy / n * (d / 2 + 1)), f, "A", 2)
            sc.blit(Hl.grip(d, f), *rp, glow=0.5)
        sc.blit(rock_img, *rp)
        draw_ship(sc, ship, ang, f)
        if held:
            text, color = "SWING IT ROUND", "hud_dim"
        elif boom:
            text, color = "HIT - NOW SLOW, IT JUST DRIFTS", "hud_dim"
        else:
            text, color = "Q: LET GO - IT FLIES ON", "ion_hi"
        label(sc, text, W / 2, H - 10, color)
        frames.append(sc.render()); times.append(90 if f < release + 14 else 120)
    r.anim("throw", frames, times, (W * k, H * k))


def ring_fill_anim(r: Review) -> None:
    """Tow a fourth rock in and let go. The field catches it and holds it. A full drill sells
    straight into the ring: a spark of gold to the nearest node and the credits go up."""
    k = 2
    W, H = 440, 350
    c = (170, 172)
    held = {1: (64, 4242, 10), 2: (48, 106, 6), 3: (96, 515, 14)}
    fills = {1: 0.92, 2: 0.3, 3: 0.55}
    d4, s4 = 64, 77
    rock4 = S.asteroid(d4, s4, 10)
    target = Hl.slot_point(c, 0)
    L = 34 + d4 / 2
    path = [(436, 36), (392, 66), (336, 104), (276, 140), (222, 170)]
    rope = Rope((468, 30), L)
    rope.held = True
    frames, times = [], []
    credits = 2310
    pulse = None
    lit_until = -1
    pop = None
    prev_ship = path[0]
    for _ in range(10):
        rope.step(tail_of(path[0], mockups.heading(path[0], path[1])))
    for f in range(64):
        sc = pix.Scene(W, H, k)
        ring_with_field(sc, c, f, 1.0, lit=(1,) if f <= lit_until else ())
        for i, (d, seed, ore) in held.items():
            p = Hl.slot_point(c, i)
            rock = S.asteroid(d, seed, ore)
            sc.blit(Hl.rock_hold(d, f), *p, glow=0.5)
            sc.blit(rock, *p)
            fills[i] = min(1.0, fills[i] + 0.01)
            place_drill(sc, rock, p, (i * 90 + 200) % 360, fills[i], f)
        # The drill on the top-right rock fills and sells.
        if fills[1] >= 1.0 and pulse is None:
            pulse = f
        if pulse is not None:
            rock = S.asteroid(*held[1])
            p = Hl.slot_point(c, 1)
            dx, dy = place_drill(pix.Scene(W, H, 1), rock, p, (1 * 90 + 200) % 360, 0, 0)
            t = (f - pulse) / 6
            if t <= 1:
                Hl.gold_pulse(sc, (dx, dy), Hl.node_point(c, 1), t)
            elif pop is None:
                pop = f
                lit_until = f + 4
                credits += 40
                fills[1] = 0.0
        if pop is not None and f - pop < 14:
            n = Hl.node_point(c, 1)
            sc.blit(Hl.credit_pop(40), n[0] + 14, n[1] - 8 - (f - pop), glow=0, hud=True)
        # The ship tows the fourth rock in, lets go, and the field settles it.
        if f < 26:
            ship = path_point(path, f / 25)
            ang = mockups.heading(prev_ship, ship) if f else 230
            prev_ship = ship
            anchor = tail_of(ship, ang)
            rp = rope.step(anchor)
            dx, dy = rp[0] - anchor[0], rp[1] - anchor[1]
            n = math.hypot(dx, dy) or 1
            Hl.draw_tow_beam(sc, anchor, (rp[0] - dx / n * (d4 / 2 + 1), rp[1] - dy / n * (d4 / 2 + 1)), f, "A", 3)
            sc.blit(Hl.grip(d4, f), *rp, glow=0.5)
            text, color = "TOW IT INSIDE", "hud_text"
        else:
            if f == 26:
                rope.held = False
                settle_from = tuple(rope.cur)
            g = min(1.0, (f - 26) / 16)
            e = 1 - (1 - g) ** 3
            rp = (settle_from[0] + (target[0] - settle_from[0]) * e, settle_from[1] + (target[1] - settle_from[1]) * e)
            ship = (prev_ship[0] + (f - 26) * 2.6, prev_ship[1] + (f - 26) * 0.4)
            ang = 100
            if g > 0.3:
                sc.blit(Hl.rock_hold(d4, f), *rp, glow=0.5 * g)
            text, color = ("Q: LET GO - THE RING HOLDS IT", "ion_hi") if g < 1 else ("4 OF 4 HELD", "hud_text")
        sc.blit(rock4, *rp)
        place_drill(sc, rock4, rp, 20, min(1.0, 0.3 + f * 0.008), f)
        draw_ship(sc, ship, ang, f, thrust=True)
        # Credits, top right.
        tag = pixfont.render(f"CR {credits:,}", "ore")
        sc.blit(tag, W - tag.width - 6, 6, center=False, glow=0, hud=True)
        label(sc, text, W / 2 + 40, H - 10, color)
        frames.append(sc.render()); times.append(100)
    r.anim("ring_fill", frames, times, (W * k, H * k))


def ring_break_anim(r: Review) -> None:
    """Mount a sentry from inside the ring, then a raid wears the ring down. Hits on mounted turrets
    hurt the ring, and when it breaks the mounted sentries go with it. The rocks are left drifting."""
    k = 2
    W, H = 360, 364
    c = (180, 182)
    held = [(64, 515, 10), (48, 4242, 8)]
    kinds = {0: ("auto", 0.0), 1: ("sniper", 0.0), 3: ("missile", 0.0)}
    frames, times = [], []
    raiders = [(318, 26), (340, 50), (304, 58), (346, 14)]
    health = 1.0
    me = (c[0] + 10, c[1] + 30)
    mounted = {1: kinds[1], 3: kinds[3]}
    broke_at = None
    bits = None
    for f in range(58):
        sc = pix.Scene(W, H, k)
        if broke_at is None:
            if 6 <= f < 10:
                mounted[0] = kinds[0]
            if f >= 12:
                health = max(0.0, health - (0.03 if f < 40 else 0.05))
            if health <= 0:
                broke_at = f
                sprite = Hl.ring_sprite(f, 0.0, (), {i: (kd, mockups.heading(Hl.mount_point(c, i), raiders[0]))
                                                     for i, (kd, _) in mounted.items()})
                bits = I.shatter(S.tight(sprite), 12, 28, seed=5, speed=1.1)
        for i, (d, seed, ore) in enumerate(held):
            p = Hl.slot_point(c, i)
            if broke_at is not None:
                drift = f - broke_at
                p = (p[0] + (i * 2 - 1) * drift * 0.5, p[1] + drift * 0.3)
            rock = S.asteroid(d, seed, ore)
            if broke_at is None:
                sc.blit(Hl.rock_hold(d, f), *p, glow=0.5)
            sc.blit(rock, *p)
            place_drill(sc, rock, p, 300 - i * 120, 0.5, f)
        if broke_at is None:
            ring_with_field(sc, c, f, health)
            for i, (kd, _) in mounted.items():
                aim = mockups.heading(Hl.mount_point(c, i), raiders[i % len(raiders)])
                firing = f >= 12 and (f + i) % 3 == 0
                Hl.mounted_turret(sc, c, i, kd, aim, firing)
                if firing and kd != "missile":
                    mx, my = Hl.mount_point(c, i)
                    tx, ty = raiders[i % len(raiders)]
                    t = 0.4
                    sc.blit_smooth(I.sentry_shot(kd), mx + (tx - mx) * t, my + (ty - my) * t, angle=aim)
            bar_over_ring(sc, c, health)
            # Enemy fire landing on the ring and its mounted turrets.
            if f >= 12:
                for j, (ex, ey) in enumerate(raiders):
                    tgt = Hl.mount_point(c, 0) if j % 2 == 0 else Hl.mount_point(c, 1)
                    t = ((f + j * 2) % 6) / 6
                    sc.blit(S.shot_infantry(f % 2), ex + (tgt[0] - ex) * t, ey + (tgt[1] - ey) * t)
                    if (f + j * 2) % 6 == 5:
                        sc.blit(E.flare("enemy", 0), *tgt)
        else:
            g = f - broke_at
            if g < len(bits):
                sc.blit(bits[g], c[0], c[1])
        for j, (ex, ey) in enumerate(raiders):
            sc.blit(S.infantry(f % 2, angle=mockups.heading((ex, ey), c)), ex, ey)
        if f < 6:
            draw_ship(sc, me, 0, f, thrust=False)
            text, color = "INSIDE THE RING", "hud_dim"
        elif f < 12:
            draw_ship(sc, me, 0, f, thrust=False)
            text, color = "R: MOUNTED ON TOP", "ion_hi"
        else:
            draw_ship(sc, (me[0] - (f - 12) * 2.5, me[1] + (f - 12) * 1.5), 230, f)
            if broke_at is None:
                text, color = ("HITS ON TURRETS HURT THE RING", "hud_text") if health > 0.3 else ("RING ALMOST GONE", "danger_pink_hi")
            else:
                text, color = "RING DESTROYED - ITS SENTRIES TOO", "danger_pink_hi"
        label(sc, text, W / 2, H - 10, color)
        frames.append(sc.render()); times.append(110 if broke_at is None else 120)
    r.anim("ring_break", frames, times, (W * k, H * k))


def anims(r: Review) -> None:
    tow_anim(r, "A")
    tow_anim(r, "B")
    throw_anim(r)
    ring_fill_anim(r)
    ring_break_anim(r)


# ---------------------------------------------------------------- mock screenshots

def tools_rows(selected: str) -> dict:
    """The Tools page with the lasso and the ring added at the bottom."""
    credits = 4650
    Row, Step, Detail = station.Row, station.Step, station.Detail
    rows = [Row("drill", "DRILL", 150, sub="0 CARRIED  4 OUT"), Row("mine", "MINE", 40, sub="3/5 CARRIED"),
            Row("sentry_auto", "AUTO SENTRY", 800, sub="FROM 800"), Row("sentry_sniper", "SNIPER SENTRY", 1600, sub="FROM 1,600"),
            Row("sentry_missile", "MISSILE SENTRY", 3200, sub="FROM 3,200"),
            Row("lasso", "LASSO", 1200, level=1), Row("ring", "COLLECTOR RING", 4000, sub="HOLDS 4 ROCKS")]

    def rock_art(d: int) -> Image.Image:
        return S.tight(S.asteroid(d, 40 + d, 0)).resize((max(5, d // 4), max(5, d // 4)), Image.NEAREST)

    if selected == "lasso":
        det = Detail("LASSO", "LEVEL 1 OF 3",
                     ["PRESS Q TO TOW A ROCK BEHIND YOU.", "LET GO AND IT FLIES ON. FAST ROCKS HURT ENEMIES."],
                     [Step("LV1", "SMALL", 500, "owned", art=pix.scale(rock_art(24), 2)),
                      Step("LV2", "MEDIUM", 1200, "next", art=pix.scale(rock_art(48), 2)),
                      Step("LV3", "LARGE", 2500, "locked", art=pix.scale(rock_art(96), 2))],
                     stats=[("TOWS", "SMALL", "MEDIUM")], buy="BUY LV2", price=1200)
        return dict(credits=credits, rows=rows, selected=5, det=det)
    det = Detail("COLLECTOR RING", "ONE PER GAME",
                 ["PLACE IT WITH T. TOW UP TO 4 ROCKS INSIDE AND THEIR DRILLS SELL ON THEIR OWN.",
                  "4 SENTRY MOUNTS. ENEMIES RAID IT."],
                 [], buy="BUY RING", price=4000)
    return dict(credits=credits, rows=rows, selected=6, det=det)


def station_mock(selected: str) -> pix.Scene:
    sc = pix.Scene()
    sc.blit(mockups.space_backdrop(seed=31), 0, 0, center=False)
    mockups.scatter_asteroids(sc, 12, 10, [(0, 100, 230, 300), (220, 0, 640, 360)], sizes=(8, 10, 12, 16))
    base = (112, 196)
    sc.blit(S.home_base(0), *base)
    body, fl = ship_parts(4, (), 0)
    sc.blit_smooth(body, base[0] + 18, base[1] - 18, angle=45, outline=OUTLINE, overlay=fl)
    label(sc, "DOCKED", base[0], base[1] + 40, "ion_hi")
    st = tools_rows(selected)
    panel = station.station_panel("tools", st["rows"], st["selected"], st["det"], st["credits"])
    sc.blit(panel, 640 - panel.width - 6, 40, center=False, hud=True)
    _top(sc)
    return sc


def in_game_mock() -> pix.Scene:
    sc = pix.Scene()
    sc.blit(mockups.space_backdrop(seed=53), 0, 0, center=False)
    c = (190, 190)
    keep = [(30, 30, 350, 350), (370, 40, 640, 170), (370, 270, 500, 340), (500, 200, 640, 360), (0, 0, 640, 30), (0, 330, 640, 360)]
    mockups.scatter_asteroids(sc, 23, 14, keep, sizes=(8, 10, 12, 14, 18))
    sc.blit(Hl.ring_field(2), *c, glow=0.6)
    held = [(96, 515, 14), (64, 4242, 10), (48, 106, 6)]
    fills = [0.7, 0.05, 0.4]
    for i, (d, seed, ore) in enumerate(held):
        p = Hl.slot_point(c, i)
        rock = I.drained_rock(d, seed, ore, 1 if i == 0 else 0)
        sc.blit(Hl.rock_hold(d, 2), *p, glow=0.5)
        sc.blit(rock, *p)
        place_drill(sc, rock, p, (i * 90 + 200) % 360, fills[i], i)
    sc.blit(Hl.collector_ring(1, 0.8, (1,)), *c)
    # A drill just sold: its spark has landed, the node is lit, credits pop.
    n = Hl.node_point(c, 1)
    sc.blit(Hl.credit_pop(40), n[0] - 26, n[1] - 14, glow=0, hud=True)
    bar_over_ring(sc, c, 0.8)
    # Raiders coming up from the bottom right; the mounted turrets answer.
    raiders = [(410, 300), (436, 312), (392, 322), (460, 296)]
    for i, (x, y) in enumerate(raiders):
        sc.blit(S.infantry(i % 2, angle=mockups.heading((x, y), c)), x, y)
    for i, kind, tgt in ((1, "sniper", raiders[3]), (2, "auto", raiders[2]), (3, "missile", raiders[2])):
        mp = Hl.mount_point(c, i)
        aim = mockups.heading(mp, tgt)
        Hl.mounted_turret(sc, c, i, kind, aim, firing=True)
        if kind == "auto":
            for t in (0.25, 0.45, 0.65):
                sc.blit_smooth(I.sentry_shot("auto"), mp[0] + (tgt[0] - mp[0]) * t, mp[1] + (tgt[1] - mp[1]) * t, angle=aim)
        elif kind == "sniper":
            sc.blit_smooth(I.sentry_shot("sniper"), mp[0] + (tgt[0] - mp[0]) * 0.5, mp[1] + (tgt[1] - mp[1]) * 0.5, angle=aim)
    for (x, y), tgt in zip(raiders[:2], (Hl.mount_point(c, 2), Hl.mount_point(c, 1))):
        for t in (0.35, 0.6):
            sc.blit(S.shot_infantry(1), x + (tgt[0] - x) * t, y + (tgt[1] - y) * t)
    # You, towing a fourth rock home with its drill still going.
    me = (430, 118)
    ang = mockups.heading(me, c)
    anchor = tail_of(me, ang)
    d4 = 64
    L = 34 + d4 / 2
    back = math.radians(ang + 180 + 14)
    rp = (anchor[0] + math.sin(back) * L, anchor[1] - math.cos(back) * L)
    dx, dy = rp[0] - anchor[0], rp[1] - anchor[1]
    nrm = math.hypot(dx, dy)
    Hl.draw_tow_beam(sc, anchor, (rp[0] - dx / nrm * (d4 / 2 + 1), rp[1] - dy / nrm * (d4 / 2 + 1)), 3, "A", 3)
    rock4 = S.asteroid(d4, 77, 10)
    sc.blit(Hl.grip(d4, 3), *rp, glow=0.5)
    sc.blit(rock4, *rp)
    place_drill(sc, rock4, rp, 160, 0.85, 0)
    body, fl = I.boost_parts(2, 0, missiles=4)
    sc.blit_smooth(body, *me, angle=ang, outline=OUTLINE, overlay=fl)
    hud.place_edge_arrow(sc, (-400, 520), "ion_hi", label="BASE")
    _top(sc, wave="WAVE 6", state="SPOTTED", state_color="danger_pink_hi", credits="4,120")
    con = hud.campaign_console(weapons=("auto", "sniper", "missiles"), current="auto", missiles=4,
                               shield_level=2, shield=0.9, hull=0.85, armor_level=1, boost_level=2, boost=0.7,
                               drills=1, mines=3, sentries=0)
    sc.blit(con, 640 - con.width - 6, 360 - con.height - 16, center=False, hud=True)
    x = 8
    for key, word in (("WASD", "FLY"), ("CLICK", "FIRE"), ("Q", "LASSO"), ("T", "RING"), ("F", "DRILL"),
                      ("G", "MINES"), ("R", "SENTRY")):
        k_ = pixfont.render(key, "hud_text")
        w_ = pixfont.render(word, "hud_dim")
        sc.blit(k_, x, 349, center=False, glow=0, hud=True)
        sc.blit(w_, x + k_.width + 4, 349, center=False, glow=0, hud=True)
        x += k_.width + w_.width + 14
    return sc


def mocks(r: Review) -> None:
    for sel in ("lasso", "ring"):
        station_mock(sel).render().save(r.dest / "mock" / f"station_{sel}.png", optimize=True)
    sc = in_game_mock()
    sc.render().save(r.dest / "mock" / "in_game.png", optimize=True)
    sc.render(crt=True).save(r.dest / "mock" / "in_game_crt.png", optimize=True)


def build(dest: Path) -> dict:
    r = Review(dest)
    boards(r)
    anims(r)
    mocks(r)
    (dest / "meta.json").write_text(json.dumps(r.meta, indent=1))
    return r.meta


if __name__ == "__main__":
    out = Path(sys.argv[1])
    build(out)
    from . import review_page9
    print(review_page9.build(out))
