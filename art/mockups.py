"""Mock screenshots that show how the art looks together in a real fight."""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from . import hud, pix, sprites as S
from .palette import rgba


# ---------------------------------------------------------------- backdrop

def space_backdrop(w: int = 640, h: int = 360, seed: int = 7) -> Image.Image:
    """Deep space with dithered violet and teal nebulae and three layers of stars."""
    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[:] = rgba("space")
    violet = pix.value_noise(w, h, 64, seed) * 0.65 + pix.value_noise(w, h, 22, seed + 1) * 0.35
    teal = pix.value_noise(w, h, 80, seed + 2) * 0.7 + pix.value_noise(w, h, 26, seed + 3) * 0.3
    vl = pix.dither_levels(np.clip((violet - 0.56) * 3.0, 0, 1), 3)
    tl = pix.dither_levels(np.clip((teal - 0.6) * 3.2, 0, 1), 3)
    out[tl == 1] = rgba("nebula_teal")
    out[tl == 2] = rgba("nebula_teal_hi")
    out[vl == 1] = rgba("nebula_violet")
    out[vl == 2] = rgba("nebula_violet_hi")
    img = Image.fromarray(out).copy()
    px = img.load()
    rng = pix.seeded(seed)
    for _ in range(int(w * h / 260)):
        px[rng.randrange(w), rng.randrange(h)] = rgba("star_dim")
    for _ in range(int(w * h / 1400)):
        px[rng.randrange(w), rng.randrange(h)] = rgba("star_mid")
    for _ in range(int(w * h / 9000)):
        x, y = rng.randrange(2, w - 2), rng.randrange(2, h - 2)
        px[x, y] = rgba("star_bright")
        if rng.random() < 0.5:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                px[x + dx, y + dy] = rgba("star_mid")
    return img


def scatter_asteroids(scene: pix.Scene, seed: int, count: int, keep_clear: list[tuple[int, int, int, int]],
                      sizes=(8, 10, 12, 14, 18, 22), band=None) -> None:
    rng = pix.seeded(seed)
    placed = 0
    tries = 0
    while placed < count and tries < count * 40:
        tries += 1
        x, y = rng.uniform(0, scene.w), rng.uniform(0, scene.h)
        if band and not band(x, y):
            continue
        if any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in keep_clear):
            continue
        d = rng.choice(sizes)
        scene.blit(S.asteroid(d, rng.randrange(10_000), ore=rng.choice([0, 0, 0, 1, 2])), x, y)
        placed += 1


def surface_y(img: Image.Image, x: int) -> int:
    """Top-most solid pixel in a column of a sprite."""
    a = np.array(img)[:, :, 3]
    col = np.where(a[:, x] > 0)[0]
    return int(col[0]) if len(col) else img.height // 2


# ---------------------------------------------------------------- effects drawn in scene space

def ram_lane(scene: pix.Scene, p0, p1, frame: int = 0) -> None:
    """A guard's dash warning from p0 to p1: the lane sprite, turned to face the target."""
    L = int(math.hypot(p1[0] - p0[0], p1[1] - p0[1]))
    mid = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
    scene.blit_smooth(S.ram_warning(L, frame), *mid, angle=heading(p0, p1), glow=0.5)


def trail(scene: pix.Scene, points, colors=("danger_pink_hi", "danger_pink", "danger_red", "danger_dark")) -> None:
    d = ImageDraw.Draw(scene.base)
    n = len(points)
    for i, (x, y) in enumerate(points):
        col = colors[min(len(colors) - 1, int(i / max(1, n) * len(colors)))]
        d.point((round(x), round(y)), fill=rgba(col))
        if i % 3 == 0:
            scene.light[int(round(y)) % scene.h, int(round(x)) % scene.w] = np.array(rgba(col)[:3]) / 255 * 0.5


def along(p0, p1, ts):
    return [(p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t) for t in ts]


def heading(p0, p1) -> float:
    """Clockwise degrees from straight up, for a sprite moving from p0 to p1."""
    return math.degrees(math.atan2(p1[0] - p0[0], -(p1[1] - p0[1])))


# ---------------------------------------------------------------- HUD placement

def place_hud(scene: pix.Scene, console_kwargs: dict, blips, alert: str | None = None, wave: int = 7,
              next_wave: str = "0:42") -> None:
    for img, x, y in hud.top_bar(wave=wave, next_wave=next_wave, alert=alert):
        scene.blit(img, x, y, center=False, hud=True)
    con = hud.ship_console(**console_kwargs)
    scene.blit(con, scene.w - con.width - 6, scene.h - con.height - 6, center=False, hud=True)
    rad = hud.radar(blips)
    scene.blit(rad, 6, scene.h - rad.height - 4, center=False, hud=True)


# ---------------------------------------------------------------- scene 1: defending the drill

