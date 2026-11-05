"""Every scene in the weapon gallery, as short scripts for the director.

Two kinds of scene:
- Your weapons: the auto cannon, sniper, missiles and laser against each enemy class, ending in
  that enemy's destruction.
- Enemy attacks: each enemy weapon hitting you, with the shield up, with the shield breaking, or
  straight onto the armor.

Positions are game pixels from the arena centre, where your ship holds its post facing up.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from ..combat.specs import ENEMIES, ENEMY_WEAPONS, GALLERY, WEAPONS
from ..combat.stage import EMITTER, SCOOP_REACH, Anim, Lane, dist, to_world
from ..flight import angle_to, forward_vector, wrap_angle
from .director import Director, Script, health_for, wait_until

TICK = 1 / 60
FOREVER = 1e9


@dataclass(frozen=True)
class Scene:
    column: str                    # a weapon (auto, sniper, missile, laser) or an attack
    row: str                       # a target class, or a defense (shield, shield_breaks, armor)
    title: str
    about: str
    script: Callable[[Director], Script]
    focus: tuple[float, float] = (0.0, 70.0)    # what the fixed camera looks at, from the centre
    crop: tuple[int, int] = (384, 216)          # GIF size in game pixels

    @property
    def key(self) -> str:
        return f"{self.column}-{self.row}"

    @property
    def defense(self) -> str:
        return self.row if self.row in DEFENSES else "shield"


DEFENSES = {"shield": "SHIELD", "shield_breaks": "SHIELD BREAKS", "armor": "ARMOR"}

WEAPON_ABOUT = {
    "auto": "FAST ROUNDS FROM BOTH PODS. EVERY HIT FLARES AND CHIPS THE HULL.",
    "sniper": "ONE HEAVY ROUND THAT GOES THROUGH UP TO {pierce} HULLS AND KICKS YOU BACK.",
    "missile": "{salvo} HOMING MISSILES A SALVO. THE BLAST HURTS AND SHOVES EVERYTHING NEAR IT.",
    "laser": "A SHORT WARM-UP, THEN A BEAM THAT BURNS EVERY HULL IT TOUCHES AS YOU SWEEP.",
}
DEATH_ABOUT = {
    "infantry": "INFANTRY POP IN ONE BURST.",
    "guard": "GUARDS BURST AND THROW STEEL FROM THE SCOOP.",
    "rapid": "RAPID ASSAULT WRECKS KEEP FLYING AS THEY POP.",
    "tank": "TANKS CRACK, COOK OFF BOTH MISSILE PODS, THEN BLOW.",
    "mothership": "THE MOTHERSHIP BURNS IN A CHAIN OF BLASTS, THEN GOES UP.",
}

ATTACKS = {
    "infantry_lasers": ("INFANTRY LASERS", "SLOW PINK BOLTS, ONE EVERY {fire_every}S FROM EACH SHIP. EASY TO DODGE."),
    "rapid_assault": ("RAPID ASSAULT", "HIT AND RUN: A DIVE, A BURST OF {burst} FAST SHOTS, AND AWAY."),
    "guard_ram": ("GUARD RAM", "THE SCOOP LOCKS WITH A GLINT, THE LANE FLASHES, THEN IT CHARGES."),
    "tank_missiles": ("TANK MISSILES", "TWO SLOW HOMING MISSILES. THEY TURN WIDE, SO SIDESTEP LATE."),
    "shoot_down": ("SHOOT DOWN MISSILES", "TANK MISSILES CAN BE SHOT DOWN. ONE ROUND EACH."),
    "mothership_laser": ("MOTHERSHIP LASER", "IT TURNS TO TRACK YOU, THE LANE LOCKS AND FLASHES, THEN IT FIRES."),
}


# ---------------------------------------------------------------- your weapons against each target

def _targets(d: Director, weapon: str, target: str) -> list:
    """Spawn the targets for one weapon scene and give them something to do."""
    hp = health_for(weapon, target)
    foes = []
    if target == "infantry":
        spots = {
            "sniper": [(0, 100), (0, 128), (0, 156)],           # a column, to show the round piercing
            "missile": [(-40, 114), (0, 130), (40, 114), (-20, 154), (20, 154)],
        }.get(weapon, [(-44, 116), (0, 128), (44, 116)])
    elif target == "rapid":
        spots = []
    elif target == "mothership":
        spots = [(0, 190)]
    else:
        spots = [(0, 122)]

    for i, (dx, dy) in enumerate(spots):
        heading = 180.0 if target == "mothership" else None
        e = d.spawn(target, dx, dy, health=hp, heading=heading)
        if target == "mothership":
            d.anchor(e, lambda p=d.at(dx, dy): p, stiff=40, face=None)
        else:
            d.anchor(e, lambda p=d.at(dx, dy), ph=i * 1.9: (p[0] + 5 * math.sin(d.time * 1.4 + ph),
                                                           p[1] + 3 * math.sin(d.time * 2.3 + ph)))
        foes.append(e)

    if target == "rapid":
        # Three fast ships circling, so the aiming has to lead them.
        r = 58.0
        cx, cy = d.at(0, 118)
        w = GALLERY["orbit_speed"] / r
        for i in range(3):
            ph = i * math.tau / 3

            def where(ph=ph):
                a = ph + w * d.time
                return cx + r * math.cos(a), cy + r * math.sin(a) * 0.6
            x, y = where()
            e = d.stage.spawn("rapid", x, y, health=hp)
            d.anchor(e, where, stiff=60, face="motion")
            foes.append(e)
    return foes


def _alive(foes) -> list:
    return [e for e in foes if e.alive and e.dying < 0]


def _nearest(d: Director, foes):
    ship = d.stage.ship
    return min(_alive(foes), key=lambda e: dist(e.x, e.y, ship.x, ship.y))


def weapon_script(weapon: str, target: str) -> Callable[[Director], Script]:
    w = WEAPONS[weapon]

    def script(d: Director) -> Script:
        foes = _targets(d, weapon, target)
        yield 0.45                                # let them warp in
        limit = 12.0 if d.auto else FOREVER
        start = d.time
        while _alive(foes) and d.time - start < limit:
            e = _nearest(d, foes)
            if weapon == "auto":
                d.aim = lambda e=e: d.lead(e.x, e.y, e.vx, e.vy, w["speed"])
                if d.aim_error() < 6:
                    d.fire("auto")
                yield 1 / w["fire_rate"]
            elif weapon == "sniper":
                d.aim = lambda e=e: d.lead(e.x, e.y, e.vx, e.vy, w["speed"])
                yield from wait_until(lambda: d.aim_error() < 0.6, 0.8)
                d.fire("sniper")
                yield 1 / w["fire_rate"]
            elif weapon == "missile":
                d.aim = e
                yield from wait_until(lambda: d.aim_error() < 8, 0.6)
                d.fire("missile", e)
                yield 1 / w["fire_rate"]
            else:
                yield from _laser_sweep(d, foes)
        d.aim = None

    return script


def _laser_sweep(d: Director, foes) -> Script:
    """Swing the laser across the targets once: start to one side, fire, sweep to the other."""
    w = WEAPONS["laser"]
    ship = d.stage.ship
    live = _alive(foes)
    cx = sum(e.x for e in live) / len(live)
    cy = sum(e.y for e in live) / len(live)
    mid = angle_to(cx - ship.x, cy - ship.y)
    # Wide enough to cross every target, and never narrower than the sweep in the data.
    spread = max(abs(wrap_angle(angle_to(e.x - ship.x, e.y - ship.y) - mid)) for e in live)
    half = max(GALLERY["laser_sweep"] / 2, spread + 5)
    d.aim = mid - half
    yield from wait_until(lambda: d.aim_error() < 1.0, 0.6)
    d.fire("laser")
    t0 = d.time
    span = w["warmup"] + w["duration"]
    d.aim = lambda: mid - half + 2 * half * min(1.0, max(0.0, (d.time - t0 - w["warmup"]) / w["duration"]))
    yield from wait_until(lambda: d.time - t0 >= span, span + 0.2)
    yield 0.35


# ---------------------------------------------------------------- enemy attacks

def infantry_lasers(d: Director) -> Script:
    spec = ENEMY_WEAPONS["infantry_laser"]
    foes = []
    for i, (dx, dy) in enumerate([(-74, 118), (0, 140), (74, 118)]):
        e = d.spawn("infantry", dx, dy)
        d.anchor(e, lambda p=d.at(dx, dy), ph=i * 2.1: (p[0] + 16 * math.sin(d.time * 1.2 + ph),
                                                       p[1] + 5 * math.sin(d.time * 2.0 + ph)))
        foes.append(e)
    timers = [0.55 + i * 0.37 for i in range(len(foes))]
    stop = [5.4 if d.auto else FOREVER]

    def gunner(dt: float) -> None:
        if d.time > stop[0]:
            return
        ship = d.stage.ship
        for i, e in enumerate(foes):
            if not e.targetable:
                continue
            timers[i] -= dt
            if timers[i] <= 0:
                timers[i] += spec["fire_every"]
                d.stage.enemy_shot(e, "infantry", (ship.x, ship.y))
    d.brain(gunner)
    yield from wait_until(lambda: d.time > stop[0] or not _alive(foes), FOREVER)


def rapid_assault(d: Director) -> Script:
    """Two rapid assault ships take turns diving past, each firing one burst on the way in."""
    spec = ENEMY_WEAPONS["rapid_laser"]
    speed = ENEMIES["rapid"]["speed"]
    st = d.stage
    passes = 3 if d.auto else 10 ** 6
    ships = []
    for side in (-1, 1):
        ships.append(st.spawn("rapid", *d.at(-300 * side, 220), heading=90.0 * side, warp=False))
    for n in range(passes):
        e = ships[n % 2]
        if not e.alive:
            e = ships[(n + 1) % 2]
            if not e.alive:
                return
        side = -1 if n % 2 == 0 else 1          # -1: in from the left
        yield from _dive(d, e, side, speed, spec)
        yield 0.25


def _dive(d: Director, e, side: int, speed: float, spec: dict) -> Script:
    st = d.stage
    ship = st.ship
    ox, oy = ship.x, ship.y
    # A curve that comes down from high on one side, passes over you and climbs away on the other.
    p0 = (ox + 250 * side, oy + 210)
    p1 = (ox + 20 * side, oy - 40)
    p2 = (ox - 250 * side, oy + 210)

    def bez(t):
        a, b, c = (1 - t) ** 2, 2 * t * (1 - t), t * t
        return (a * p0[0] + b * p1[0] + c * p2[0], a * p0[1] + b * p1[1] + c * p2[1])
    # Arc length, to fly the curve at a steady speed.
    samples = [bez(i / 60) for i in range(61)]
    length = sum(dist(*samples[i], *samples[i + 1]) for i in range(60))
    t = 0.0
    fired = 0
    shot_clock = 0.0
    e.x, e.y = p0
    while t < 1.0 and e.alive and e.dying < 0:
        t = min(1.0, t + speed * TICK / length)
        x, y = bez(t)
        e.heading = angle_to(x - e.x, y - e.y)
        e.vx, e.vy = (x - e.x) / TICK, (y - e.y) / TICK
        e.x, e.y = x, y
        if t > 0.3 and fired < spec["burst"]:
            shot_clock -= TICK
            if shot_clock <= 0:
                st.enemy_shot(e, "rapid", (ship.x, ship.y))
                fired += 1
                shot_clock = spec["burst_gap"]
        yield TICK
    e.vx = e.vy = 0.0


def guard_ram(d: Director) -> Script:
    spec = ENEMIES["guard"]
    st = d.stage
    g = d.spawn("guard", 0, 120)
    home = d.at(0, 120)
    mode = {"m": "hold"}

    def keep(dt: float) -> None:
        if not g.alive or g.dying >= 0:
            return
        if mode["m"] == "hold":
            g.vx += ((home[0] - g.x) * 6 - g.vx * 4.4) * dt
            g.vy += ((home[1] - g.y) * 6 - g.vy * 4.4) * dt
            d.face_ship(g, 220, dt)
    d.brain(keep)

    yield 0.7
    rams = 2 if d.auto else 10 ** 6
    for _ in range(rams):
        if not g.alive:
            return
        # The scoop folds out in three steps and locks with a glint.
        d.face_ship(g)
        for stage_ in (1, 2, 3):
            g.ram = stage_
            yield 0.12
        tip = lambda: g.point(0, SCOOP_REACH - 1)
        st.anims.append(Anim("glint", (), 4, 12, *tip(), follow=lambda: (*tip(), 0.0)))
        yield 0.2
        # The lane flashes along the path it is about to take.
        mode["m"] = "aim"
        ship = st.ship
        heading = angle_to(ship.x - g.x, ship.y - g.y)
        g.heading = heading
        reach = dist(g.x, g.y, ship.x, ship.y) + 40
        lane = Lane("ram", g.x, g.y, heading, reach)
        st.lanes.append(lane)
        yield spec["warn_time"]
        st.lanes.remove(lane)
        # Charge.
        mode["m"] = "dash"
        fx, fy = forward_vector(heading)
        travelled = 0.0
        hit = False
        while travelled < reach + 30 and g.alive and g.dying < 0:
            x0, y0 = tip()
            g.vx, g.vy = fx * spec["ram_speed"], fy * spec["ram_speed"]
            step = spec["ram_speed"] * TICK
            g.x += fx * step
            g.y += fy * step
            g.vx = g.vy = 0.0
            travelled += step
            x1, y1 = tip()
            for i in range(1, 6):
                px, py = x0 + (x1 - x0) * i / 5, y0 + (y1 - y0) * i / 5
                if st.player_blocks(px, py, 1.0):
                    hit = True
                    _ram_impact(d, g, px, py, fx, fy)
                    break
            if hit:
                break
            yield TICK
        mode["m"] = "recoil"
        yield 0.45
        for stage_ in (2, 1, 0):
            g.ram = stage_
            yield 0.1
        mode["m"] = "hold"
        yield 1.1 if hit else 0.6


def _ram_impact(d: Director, g, x: float, y: float, fx: float, fy: float) -> None:
    spec = ENEMIES["guard"]
    st = d.stage
    st.damage_player(spec["ram_damage"], x, y, kind="ram", push=spec["ram_speed"] * 0.45)
    st.sparks.burst("steel", x, y, math.atan2(-fy, -fx), 1.0, 14, (40, 130), (0.2, 0.5))
    st.sparks.burst("danger_spark", x, y, math.atan2(fy, fx), 0.9, 8, (30, 100), (0.15, 0.35))
    st.anims.append(Anim("flare", ("steel",), 2, 18, x, y))
    st.kick += 0.45
    # The guard bounces back off you.
    st.push_enemy(g, -fx * 150 * g.mass, -fy * 150 * g.mass)


def tank_missiles(shoot_down: bool) -> Callable[[Director], Script]:
    def script(d: Director) -> Script:
        st = d.stage
        tank = d.spawn("tank", 0, 146)
        d.anchor(tank, lambda p=d.at(0, 146): p, stiff=8)
        auto = WEAPONS["auto"]
        gun = {"cool": 0.0}
        d.aim = tank

        if shoot_down:
            def gunner(dt: float) -> None:
                gun["cool"] -= dt
                incoming = [m for m in st.missiles if m.owner == "enemy" and m.health > 0 and m.clock > 0.25]
                if not incoming:
                    d.aim = tank
                    return
                ship = st.ship
                m = min(incoming, key=lambda m: dist(m.x, m.y, ship.x, ship.y))
                fx, fy = forward_vector(m.heading)
                d.aim = d.lead(m.x, m.y, fx * m.speed, fy * m.speed, auto["speed"])
                if d.auto and gun["cool"] <= 0 and d.aim_error() < 4:
                    st.fire_auto()
                    gun["cool"] = 1 / auto["fire_rate"]
            d.brain(gunner)

        yield 0.8
        volleys = 2 if d.auto else 10 ** 6
        for _ in range(volleys):
            if not tank.alive:
                return
            st.tank_missiles(tank)
            st.later(1.4, lambda: setattr(tank, "pods_loaded", True))
            yield 3.3
        yield from wait_until(lambda: not any(m.owner == "enemy" for m in st.missiles), 8)
        d.aim = None
    return script


def mothership_laser(d: Director) -> Script:
    spec = ENEMY_WEAPONS["mothership_laser"]
    st = d.stage
    ms = d.spawn("mothership", 0, 190, heading=180.0, health=ENEMIES["mothership"]["health"])
    d.anchor(ms, lambda p=d.at(0, 190): p, stiff=40, face=None)
    phase = {"p": "idle", "t": 0.0}
    lane = Lane("laser", 0.0, 0.0, 180.0, 420.0)

    def emitter():
        return to_world(ms.x, ms.y, ms.heading, *EMITTER)

    def think(dt: float) -> None:
        if not ms.alive or ms.dying >= 0:
            return
        phase["t"] += dt
        p = phase["p"]
        if p == "track":
            d.face_ship(ms, spec["turn_rate"], dt)
            ms.charge = min(1.0, phase["t"] / spec["track_time"])
        elif p == "cool":
            ms.charge = max(0.0, ms.charge - dt * 1.5)
        lane.x, lane.y = emitter()
        lane.heading = ms.heading

    d.brain(think)
    d.aim = ms
    # In auto mode the ship slides sideways while the mothership tracks it.
    yield 0.3
    if d.auto:
        d.post = d.at(-52, 0)
    yield 0.6
    cycles = 1 if d.auto else 10 ** 6
    for _ in range(cycles):
        if not ms.alive:
            return
        phase.update(p="track", t=0.0)
        st.lanes.append(lane)
        if d.auto:
            slide_start = d.time

            def slide():
                k = min(1.0, (d.time - slide_start) / (spec["track_time"] * 0.65))
                k = k * k * (3 - 2 * k)
                return d.at(-52 + 96 * k, 0)
            d.post_fn = slide
        yield spec["track_time"]
        phase.update(p="lock", t=0.0)
        lane.locked = True
        yield spec["lock_time"]
        st.lanes.remove(lane)
        lane.locked = False
        phase.update(p="fire", t=0.0)
        st.mothership_beam(ms)
        yield spec["fire_time"]
        phase.update(p="cool", t=0.0)
        yield 1.1
    d.post_fn = None


ATTACK_SCRIPTS = {
    "infantry_lasers": infantry_lasers,
    "rapid_assault": rapid_assault,
    "guard_ram": guard_ram,
    "tank_missiles": tank_missiles(False),
    "shoot_down": tank_missiles(True),
    "mothership_laser": mothership_laser,
}
BIG = ((0.0, 108.0), (512, 304))          # framing for scenes with the mothership in them
ATTACK_FOCUS = {"mothership_laser": BIG, "rapid_assault": ((0.0, 80.0), (448, 252))}


def _fmt(text: str, spec: dict) -> str:
    return text.format(**{k: (f"{v:g}" if isinstance(v, float) else v) for k, v in spec.items()})


def build() -> list[Scene]:
    scenes = []
    for weapon in WEAPONS:
        label = WEAPONS[weapon]["label"]
        about = _fmt(WEAPON_ABOUT[weapon], WEAPONS[weapon])
        for target in ENEMIES:
            focus, crop = BIG if target == "mothership" else (Scene.focus, Scene.crop)
            scenes.append(Scene(
                weapon, target, f"{label} VS {ENEMIES[target]['label']}", f"{about} {DEATH_ABOUT[target]}",
                weapon_script(weapon, target), focus=focus, crop=crop))
    for attack, (label, about) in ATTACKS.items():
        spec = {"infantry_lasers": ENEMY_WEAPONS["infantry_laser"], "rapid_assault": ENEMY_WEAPONS["rapid_laser"]}.get(attack, {})
        focus, crop = ATTACK_FOCUS.get(attack, (Scene.focus, Scene.crop))
        for defense, dlabel in DEFENSES.items():
            scenes.append(Scene(attack, defense, f"{label} ON {dlabel}", _fmt(about, spec),
                                ATTACK_SCRIPTS[attack], focus=focus, crop=crop))
    return scenes


SCENES = build()
BY_KEY = {s.key: s for s in SCENES}
COLUMNS = list(dict.fromkeys(s.column for s in SCENES))


def column_label(column: str) -> str:
    return WEAPONS[column]["label"] if column in WEAPONS else ATTACKS[column][0]


def row_label(row: str) -> str:
    return ENEMIES[row]["label"] if row in ENEMIES else DEFENSES[row]


def rows_of(column: str) -> list[str]:
    return [s.row for s in SCENES if s.column == column]


def find(column: str, row: str) -> Scene:
    return BY_KEY[f"{column}-{row}"]

