"""Images and animations for the sprint 6 review page (station and item art).

    python -m art.review6 DIR      # writes DIR/img, DIR/anim, DIR/mock, DIR/meta.json and DIR/index.html
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from . import effects as E, hud, items as I, mockups, pix, pixfont, sprites as S, station
from .build import _gif

OUTLINE = I.OUTLINE


# ---------------------------------------------------------------- helpers

def label(scene: pix.Scene, text: str, x: float, y: float, color: str = "hud_dim", centre: bool = True) -> None:
    img = pixfont.render(text, color)
    scene.blit(img, x - (img.width // 2 if centre else 0), y, center=False, glow=0, hud=True)


def place_drill(scene: pix.Scene, rock: Image.Image, rock_xy, angle: float, fill: float, frame: int,
                health: float | None = None) -> tuple[float, float]:
    """Stand a drill on a rock's rim, facing out, the way the game places it. Returns its centre."""
    rx, ry = I.rim_point(rock, angle)
    cx, cy = rock_xy[0] - rock.width / 2 + rx + 0.5, rock_xy[1] - rock.height / 2 + ry + 0.5
    a = math.radians(angle)
    out = 5.0          # the legs sink a pixel or two into the rock
    x, y = cx + math.sin(a) * out, cy - math.cos(a) * out
    scene.blit_smooth(I.drill_interior(fill, frame), x, y, angle=angle, outline=OUTLINE)
    if health is not None:
        bar = I.struct_bar(13, health)
        scene.blit(bar, x, y - 14, glow=0.3)
    return x, y


def drill_site(rock: Image.Image, angle: float) -> tuple[int, int]:
    return I.rim_point(rock, angle)


def ship_parts(missiles: int = 6, boosters: tuple[str, ...] = (), frame: int = 0):
    body = pix.pad(I.player_interior_loaded(missiles), (27, 27))
    return body, S.player_flames(boosters, frame)