def defend_the_drill() -> pix.Scene:
    sc = pix.Scene()
    sc.blit(space_backdrop(seed=11), 0, 0, center=False)

    # Belt asteroids, kept away from the main action.
    clear = [(95, 160, 360, 300), (380, 40, 520, 150), (520, 180, 640, 270), (40, 40, 110, 100),
             (0, 260, 100, 360), (500, 255, 640, 360), (180, 0, 470, 30)]
    scatter_asteroids(sc, 5, 22, clear, band=lambda x, y: abs((y - 40) - x * 0.42) < 120)
    sc.blit(S.asteroid(30, 812, ore=3), 548, 132)
    sc.blit(S.asteroid(26, 77, ore=0), 60, 150)

    # The mined asteroid with a drill on top.
    rock = S.asteroid(92, 4242, ore=16)
    rx, ry = 150, 252
    sc.blit(rock, rx, ry)
    rock_left = rx - rock.width // 2
    top = surface_y(rock, rock.width // 2 + 6)
    drill = S.drill(0)
    sc.blit(drill, rx + 6, ry - rock.height // 2 + top - drill.height // 2 + 3)

    # Safe zone and a shield powerup from the friendly faction.
    sc.blit(S.safe_zone(38, 2), 270, 320, alpha=0.95, glow=0.5)
    sc.blit(S.powerup("shield", 0), 372, 288)

    # Enemy tank (top left) with homing missiles, one shot down by the sentry.
    sc.blit(S.tank(0, angle=90), 66, 70)
    m1 = (238, 152)
    trail(sc, along((92, 70), (230, 146), np.linspace(0.08, 0.92, 70)) )
    sc.blit_smooth(S.missile_enemy(0), *m1, angle=heading((180, 118), m1))
    sc.blit(S.explosion(2, "danger", seed=8), 168, 104)
    trail(sc, along((92, 74), (160, 102), np.linspace(0.1, 0.9, 30)))

    # Sentry beside the drill, firing at the missile.
    sentry_pos = (214, 186)
    aim = heading(sentry_pos, m1)
    sc.blit_smooth(S.sentry_interior(firing=True), *sentry_pos, angle=aim, outline="hull_outline")
    for p in along(sentry_pos, m1, (0.35, 0.6)):
        sc.blit_smooth(S.shot_auto(), *p, angle=aim)

    # Infantry formation coming down from the top right, one just destroyed.
    form = [(452, 66), (437, 77), (467, 77), (422, 88), (482, 88), (407, 99), (497, 99)]
    for i, (x, y) in enumerate(form):
        if i == 4:
            sc.blit(S.explosion(2, "enemy", seed=5), x, y)
            continue
        sc.blit(S.infantry(i % 2, angle=180), x, y)
    for (x, y), (tx, ty) in zip(form[:4], [(330, 220), (300, 230), (345, 210), (190, 220)]):
        for t in (0.18, 0.42):
            px_, py_ = x + (tx - x) * t, y + (ty - y) * t
            sc.blit(S.shot_infantry(int(t * 10) % 2), px_, py_)

    # Guard wall in front of the formation; the middle guard is about to ram the player.
    player = (318, 222)
    guards = [(426, 126), (444, 130), (462, 126)]
    ram_lane(sc, (guards[1][0] - 7, guards[1][1] + 7), (player[0] + 13, player[1] - 11), frame=0)
    for i, (x, y) in enumerate(guards):
        sc.blit(S.guard(0, charging=(i == 1), angle=180), x, y)
    sc.blit(S.explosion(3, "player", seed=12), 474, 142)

    # Rapid assault darts cutting in from the right.
    for (x, y) in ((582, 206), (600, 232), (566, 248)):
        sc.blit(S.rapid_assault(0, angle=270), x, y)
        for dx in (24, 44):
            sc.blit(S.shot_rapid().rotate(90, expand=True), x - dx, y)

    # The player: strafing left while thrusting, firing at the formation, shield taking a hit.
    aim_p = heading(player, (430, 95))
    body, flames = S.player_parts(("W", "A"), 0)
    sc.blit_smooth(body, *player, angle=aim_p, outline="hull_outline", overlay=flames)
    for dist in (20, 36, 52, 68, 84, 100):
        bx = player[0] + math.sin(math.radians(aim_p)) * dist
        by = player[1] - math.cos(math.radians(aim_p)) * dist
        sc.blit_smooth(S.shot_auto(), bx, by, angle=aim_p)
    sc.blit_smooth(S.shield_hit(0), *player, angle=heading(player, (352, 190)))

    # Off-screen pointers.
    hud.place_edge_arrow(sc, (760, 200), "alien_green_hi")
    hud.place_edge_arrow(sc, (560, -60), "alien_green_hi")
    hud.place_edge_arrow(sc, (-400, 300), "ion_hi", label="BASE")

    blips = [(14, -18, "enemy"), (17, -19, "enemy"), (20, -16, "enemy"), (24, 2, "enemy"), (26, 5, "enemy"),
             (-21, -17, "enemy"), (30, -26, "boss"), (-30, 24, "base"), (-15, 4, "drill"), (-34, -8, "drill"),
             (36, 10, "enemy"), (-14, -9, "danger")]
    place_hud(sc, dict(shield=0.45, hull=0.82, armor_level=2, weapon="auto", ammo=1.0), blips)
    return sc


# ---------------------------------------------------------------- scene 2: the mothership

def mothership_assault() -> pix.Scene:
    sc = pix.Scene()
    sc.blit(space_backdrop(seed=23), 0, 0, center=False)
    clear = [(200, 0, 460, 360)]
    scatter_asteroids(sc, 9, 12, clear, sizes=(8, 10, 12, 16, 20, 28))

    ms = S.mothership(1, laser_charge=0.85)
    mx, my = 330, 112
    sc.blit(ms, mx, my)
    left, top = mx - ms.width // 2, my - ms.height // 2
    # Emitter position inside the sprite (outline adds 1px).
    ex, ey = left + 1 + (220 - 1) / 2, top + 1 + 160 - 24

    # Laser telegraph down the lane below the emitter.
    lane = S.laser_warning(int(sc.h - ey - 12), frame=0)
    sc.blit(lane, ex, ey + 12 + lane.height / 2, glow=0.6)

    # Turret fire.
    turrets = [(left + 1 + 110 - 86, top + 1 + 42 + 10), (left + 1 + 110 + 86, top + 1 + 42 + 10),
               (left + 1 + 110 - 32, top + 1 + 76 + 10), (left + 1 + 110 + 32, top + 1 + 76 + 10)]
    targets = [(250, 260), (300, 280), (262, 270), (290, 262)]
    for (tx, ty), (gx, gy) in zip(turrets, targets):
        for t in (0.25, 0.55, 0.8):
            sc.blit(S.shot_infantry(int(t * 10) % 2), tx + (gx - tx) * t, ty + (gy - ty) * t)

    # Missiles leaving the wing racks.
    for side in (-1, 1):
        rx = left + 1 + 110 + side * 66
        start = (rx, top + 1 + 72)
        end = (rx + side * 18, top + 1 + 112)
        trail(sc, along(start, end, np.linspace(0.05, 0.8, 30)))
        sc.blit_smooth(S.missile_enemy(0), *end, angle=heading(start, end) + side * 10)

    # Infantry pouring out of the hangar bays.
    for side in (-1, 1):
        bx = left + 1 + 110 + side * 41
        for i in range(4):
            sc.blit(S.infantry(i % 2, angle=180), bx + side * i * 3, top + 1 + 124 + i * 15)

    # A hit from the player's explosive on the hull.
    sc.blit(S.explosion(2, "player", seed=4), 392, 50)
    sc.blit(S.explosion(4, "player", seed=6), 360, 70)

    # Two guards screening the left bay.
    sc.blit(S.guard(1, angle=180), 228, 182)
    sc.blit(S.guard(0, angle=180), 212, 176)

    # Player sliding left out of the laser lane, sniping a turret.
    player = (282, 268)
    aim = heading(player, turrets[2])
    body, flames = S.player_parts(("A",), 1)
    sc.blit_smooth(body, *player, angle=aim, outline="hull_outline", overlay=flames)
    shot = along(player, turrets[2], (0.45,))[0]
    sc.blit_smooth(S.shot_sniper(), *shot, angle=aim)
    sc.blit(S.powerup("repair", 1), 180, 300)

    hud.place_edge_arrow(sc, (-400, 300), "ion_hi", label="BASE")
    hud.place_edge_arrow(sc, (900, 200), "alien_green_hi")

    blips = [(0, -30, "boss"), (-6, -22, "enemy"), (6, -22, "enemy"), (-5, -18, "enemy"), (5, -18, "enemy"),
             (-12, -20, "enemy"), (-36, 30, "base"), (-30, 20, "drill"), (-2, -12, "danger"), (2, -12, "danger")]
    place_hud(sc, dict(shield=0.12, hull=0.34, armor_level=4, weapon="sniper", ammo=0.55,
                       others=("auto", "explosive", "laser"), low_hull=True),
              blips, alert="LASER CHARGING - CLEAR THE LANE", wave=12, next_wave="1:05")
    return sc


if __name__ == "__main__":
    import sys
    out = sys.argv[1]
    defend_the_drill().render().save(f"{out}/mock_defend.png")
    mothership_assault().render().save(f"{out}/mock_mothership.png")
    print("saved")