class Review:
    def __init__(self, dest: Path):
        self.dest = dest
        for sub in ("img", "anim", "mock"):
            (dest / sub).mkdir(parents=True, exist_ok=True)
        self.meta: dict = {"sprites": {}, "anims": {}}

    def board(self, name: str, items: list[tuple[str | None, Image.Image]], k: int, gap: int = 10, pad: int = 8,
              hud_piece: bool = False, zoom: int = 1) -> None:
        """A row of sprites with labels. `zoom` blows the sprites up without growing the labels."""
        if zoom > 1:
            items = [(lbl, pix.scale(img, zoom)) for lbl, img in items]
        labels = [pixfont.render(lbl, "hud_dim") if lbl else None for lbl, _ in items]
        label_h = 11 if any(labels) else 0
        slots = [max(img.width, t.width if t else 0) for (_, img), t in zip(items, labels)]
        w = sum(slots) + gap * (len(items) - 1) + pad * 2
        h = max(img.height for _, img in items) + pad * 2 + label_h
        sc = pix.Scene(w, h, k)
        x = pad
        inner_h = h - pad * 2 - label_h
        for (_, img), t, slot in zip(items, labels, slots):
            sc.blit(img, x + (slot - img.width) // 2, pad + (inner_h - img.height) // 2, center=False, hud=hud_piece)
            if t:
                sc.blit(t, x + (slot - t.width) // 2, h - pad - 7, center=False, glow=0, hud=True)
            x += slot + gap
        self.save(name, sc)

    def save(self, name: str, sc: pix.Scene) -> None:
        sc.render().save(self.dest / "img" / f"{name}.png", optimize=True)
        self.meta["sprites"][name] = [sc.w * sc.k, sc.h * sc.k]

    def anim(self, name: str, frames: list[Image.Image], ms, size: tuple[int, int]) -> None:
        _gif(frames, self.dest / "anim" / f"{name}.gif", ms)
        self.meta["anims"][name] = list(size)


# ---------------------------------------------------------------- boards

def boards(r: Review) -> None:
    r.board("drill_fill", [("EMPTY", I.drill(0.0, 0)), ("1/4", I.drill(0.25, 0)), ("HALF", I.drill(0.5, 0)),
                           ("3/4", I.drill(0.75, 1)), ("FULL", I.drill(1.0, 0)), ("FULL", I.drill(1.0, 1))], 3, gap=8, zoom=2)

    def with_bar(health: float) -> Image.Image:
        d = I.drill(0.6, 0)
        bar = I.struct_bar(13, health)
        out = Image.new("RGBA", (d.width, d.height + 6), pix.CLEAR)
        out.alpha_composite(bar, ((d.width - bar.width) // 2, 0))
        out.alpha_composite(d, (0, 6))
        return out
    r.board("drill_health", [("HEALTHY", with_bar(1.0)), ("HIT", with_bar(0.55)), ("ALMOST GONE", with_bar(0.2))], 3, gap=10, zoom=2)

    # Asteroid stages with two drills sharing it.
    d, seed, ore = 64, 4242, 12
    rich = S.asteroid(d, seed, ore)
    sites = [drill_site(rich, 25), drill_site(rich, 240)]
    cracks = I.crack_points(rich, sites, 9)
    w, h = 4 * 86 + 16, 104
    sc = pix.Scene(w, h, 3)
    for st, text in enumerate(("FULL", "3/4 LEFT", "HALF LEFT", "1/4 LEFT")):
        x = 8 + 43 + st * 86
        rock = I.drained_rock(d, seed, ore, st)
        rock.alpha_composite(I.crack_overlay(rock, cracks, st))
        sc.blit(rock, x, 50)
        fills = [(0.3, 0.8), (0.55, 0.2), (1.0, 0.6), (0.75, 1.0)][st]
        place_drill(sc, rock, (x, 50), 25, fills[0], 0)
        place_drill(sc, rock, (x, 50), 240, fills[1], 1)
        label(sc, text, x, h - 12)
    r.save("rock_stages", sc)

    r.board("drill_markers", [("WORKING", hud.drill_marker(200, 0.9, 0.45)), ("FULL", hud.drill_marker(160, 0.9, 1.0)),
                              ("UNDER ATTACK", hud.drill_marker(-30, 0.35, 0.7, hit=True))], 3, gap=14, hud_piece=True, zoom=2)

    # Sentries: kinds down, tiers across, each with its health bar.
    cell_w, cell_h = 44, 40
    sc = pix.Scene(3 * cell_w + 70, 3 * cell_h + 20, 5)
    for row, kind in enumerate(I.SENTRY_KINDS):
        y = 10 + row * cell_h + cell_h / 2 + 2
        label(sc, I.SENTRY_NAMES[kind], 6, y - 3, centre=False)
        for tier in (1, 2, 3):
            x = 70 + (tier - 1) * cell_w + cell_w / 2
            sc.blit(I.sentry_base(tier), x, y)
            sc.blit_smooth(I.turret_interior(kind), x, y, angle=0, outline=OUTLINE)
            sc.blit(I.struct_bar(I.SENTRY_HEALTH_BAR[tier], 1.0), x, y - 14, glow=0.3)
            if row == 0:
                label(sc, f"TIER {tier}", x, 2)
    r.save("sentries", sc)

    def pairs(style: str) -> list:
        return [("YOURS", S.shot_auto()), ("SENTRY", I.sentry_shot("auto", style=style)),
                ("YOURS", S.shot_sniper()), ("SENTRY", I.sentry_shot("sniper", style=style)),
                ("YOURS", S.missile_player(0)), ("SENTRY", I.sentry_shot("missile", style=style))]
    r.board("shots_shape", pairs("shape"), 3, gap=8, zoom=3)
    r.board("shots_blue", pairs("blue"), 3, gap=8, zoom=3)

    r.board("mine_states", [("JUST LAID", I.mine(0, "laid")), ("ARMED", I.mine(0, "armed")),
                            ("TRIGGERED", I.mine(0, "triggered"))], 3, gap=12, zoom=3)
    blast = I.mine_blast(2, 40)
    ramp = I.blast_ramp(80)
    sc = pix.Scene(blast.width + 16, blast.height + 34, 3)
    sc.blit(blast, sc.w / 2, blast.height / 2 + 6)
    sc.blit(I.mine(0, "triggered"), sc.w / 2, blast.height / 2 + 6)
    ry = blast.height + 14
    sc.blit(ramp, sc.w / 2, ry, glow=0.6)
    label(sc, "FULL", sc.w / 2 - 40, ry + 6, centre=False)
    label(sc, "NONE", sc.w / 2 + 40 - pixfont.text_width("NONE"), ry + 6, centre=False)
    r.save("mine_blast", sc)

    def ship_with(level: int) -> Image.Image:
        body, flame = I.boost_parts(level, 0)
        return S._finish(body, OUTLINE, 0, flame)
    normal = S._finish(*ship_parts(6, ("W",), 0)[:1], OUTLINE, 0, S.player_flames(("W",), 0))
    r.board("boost_levels", [("NORMAL", S.tight(pix.pad(normal, (31, 45)))), ("BOOST 1", S.tight(ship_with(1))),
                             ("BOOST 2", S.tight(ship_with(2))), ("BOOST 3", S.tight(ship_with(3)))], 3, gap=8, zoom=2)

    def shielded(level: int) -> Image.Image:
        ship = S._finish(pix.pad(I.player_interior_loaded(6), (27, 27)), OUTLINE)
        bub = I.shield_bubble(level, 14, 0)
        out = pix.pad(bub, (max(bub.width, ship.width), max(bub.height, ship.height)))
        out.alpha_composite(pix.pad(ship, out.size))
        return out
    r.board("shield_levels", [("NONE", S.tight(S._finish(pix.pad(I.player_interior_loaded(6), (27, 27)), OUTLINE))),
                              ("LEVEL 1", shielded(1)), ("LEVEL 2", shielded(2)), ("LEVEL 3", shielded(3))], 3, gap=8, zoom=2)

    r.board("missile_pods", [(str(n), S.tight(S._finish(pix.pad(I.player_interior_loaded(n), (27, 27)), OUTLINE)))
                             for n in (6, 5, 4, 3, 1, 0)], 3, gap=6, zoom=3)

    r.board("console_early", [(None, hud.campaign_console(weapons=("auto",), current="auto", shield_level=0, armor_level=0,
                                                          boost_level=0, drills=1, mines=0, sentries=0, hull=1.0))], 3, hud_piece=True)
    r.board("console_mid", [(None, hud.campaign_console(weapons=("auto", "sniper", "missiles", "laser"), current="missiles",
                                                        ammo=0.6, missiles=4, shield_level=2, shield=0.55, hull=0.7,
                                                        armor_level=1, boost_level=2, boost=0.4, drills=2, mines=3,
                                                        sentries=1))], 3, hud_piece=True)
    icons = [("SHIELD", "shield"), ("ARMOR", "armor"), ("BOOST", "boost"), ("HEALTH", "repair"),
             ("SNIPER", "sniper"), ("MISSILES", "missiles"), ("LASER", "laser"), ("DRILL", "drill"), ("MINE", "mine"),
             ("SENTRIES", None)]
    pieces = []
    for text, kind in icons:
        if kind is None:
            trio = [S.tight(hud.item_icon(f"sentry_{k}")) for k in I.SENTRY_KINDS]
            img = Image.new("RGBA", (sum(t.width for t in trio) + 6, max(t.height for t in trio)), pix.CLEAR)
            x = 0
            for t in trio:
                img.alpha_composite(t, (x, img.height - t.height))
                x += t.width + 3
        else:
            img = hud.item_icon(kind)
        pieces.append((text, img))
    r.board("item_icons", pieces, 4, gap=8)
    r.board("upgrade_pane", [(None, station.boost_upgrade_pane())], 3, hud_piece=True)


# ---------------------------------------------------------------- animations

def anims(r: Review) -> None:
    k = 4
    rock = I.drained_rock(48, 106, 6, 0)

    # A drill filling up, stopping when full, then unloaded by your ship.
    frames, times = [], []
    W, H = 110, 76
    rxy = (40, 46)

    def drill_frame(fill: float, f: int, ship: tuple | None = None, flecks: list | None = None):
        sc = pix.Scene(W, H, k)
        sc.blit(rock, *rxy)
        place_drill(sc, rock, rxy, 60, fill, f, health=1.0)
        if ship is not None:
            body, fl = ship_parts(6, ship[2], f)
            sc.blit_smooth(body, ship[0], ship[1], angle=ship[3], outline=OUTLINE, overlay=fl)
        for (x, y) in flecks or []:
            sc.blit(pix.from_grid(["o"], {"o": "ore_hi"}), x, y)
        label(sc, "FULL - STOPPED" if fill >= 1 else ("UNLOADING" if flecks else "DRILLING"), W / 2, H - 9,
              "ore" if fill >= 1 else "hud_dim")
        return sc.render()

    for i in range(13):
        frames.append(drill_frame(i / 12, i)); times.append(220)
    for f in range(6):
        frames.append(drill_frame(1.0, f)); times.append(200)
    start, stop = (122, 20), (88, 30)
    for i in range(5):
        t = (i + 1) / 5
        x, y = start[0] + (stop[0] - start[0]) * t, start[1] + (stop[1] - start[1]) * t
        frames.append(drill_frame(1.0, i, ship=(x, y, ("S",) if i > 2 else ("W",), -105))); times.append(110)
    dx, dy = place_drill(pix.Scene(W, H, 1), rock, rxy, 60, 0, 0)
    for i in range(8):
        fill = 1 - (i + 1) / 8
        flecks = [(dx + (stop[0] - dx) * ((i * 0.3 + j * 0.33) % 1), dy + (stop[1] - dy) * ((i * 0.3 + j * 0.33) % 1))
                  for j in range(3)]
        frames.append(drill_frame(fill, i, ship=(stop[0], stop[1], (), -105), flecks=flecks)); times.append(110)
    for i in range(3):
        frames.append(drill_frame(0.0, i, ship=(stop[0] + i * 6, stop[1] - i * 3, ("W",), 60))); times.append(140)
    r.anim("drill_working", frames, times, (W * k, H * k))

    # An asteroid's life: two drills, cracks spreading, then it crumbles and takes the drills with it.
    k3 = 3
    W, H = 150, 120
    d, seed, ore = 64, 4242, 12
    rich = S.asteroid(d, seed, ore)
    sites = (25, 240)
    cracks = I.crack_points(rich, [drill_site(rich, a) for a in sites], 9)
    frames, times = [], []
    centre = (W / 2, H / 2 + 4)
    fills = [0.0, 0.3]

    def life_frame(st: int, f: int, text: str):
        sc = pix.Scene(W, H, k3)
        rk = I.drained_rock(d, seed, ore, st)
        rk.alpha_composite(I.crack_overlay(rk, cracks, st))
        sc.blit(rk, *centre)
        for a, fl in zip(sites, fills):
            place_drill(sc, rk, centre, a, fl, f)
        label(sc, text, W / 2, H - 10)
        return sc.render(), rk

    labels = ("FULL", "3/4 LEFT", "HALF LEFT", "1/4 LEFT")
    last_rock = None
    for st in range(4):
        for f in range(5):
            fills[0] = min(1.0, fills[0] + 0.12)
            fills[1] = min(1.0, fills[1] + 0.09)
            img, last_rock = life_frame(st, f, labels[st])
            frames.append(img); times.append(160)
        fills[0] = 0.15 if st % 2 == 0 else fills[0]
    # Crumble: compose the rock and drills into one sprite and break it apart.
    whole = pix.Scene(W, H, 1)
    whole.base = Image.new("RGBA", (W, H), pix.CLEAR)
    whole.blit(last_rock, *centre, glow=0)
    canvas = whole.base.copy()
    # Drills drawn upright-rotated into the sprite so they break with the rock.
    for a, fl in zip(sites, fills):
        rx, ry = I.rim_point(last_rock, a)
        cx = centre[0] - last_rock.width / 2 + rx + 0.5 + math.sin(math.radians(a)) * 5.0
        cy = centre[1] - last_rock.height / 2 + ry + 0.5 - math.cos(math.radians(a)) * 5.0
        dimg = S._finish(I.drill_interior(fl, 1), OUTLINE, a)
        canvas.alpha_composite(dimg, (int(round(cx - dimg.width / 2)), int(round(cy - dimg.height / 2))))
    box = canvas.getbbox()
    sprite = canvas.crop(box)
    bits = I.shatter(sprite, 9, 12, seed=4, speed=1.6)
    ox = box[0] + sprite.width / 2
    oy = box[1] + sprite.height / 2
    for f, bit in enumerate(bits):
        sc = pix.Scene(W, H, k3)
        if f == 0:
            sc.blit(sprite, ox, oy)
        else:
            sc.blit(bit, ox, oy)
        label(sc, "EMPTY - IT CRUMBLES", W / 2, H - 10, "hud_text")
        frames.append(sc.render()); times.append(260 if f == 0 else 110)
    sc = pix.Scene(W, H, k3)
    label(sc, "DRILLS USED UP", W / 2, H - 10)
    frames.append(sc.render()); times.append(900)
    r.anim("asteroid_life", frames, times, (W * k3, H * k3))

    # Sentries tracking an enemy and firing their own shots.
    W, H = 180, 104
    frames, times = [], []
    posts = [("auto", 1, (36, 72)), ("sniper", 2, (90, 78)), ("missile", 3, (144, 72))]
    for f in range(24):
        sc = pix.Scene(W, H, k)
        ex, ey = 14 + f * 7, 20 + 5 * math.sin(f / 3)
        alive = f < 21
        for kind, tier, (x, y) in posts:
            aim = mockups.heading((x, y), (ex, ey))
            sc.blit(I.sentry_base(tier, f // 3), x, y)
            firing = (kind == "auto" and f % 2 == 0) or (kind == "sniper" and f % 8 == 3) or (kind == "missile" and f % 12 == 5)
            sc.blit_smooth(I.turret_interior(kind, firing and alive, loaded=3), x, y, angle=aim, outline=OUTLINE)
            sc.blit(I.struct_bar(I.SENTRY_HEALTH_BAR[tier], 1.0 if kind != "auto" else 0.6), x, y - 14, glow=0.3)
            if not alive:
                continue
            if kind == "auto":
                for j in range(3):
                    t = ((f % 2) + j * 2) / 6
                    sc.blit_smooth(I.sentry_shot("auto"), x + (ex - x) * t, y + (ey - y) * t, angle=aim)
            elif kind == "sniper" and f % 8 in (3, 4):
                t = 0.35 if f % 8 == 3 else 0.75
                sc.blit_smooth(I.sentry_shot("sniper"), x + (ex - x) * t, y + (ey - y) * t, angle=aim)
            elif kind == "missile" and 5 <= f % 12 <= 10:
                t = (f % 12 - 4) / 7
                mx, my = x + (ex - x) * t + 10 * math.sin(t * 3), y + (ey - y) * t
                sc.blit_smooth(I.sentry_shot("missile", f), mx, my, angle=mockups.heading((x, y), (ex, ey)))
        if alive:
            sc.blit(S.infantry(f % 2, angle=90), ex, ey)
        elif f - 21 < 3:
            sc.blit(S.explosion(min(5, (f - 21) * 2), "enemy", seed=3), ex, ey)
        label(sc, "AUTO T1", 36, H - 10)
        label(sc, "SNIPER T2", 90, H - 10)
        label(sc, "MISSILE T3", 144, H - 10)
        frames.append(sc.render()); times.append(110)
    r.anim("sentries_firing", frames, times, (W * k, H * k))

    # Laying mines: a line while flying, a pile while holding still, then an enemy sets one off.
    W, H = 230, 120
    frames, times = [], []
    laid: list[tuple[float, float, int]] = []
    path = [(30 + i * 9, 80) for i in range(12)] + [(129, 80)] * 6 + [(129 + i * 7, 80) for i in range(1, 6)]
    for f, (x, y) in enumerate(path):
        if f % 2 == 0 and f < 18:
            jitter = (0, 0) if f < 12 else ((f % 3) - 1, (f % 4) - 1.5)
            laid.append((x - 10 + jitter[0] * 2, y + 2 + jitter[1] * 2, f))
        sc = pix.Scene(W, H, k3)
        for mx, my, born in laid:
            sc.blit(I.mine(f, "armed" if f - born > 2 else "laid"), mx, my)
        body, fl = ship_parts(6, ("W",) if (f < 12 or f >= 18) else (), f)
        sc.blit_smooth(body, x, y, angle=90, outline=OUTLINE, overlay=fl)
        text = "HOLD G: FLY FOR A LINE" if f < 12 else ("HOLD STILL FOR A PILE" if f < 18 else "UP TO 5 CARRIED")
        label(sc, text, W / 2, H - 10)
        frames.append(sc.render()); times.append(140)
    ship_x = path[-1][0]
    target = laid[2]
    for f in range(17):
        sc = pix.Scene(W, H, k3)
        ex, ey = target[0] - 56 + f * 8, target[1] - 56 + f * 8
        boom = f >= 8
        for i, (mx, my, born) in enumerate(laid):
            if boom and i == 2:
                continue
            state = "triggered" if (i == 2 and f >= 6) else "armed"
            sc.blit(I.mine(f, state), mx, my)
        body, fl = ship_parts(6, (), f)
        sc.blit_smooth(body, ship_x, 80, angle=90, outline=OUTLINE, overlay=fl)
        if not boom:
            sc.blit(S.infantry(f % 2, angle=135), ex, ey)
        else:
            bf = f - 8
            if bf < 6:
                sc.blit(I.mine_blast(bf, 34), target[0], target[1], glow=1.0)
            if bf < 3:
                sc.blit(S.explosion(min(5, bf * 2), "enemy", seed=2), target[0], target[1])
        text = "AN ENEMY FLIES RIGHT OVER ONE" if not boom else "BIG BLAST, DAMAGE FADES TO THE EDGE"
        label(sc, text, W / 2, H - 10, "hud_dim" if not boom else "hud_text")
        frames.append(sc.render()); times.append(120 if not boom else 130)
    r.anim("mines", frames, times, (W * k3, H * k3))

    laser_anims(r)
    boost_anim(r)
    shield_anim(r)
    missile_anim(r)


def _charges(sc: pix.Scene, n: int, x: float, y: float) -> None:
    label(sc, "CHARGES", x, y, centre=False)
    sc.blit(hud.level_pips(n, 3, size=4, gap=2, color="ion_hi"), x + 46, y + 2, center=False, hud=True)


def laser_anims(r: Review) -> None:
    k = 3
    W, H = 200, 150
    ship = (100, 108)
    targets = [(50, 30), (80, 22), (112, 18), (146, 26)]
    beam_len = 120

    def frame(t: float, angle: float, f: int, charges: int, text: str, color: str = "hud_dim",
              beam: int | None = None, dead: dict | None = None, cancel: float = 0.0, burst_fade: float = 1.0,
              hint: str = ""):
        sc = pix.Scene(W, H, k)
        for i, (tx, ty) in enumerate(targets):
            if dead and i in dead:
                age = dead[i]
                if age < 6:
                    sc.blit(S.explosion(age, "enemy", seed=i + 2), tx, ty)
                continue
            sc.blit(S.infantry(f % 2, angle=180), tx, ty)
        if hint:
            label(sc, hint, 6, 4, "hud_dim", centre=False)
        a = math.radians(angle)
        if beam is not None:
            nose = (ship[0] + math.sin(a) * 9, ship[1] - math.cos(a) * 9)
            img = I.laser_burst(beam_len, beam)
            mid = (nose[0] + math.sin(a) * beam_len / 2, nose[1] - math.cos(a) * beam_len / 2)
            sc.blit_smooth(img, *mid, angle=angle, alpha=burst_fade)
            if beam < 2:
                sc.blit(E.flare("player", 0), *nose)
                sc.blit(E.shockwave(6 + beam * 5, "player", beam / 3), *nose)
        body, fl = ship_parts(6, (), f)
        sc.blit_smooth(body, ship[0], ship[1], angle=angle, outline=OUTLINE, overlay=fl)
        if beam is None and (t > 0 or cancel > 0):
            I.draw_laser_charge(sc, ship[0], ship[1], angle, t, f, cancel=cancel)
        _charges(sc, charges, 6, H - 22)
        label(sc, text, 6, H - 11, color, centre=False)
        return sc.render()

    def charge_frames(start_angle: float, end_angle: float, upto: float = 1.0):
        out = []
        n = 16
        for i in range(n + 1):
            t = i / n
            if t > upto + 1e-6:
                break
            ang = start_angle + (end_angle - start_angle) * min(1.0, t * 1.3)
            secs = 2.0 * t
            out.append((t, ang, i, f"CHARGING {secs:.1f} S"))
        return out

    def hit_check(angle: float, dead: dict) -> None:
        """Enemies the beam touches start exploding; `dead` maps each to its explosion frame."""
        a = math.radians(angle)
        for i in dead:
            dead[i] += 1
        for i, (tx, ty) in enumerate(targets):
            vx, vy = tx - ship[0], ty - ship[1]
            along = vx * math.sin(a) - vy * math.cos(a)
            across = abs(vx * math.cos(a) + vy * math.sin(a))
            if 0 < along < beam_len + 10 and across < 7 and i not in dead:
                dead[i] = 0

    # Option A: the charged beam lasts as long as it does today, and you can sweep it.
    hint = "TURN TO AIM - YOU CAN'T MOVE"
    frames, times = [], []
    for f in range(2):
        frames.append(frame(0, -40, f, 3, "HOLD FIRE TO CHARGE")); times.append(300)
    for t, ang, i, text in charge_frames(-40, -32):
        frames.append(frame(t, ang, i, 3, text, "hud_text" if t >= 1 else "hud_dim", hint=hint)); times.append(125)
    frames.append(frame(1.0, -32, 0, 3, "READY", "ion_hi", hint=hint)); times.append(160)
    dead: dict = {}
    for j in range(14):
        ang = -32 + j * 5.2
        hit_check(ang, dead)
        frames.append(frame(0, ang, j, 2, "BURST - SWEEP IT WHILE IT LASTS", "ion_hi", beam=j, dead=dict(dead)))
        times.append(105)
    for j in range(4):
        hit_check(1000, dead)
        frames.append(frame(0, 40, j, 2, "", dead=dict(dead))); times.append(200 if j < 3 else 700)
    r.anim("laser_a", frames, times, (W * k, H * k))

    # Option B: everything goes out in one short, powerful blast.
    frames, times = [], []
    for f in range(2):
        frames.append(frame(0, -2, f, 3, "HOLD FIRE TO CHARGE")); times.append(300)
    for t, ang, i, text in charge_frames(-2, 4):
        frames.append(frame(t, ang, i, 3, text, "hud_text" if t >= 1 else "hud_dim", hint=hint)); times.append(125)
    frames.append(frame(1.0, 4, 0, 3, "READY", "ion_hi", hint=hint)); times.append(160)
    dead = {}
    for j, fade in enumerate((1.0, 1.0, 1.0, 0.7, 0.4, 0.15)):
        hit_check(4, dead)
        frames.append(frame(0, 4, j, 2, "ONE BIG BLAST", "ion_hi", beam=min(j, 2), dead=dict(dead),
                            burst_fade=fade)); times.append(90)
    for j in range(4):
        hit_check(1000, dead)
        frames.append(frame(0, 4, j, 2, "", dead=dict(dead))); times.append(200 if j < 3 else 700)
    r.anim("laser_b", frames, times, (W * k, H * k))

    # Letting go early cancels it, and no charge is used.
    frames, times = [], []
    for t, ang, i, text in charge_frames(-10, -4, upto=0.56):
        frames.append(frame(t, ang, i, 3, text, hint=hint)); times.append(125)
    for j in range(6):
        frames.append(frame(0.56, -4, j, 3, "LET GO EARLY - CANCELLED", "hud_text", cancel=(j + 1) / 6)); times.append(110)
    for j in range(2):
        frames.append(frame(0, -4, j, 3, "NO CHARGE USED", "ion_hi")); times.append(500)
    r.anim("laser_cancel", frames, times, (W * k, H * k))


def boost_anim(r: Review) -> None:
    k = 4
    W, H = 180, 92
    frames, times = [], []
    # Hold for 1.2 s, the meter drains; let go, a 2 s pause, then it refills.
    plan = [("hold", i) for i in range(10)] + [("pause", i) for i in range(10)] + [("refill", i) for i in range(6)]
    meter = 1.0
    rng = pix.seeded(5)
    stars = [(rng.uniform(0, W), rng.uniform(0, H - 20)) for _ in range(30)]
    for step, (state, i) in enumerate(plan):
        if state == "hold":
            meter = max(0.0, 1 - (i + 1) / 10)
        elif state == "refill":
            meter = min(1.0, (i + 1) / 6)
        sc = pix.Scene(W, H, k)
        for level, x in ((1, 32), (2, 90), (3, 148)):
            speed = (1.2, 1.4, 1.8)[level - 1] if state == "hold" else 1.0
            for j, (sx, sy) in enumerate(stars):
                yy = (sy + step * 3 * speed) % (H - 22)
                if abs(sx - x) < 20:
                    streak = 1 + int(speed * 2 if state == "hold" else 0)
                    for s in range(streak):
                        sc.blit(pix.from_grid(["s"], {"s": "star_dim"}), sx, yy - s, glow=0)
            if state == "hold":
                body, fl = I.boost_parts(level, step)
            else:
                body = pix.pad(I.player_interior_loaded(6), (I.BOOST_CANVAS, I.BOOST_CANVAS))
                fl = pix.pad(S.player_flames(("W",), step), (I.BOOST_CANVAS, I.BOOST_CANVAS))
            sc.blit_smooth(body, x, 34, angle=0, outline=OUTLINE, overlay=fl)
            sc.blit(hud.bar(30, meter, "ion_hi", "console_mid"), x, 66, glow=0.2, hud=True)
            label(sc, f"BOOST {level}", x, 72)
        text = {"hold": "HOLD SHIFT", "pause": "LET GO - A SHORT PAUSE", "refill": "RECHARGING"}[state]
        label(sc, text, W / 2, H - 9, "hud_text" if state == "hold" else "hud_dim")
        frames.append(sc.render()); times.append(120)
    r.anim("boost", frames, times, (W * k, H * k))


def shield_anim(r: Review) -> None:
    k = 4
    W, H = 180, 90
    frames, times = [], []
    breaks_after = {1: 2, 2: 4, 3: 99}
    hits = [3, 7, 11, 15, 19, 23]
    for f in range(28):
        sc = pix.Scene(W, H, k)
        for level, x in ((1, 32), (2, 90), (3, 148)):
            y = 48
            landed = [h for h in hits if h <= f]
            broken_at = hits[breaks_after[level] - 1] if breaks_after[level] <= len(hits) else None
            sc.blit(S._finish(pix.pad(I.player_interior_loaded(6), (27, 27)), OUTLINE), x, y)
            for h in hits:
                if h - 3 < f < h:
                    t = (f - (h - 3)) / 3
                    sc.blit(S.shot_infantry(f % 2), x, 6 + (y - 20) * t)
            if landed and f - landed[-1] < 3:
                if broken_at is not None and landed[-1] >= broken_at:
                    if landed[-1] == broken_at:
                        sc.blit(E.shield_break(14, f - landed[-1]), x, y)
                    else:
                        sc.blit(S.armor_hit(f - landed[-1]), x + 2, y - 4)
                else:
                    sc.blit(I.shield_bubble(level, 14, f), x, y)
                    sc.blit(S.shield_hit(f - landed[-1]), x, y)
            elif broken_at is not None and landed and landed[-1] == broken_at and f - landed[-1] < 4:
                sc.blit(E.shield_break(14, f - landed[-1]), x, y)
            up = broken_at is None or f < broken_at
            label(sc, f"LEVEL {level}" if up else "BROKEN", x, 72, "hud_text" if up else "danger_pink")
        label(sc, "THE SAME HITS ON EACH", W / 2, H - 9)
        frames.append(sc.render()); times.append(110)
    r.anim("shields", frames, times, (W * k, H * k))


def missile_anim(r: Review) -> None:
    k = 6
    W, H = 110, 74
    frames, times = [], []
    ship = (40, 46)
    flying: list[tuple[int, int]] = []        # (launch frame, side)
    left = 6
    timeline = []
    for f in range(30):
        if f in (4, 8, 12, 16, 20, 24) and left > 0:
            side = 0 if (6 - left) % 2 == 0 else 1
            flying.append((f, side))
            left -= 1
        timeline.append(left)
    for f in range(36):
        n = timeline[min(f, len(timeline) - 1)]
        if f >= 31:
            n = 6
        sc = pix.Scene(W, H, k)
        body, fl = ship_parts(n, (), f)
        sc.blit_smooth(body, *ship, angle=0, outline=OUTLINE, overlay=fl)
        for launch, side in flying:
            age = f - launch
            if 0 <= age < 9 and f < 31:
                x = ship[0] + (-6 if side == 0 else 6)
                y = ship[1] - 6 - age * age * 0.9
                if y > -10:
                    sc.blit(S.missile_player(f), x, y)
        slot = hud.campaign_console(weapons=("auto", "missiles"), current="missiles", missiles=n,
                                    ammo=1.0 if n else 0.0).crop((128 - 26, 10, 128, 36))
        sc.blit(slot, 86, 38, hud=True)
        label(sc, "CLICK: ONE MISSILE" if f < 31 else "BOUGHT 6 MORE", W / 2, H - 10,
              "hud_dim" if f < 31 else "ore")
        frames.append(sc.render()); times.append(110 if f < 31 else 300)
    r.anim("missiles", frames, times, (W * k, H * k))


# ---------------------------------------------------------------- mock screenshots

def station_mock(page: str) -> pix.Scene:
    sc = pix.Scene()
    sc.blit(mockups.space_backdrop(seed=31), 0, 0, center=False)
    mockups.scatter_asteroids(sc, 12, 10, [(0, 100, 230, 300), (220, 0, 640, 360)], sizes=(8, 10, 12, 16))
    base = (112, 196)
    sc.blit(S.home_base(0), *base)
    body, fl = ship_parts(4, (), 0)
    sc.blit_smooth(body, base[0] + 18, base[1] - 18, angle=45, outline=OUTLINE, overlay=fl)
    label(sc, "DOCKED", base[0], base[1] + 40, "ion_hi")
    if page == "tools":
        for i, (x, y) in enumerate(((40, 60), (54, 52), (26, 52), (68, 44), (12, 44))):
            sc.blit(S.infantry(i % 2, angle=135), x, y)
        hud.place_edge_arrow(sc, (-200, -80), "alien_green_hi", centre=(112, 196))
    panel = station.page_panel(page)
    sc.blit(panel, 640 - panel.width - 6, 40, center=False, hud=True)
    if page == "tools":
        _top(sc, state="SPOTTED", state_color="danger_pink_hi")
    else:
        _top(sc)
    return sc


def _top(sc: pix.Scene, wave: str = "WAVE 4", state: str = "HIDDEN", state_color: str = "alien_green_hi",
         ore: str = "36/120", credits: str | None = None) -> None:
    left = hud.panel(116, 15)
    left.alpha_composite(pixfont.render("KILLS", "hud_dim"), (5, 4))
    left.alpha_composite(pixfont.render("23", "ore"), (37, 4))
    left.alpha_composite(pixfont.render("LEFT", "hud_dim"), (60, 4))
    left.alpha_composite(pixfont.render("2", "alien_green_hi"), (86, 4))
    sc.blit(left, 6, 6, center=False, hud=True)
    a = pixfont.render(wave, "hud_text")
    b = pixfont.render(state, state_color)
    mid = hud.panel(a.width + b.width + 22, 15)
    mid.alpha_composite(a, (6, 4))
    mid.alpha_composite(b, (a.width + 16, 4))
    sc.blit(mid, (640 - mid.width) // 2, 6, center=False, hud=True)
    if credits is not None:
        right = hud.panel(122, 15)
        right.alpha_composite(pixfont.render("ORE", "hud_dim"), (5, 4))
        right.alpha_composite(pixfont.render(ore, "ore"), (26, 4))
        right.alpha_composite(pixfont.render("CR", "hud_dim"), (76, 4))
        right.alpha_composite(pixfont.render(credits, "ore"), (90, 4))
        sc.blit(right, 640 - 6 - 122, 6, center=False, hud=True)


def in_game_mock() -> pix.Scene:
    sc = pix.Scene()
    sc.blit(mockups.space_backdrop(seed=41), 0, 0, center=False)
    keep = [(90, 120, 330, 330), (20, 60, 150, 190), (260, 80, 520, 290), (430, 230, 640, 360), (0, 290, 140, 360),
            (180, 0, 470, 30), (0, 0, 130, 30), (510, 0, 640, 30), (0, 336, 640, 360)]
    mockups.scatter_asteroids(sc, 21, 16, keep, sizes=(8, 10, 12, 14, 18))

    # The big rock: two drills sharing it, half its ore gone.
    d, seed, ore = 92, 4242, 16
    rich = S.asteroid(d, seed, ore)
    sites = (35, 300)
    cracks = I.crack_points(rich, [drill_site(rich, a) for a in sites], 9)
    rock = I.drained_rock(d, seed, ore, 2)
    rock.alpha_composite(I.crack_overlay(rock, cracks, 2))
    big = (205, 236)
    sc.blit(rock, *big)
    place_drill(sc, rock, big, 35, 1.0, 1, health=0.9)
    place_drill(sc, rock, big, 300, 0.4, 0, health=1.0)

    # A worked-out rock crumbling away with its drill.
    small_d, small_seed = 44, 77
    srock = I.drained_rock(small_d, small_seed, 4, 3)
    scr = I.crack_points(srock, [drill_site(srock, 120)], 3)
    srock.alpha_composite(I.crack_overlay(srock, scr, 3))
    whole = Image.new("RGBA", (srock.width + 30, srock.height + 30), pix.CLEAR)
    whole.alpha_composite(srock, (15, 15))
    rx, ry = I.rim_point(srock, 120)
    dimg = S._finish(I.drill_interior(0.7, 1), OUTLINE, 120)
    cx = 15 + rx + math.sin(math.radians(120)) * 5.0
    cy = 15 + ry - math.cos(math.radians(120)) * 5.0
    whole.alpha_composite(dimg, (int(cx - dimg.width / 2), int(cy - dimg.height / 2)))
    bits = I.shatter(S.tight(whole), 9, 6, seed=8, speed=1.3)
    sc.blit(bits[3], 82, 118)

    # A small rock with a fresh drill.
    tiny = I.drained_rock(30, 812, 3, 0)
    sc.blit(tiny, 356, 318)
    place_drill(sc, tiny, (356, 318), 330, 0.15, 0, health=1.0)

    # Infantry coming down from the top right, into the sentries and the mine line.
    raiders = [(470, 72), (494, 84), (446, 84), (518, 96), (422, 96)]
    for i, (x, y) in enumerate(raiders):
        if i == 2:
            continue
        sc.blit(S.infantry(i % 2, angle=225), x, y)
    # Sentries with their own shots.
    posts = [("auto", 1, (300, 170), raiders[4]), ("sniper", 2, (262, 116), raiders[0]), ("missile", 3, (344, 214), raiders[3])]
    for kind, tier, (x, y), tgt in posts:
        aim = mockups.heading((x, y), tgt)
        sc.blit(I.sentry_base(tier, 0), x, y)
        sc.blit_smooth(I.turret_interior(kind, True, loaded=2), x, y, angle=aim, outline=OUTLINE)
        sc.blit(I.struct_bar(I.SENTRY_HEALTH_BAR[tier], 0.75 if kind == "auto" else 1.0), x, y - 14, glow=0.3)
        if kind == "auto":
            for t in (0.25, 0.45, 0.65):
                sc.blit_smooth(I.sentry_shot("auto"), x + (tgt[0] - x) * t, y + (tgt[1] - y) * t, angle=aim)
        elif kind == "sniper":
            sc.blit_smooth(I.sentry_shot("sniper"), x + (tgt[0] - x) * 0.55, y + (tgt[1] - y) * 0.55, angle=aim)
        else:
            mx, my = x + (tgt[0] - x) * 0.5 + 12, y + (tgt[1] - y) * 0.5
            mockups.trail(sc, mockups.along((x, y), (mx, my), np.linspace(0.15, 0.95, 26)),
                          colors=("ion_hi", "ion", "ion_dark", "ion_dark"))
            sc.blit_smooth(I.sentry_shot("missile", 0), mx, my, angle=mockups.heading((x, y), (mx, my)))
    # Enemy fire at the sentries.
    for (x, y), (tx, ty) in zip(raiders[:2], [(300, 170), (262, 116)]):
        for t in (0.3, 0.55):
            sc.blit(S.shot_infantry(int(t * 10) % 2), x + (tx - x) * t, y + (ty - y) * t)

    # A mine line across their path. The far end just went off under an enemy.
    for i in range(4):
        sc.blit(I.mine(i, "armed"), 396 + i * 15, 150 - i * 7)
    sc.blit(I.mine_blast(3, 30), 456, 122, glow=0.7)
    sc.blit(S.explosion(3, "enemy", seed=6), 458, 118)

    # You, boosting back toward the drills with the shield just hit.
    me = (430, 244)
    aim = mockups.heading(me, (300, 200))
    body, fl = I.boost_parts(2, 0, missiles=3)
    sc.blit_smooth(body, *me, angle=aim, outline=OUTLINE, overlay=fl)
    sc.blit(I.shield_bubble(2, 14, 2), *me)

    # Off-screen pointers: home base and a drill under attack.
    hud.place_edge_arrow(sc, (-500, 380), "ion_hi", label="BASE")
    marker = hud.drill_marker(200, 0.35, 0.8, hit=True)
    sc.blit(marker, 8, 300, center=False, hud=True, alpha=0.95)

    _top(sc, wave="WAVE 4", state="SPOTTED", state_color="danger_pink_hi", credits="1,240")
    con = hud.campaign_console(weapons=("auto", "sniper", "missiles"), current="auto", missiles=3,
                               shield_level=2, shield=0.55, hull=0.8, armor_level=1, boost_level=2, boost=0.45,
                               drills=0, mines=1, sentries=0)
    sc.blit(con, 640 - con.width - 6, 360 - con.height - 16, center=False, hud=True)
    x = 8
    for key, word in (("WASD", "FLY"), ("CLICK", "FIRE"), ("SHIFT", "BOOST"), ("F", "DRILL"), ("G", "MINES"),
                      ("R", "SENTRY"), ("1-4", "WEAPON")):
        k_ = pixfont.render(key, "hud_text")
        w_ = pixfont.render(word, "hud_dim")
        sc.blit(k_, x, 349, center=False, glow=0, hud=True)
        sc.blit(w_, x + k_.width + 4, 349, center=False, glow=0, hud=True)
        x += k_.width + w_.width + 14
    return sc


def mocks(r: Review) -> None:
    for page in station.PAGES:
        sc = station_mock(page)
        sc.render().save(r.dest / "mock" / f"station_{page}.png", optimize=True)
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
    from . import review_page6
    print(review_page6.build(out))
