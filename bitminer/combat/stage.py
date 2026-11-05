"""A combat stage: your ship, enemies, shots, missiles, beams, and every hit and explosion they make.

Pure Python with no graphics: the renderer reads this state each frame. Positions are game pixels
with y up, and headings are degrees clockwise from straight up, like the flight model.

Colour jobs follow the art: your weapons flash cyan and white, anything that hurts you is pink
and red, enemy hulls break into green and purple, guard scoops into steel.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Callable

from art import sprites as S

from ..flight import Ship, angle_to, forward_vector, right_vector, wrap_angle
from . import shapes
from .specs import DEFENSE, ENEMIES, ENEMY_WEAPONS, WEAPONS

SNAP = 45.0                      # Enemies (but not the mothership) face one of eight directions.
SCOOP_REACH = S.scoop_reach()    # How far a deployed ram scoop sticks out in front of a guard.

# Where things sit on each ship, as (right, forward) offsets from its centre in game pixels.
GUNS = [(-6.0, 3.0), (6.0, 3.0)]           # your auto cannon, one on each pod
NOSE = (0.0, 8.5)                          # sniper and laser
PODS = [(-6.0, 0.0), (6.0, 0.0)]           # missile launch rails
ENEMY_GUN = {"infantry": (0.0, 5.0), "rapid": (0.0, 6.0)}
TANK_PODS = [(-10.5, 6.0), (10.5, 6.0)]
EMITTER = (0.0, 56.5)                      # the mothership's laser, at its nose


def snap_angle(a: float) -> float:
    return round(a / SNAP) * SNAP


def to_world(x: float, y: float, heading: float, right: float, forward: float) -> tuple[float, float]:
    fx, fy = forward_vector(heading)
    rx, ry = right_vector(heading)
    return x + right * rx + forward * fx, y + right * ry + forward * fy


def dist(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(bx - ax, by - ay)


# ---------------------------------------------------------------- things on the stage

@dataclass
class Enemy:
    kind: str
    x: float
    y: float
    heading: float = 180.0
    vx: float = 0.0
    vy: float = 0.0
    health: float = 1.0
    max_health: float = 1.0
    flash: float = 0.0           # white hit flash, 0 to 1
    heat: float = 0.0            # laser glow while a beam is on it
    ram: int = 0                 # guard scoop: 0 folded, 3 fully out
    charge: float = 0.0          # mothership laser charge, 0 to 1
    pods_loaded: bool = True     # tank missile pods
    clock: float = 0.0
    since_hit: float = 99.0
    dying: float = -1.0          # counts up while a long death plays (tank, mothership)
    alive: bool = True           # false once the wreck is gone
    fade_in: float = 1.0         # 0 to 1 while warping in
    uid: int = 0

    @property
    def mass(self) -> float:
        return float(ENEMIES[self.kind]["mass"])

    @property
    def sprite_angle(self) -> float:
        if self.kind == "mothership":
            return self.heading + 180.0     # its art faces down
        return snap_angle(self.heading)

    @property
    def mask(self):
        return shapes.enemy_mask(self.kind, self.ram if self.kind == "guard" else 0)

    @property
    def targetable(self) -> bool:
        return self.alive and self.dying < 0 and self.fade_in >= 1.0

    def point(self, right: float, forward: float) -> tuple[float, float]:
        return to_world(self.x, self.y, self.sprite_angle if self.kind != "mothership" else self.heading,
                        right, forward)


@dataclass
class Shot:
    owner: str                   # "player" or "enemy"
    kind: str                    # auto, sniper, infantry, rapid
    x: float
    y: float
    vx: float
    vy: float
    damage: float
    life: float
    pierce: int = 1
    pad: float = 0.5
    hit: set = field(default_factory=set)
    clock: float = 0.0

    @property
    def heading(self) -> float:
        return angle_to(self.vx, self.vy)


@dataclass
class Missile:
    owner: str
    x: float
    y: float
    heading: float
    speed: float
    max_speed: float
    accel: float
    turn_rate: float
    damage: float
    life: float
    target: object = None        # an Enemy, or "player"
    blast_radius: float = 0.0
    blast_push: float = 0.0
    health: float = 1.0
    clock: float = 0.0
    smoke: float = 0.0
    uid: int = 0
    struck: object = None        # the hull it hit, which takes the full damage


@dataclass
class Beam:
    owner: str                   # "player" or "enemy"
    x: float
    y: float
    heading: float
    length: float
    width: float
    dps: float
    duration: float
    warmup: float = 0.0
    t: float = 0.0
    end: tuple[float, float] = (0.0, 0.0)
    contacts: dict = field(default_factory=dict)   # uid -> (x, y), where the beam meets each hull

    @property
    def firing(self) -> bool:
        return self.warmup <= self.t < self.warmup + self.duration

    @property
    def done(self) -> bool:
        return self.t >= self.warmup + self.duration


@dataclass
class Anim:
    """A short frame animation: explosions, flares, muzzle flashes, hit sparks."""
    name: str
    params: tuple
    frames: int
    fps: float
    x: float
    y: float
    angle: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    drag: float = 0.0
    delay: float = 0.0
    t: float = 0.0
    follow: Callable | None = None   # returns (x, y, angle) to stick to something that moves

    @property
    def frame(self) -> int:
        return int(max(0.0, self.t - self.delay) * self.fps)

    @property
    def started(self) -> bool:
        return self.t >= self.delay

    @property
    def done(self) -> bool:
        return self.frame >= self.frames


@dataclass
class Ring:
    owner: str
    x: float
    y: float
    r0: float
    r1: float
    duration: float
    t: float = 0.0

    @property
    def age(self) -> float:
        return min(1.0, self.t / self.duration)

    @property
    def radius(self) -> int:
        a = 1 - (1 - self.age) ** 2      # fast out, slowing down
        return int(round(self.r0 + (self.r1 - self.r0) * a))


@dataclass
class Chunk:
    """A piece of hull thrown by an explosion, spinning as it flies."""
    kind: str
    variant: int
    x: float
    y: float
    vx: float
    vy: float
    angle: float
    spin: float
    life: float
    t: float = 0.0


@dataclass
class Streak:
    """A bright line that fades fast: the sniper round's path through a hull."""
    x0: float
    y0: float
    x1: float
    y1: float
    life: float = 0.16
    t: float = 0.0


@dataclass
class Lane:
    """A warning drawn on the ground this frame: a guard's ram path or the mothership's laser."""
    kind: str                    # "ram" or "laser"
    x: float
    y: float
    heading: float
    length: float
    locked: bool = False


# ---------------------------------------------------------------- the stage

class Stage:
    def __init__(self, sparks, smoke, seed: int = 1):
        """`sparks` and `smoke` are particle systems (anything with `burst` and `emit`)."""
        self.sparks = sparks
        self.smoke = smoke
        self.rng = random.Random(seed)
        self.ship = Ship(0.0, 0.0)
        self.ship_visible = True
        self.shield_max = float(DEFENSE["shield"])
        self.hull_max = float(DEFENSE["hull"])
        self.shield = self.shield_max
        self.hull = self.hull_max
        self.shield_radius = float(DEFENSE["shield_radius"])
        self.ship_flash = 0.0
        self.shield_show = 0.0
        self.time = 0.0
        self.enemies: list[Enemy] = []
        self.shots: list[Shot] = []
        self.missiles: list[Missile] = []
        self.beams: list[Beam] = []
        self.anims: list[Anim] = []
        self.rings: list[Ring] = []
        self.chunks: list[Chunk] = []
        self.streaks: list[Streak] = []
        self.lanes: list[Lane] = []
        self.timeline: list[tuple[float, Callable]] = []
        self.kick = 0.0              # screen shake waiting for the camera
        self.screen_flash = 0.0
        self.last_hit = None         # (amount, "shield" or "armor") for the HUD
        self._uid = 0
        self._gun = 0

    # ------------------------------------------------------------ setup

    def clear(self) -> None:
        for name in ("enemies", "shots", "missiles", "beams", "anims", "rings", "chunks", "streaks",
                     "lanes", "timeline"):
            getattr(self, name).clear()
        self.screen_flash = 0.0
        self.ship_flash = 0.0
        self.shield_show = 0.0

    def uid(self) -> int:
        self._uid += 1
        return self._uid

    def spawn(self, kind: str, x: float, y: float, heading: float = 180.0, health: float | None = None,
              warp: bool = True) -> Enemy:
        hp = float(ENEMIES[kind]["health"] if health is None else health)
        e = Enemy(kind, x, y, heading=heading, health=hp, max_health=hp, uid=self.uid(),
                  fade_in=0.0 if warp else 1.0, clock=self.rng.random())
        self.enemies.append(e)
        if warp:
            r = 8 if kind in ("infantry", "rapid") else 12 if kind == "guard" else 20 if kind == "tank" else 60
            self.rings.append(Ring("enemy", x, y, r * 1.6, r * 0.6, 0.3))
        return e

    def later(self, delay: float, fn: Callable) -> None:
        self.timeline.append((self.time + delay, fn))

    @property
    def live_enemies(self) -> list[Enemy]:
        return [e for e in self.enemies if e.targetable]

    # ------------------------------------------------------------ your weapons

    def fire_auto(self, heading: float | None = None) -> None:
        w = WEAPONS["auto"]
        ship = self.ship
        h = ship.angle if heading is None else heading
        right, fwd = GUNS[self._gun % 2]
        self._gun += 1
        x, y = to_world(ship.x, ship.y, ship.angle, right, fwd)
        a = h + self.rng.gauss(0, w["spread"])
        fx, fy = forward_vector(a)
        speed = w["speed"]
        self.shots.append(Shot("player", "auto", x, y, fx * speed + ship.vx, fy * speed + ship.vy,
                               w["damage"], w["range"] / speed))
        self.anims.append(Anim("muzzle", ("auto",), 2, 30, x, y, ship.angle,
                               follow=self._ship_follow(right, fwd)))

    def fire_sniper(self, heading: float | None = None) -> None:
        w = WEAPONS["sniper"]
        ship = self.ship
        h = ship.angle if heading is None else heading
        x, y = to_world(ship.x, ship.y, ship.angle, *NOSE)
        fx, fy = forward_vector(h)
        speed = w["speed"]
        self.shots.append(Shot("player", "sniper", x, y, fx * speed, fy * speed, w["damage"],
                               w["range"] / speed, pierce=int(w["pierce"]), pad=1.0))
        self.anims.append(Anim("muzzle", ("sniper",), 2, 20, x, y, ship.angle,
                               follow=self._ship_follow(*NOSE)))
        # Recoil: a small shove backwards, and a puff off the nose.
        ship.vx -= fx * 22
        ship.vy -= fy * 22
        self.sparks.burst("ion_spark", x, y, math.atan2(fy, fx), 0.5, 6, (20, 70), (0.08, 0.2))
        self.kick += 0.12

    def fire_missiles(self, target: Enemy | None) -> None:
        w = WEAPONS["missile"]
        ship = self.ship
        for i, (right, fwd) in enumerate(PODS[: int(w["salvo"])]):
            x, y = to_world(ship.x, ship.y, ship.angle, right, fwd)
            # Out sideways off the rail first, then the motor lights and it turns in.
            h = ship.angle + (-55 if right < 0 else 55)
            self.missiles.append(Missile(
                "player", x, y, h, w["launch_speed"], w["max_speed"], w["accel"], w["turn_rate"],
                w["damage"], w["range"] / w["max_speed"] * 1.6, target=target,
                blast_radius=w["blast_radius"], blast_push=w["blast_push"], uid=self.uid(),
                clock=i * 0.07))
            self.anims.append(Anim("muzzle", ("missile",), 2, 20, x, y, ship.angle))
            self.smoke.burst("smoke", x, y, math.radians(90 - h), 0.8, 5, (6, 24), (0.3, 0.7))

    def start_laser(self) -> Beam:
        w = WEAPONS["laser"]
        ship = self.ship
        x, y = to_world(ship.x, ship.y, ship.angle, *NOSE)
        beam = Beam("player", x, y, ship.angle, w["length"], 5.0, w["dps"], w["duration"], warmup=w["warmup"])
        self.beams.append(beam)
        return beam

    def _ship_follow(self, right: float, fwd: float):
        ship = self.ship

        def where():
            x, y = to_world(ship.x, ship.y, ship.angle, right, fwd)
            return x, y, ship.angle
        return where

    # ------------------------------------------------------------ enemy weapons

    def enemy_shot(self, e: Enemy, kind: str, at: tuple[float, float]) -> None:
        spec = ENEMY_WEAPONS["infantry_laser" if kind == "infantry" else "rapid_laser"]
        x, y = e.point(*ENEMY_GUN[e.kind])
        h = angle_to(at[0] - x, at[1] - y)
        fx, fy = forward_vector(h)
        speed = spec["speed"]
        self.shots.append(Shot("enemy", kind, x, y, fx * speed, fy * speed, spec["damage"], 4.0,
                               pad=2.0 if kind == "infantry" else 0.5))
        self.anims.append(Anim("flare", ("danger",), 2, 24, x, y))

    def tank_missiles(self, tank: Enemy) -> None:
        spec = ENEMY_WEAPONS["tank_missile"]
        for right, fwd in TANK_PODS:
            x, y = tank.point(right, fwd)
            h = tank.sprite_angle + (-25 if right < 0 else 25)
            self.missiles.append(Missile(
                "enemy", x, y, h, spec["launch_speed"], spec["max_speed"], spec["accel"], spec["turn_rate"],
                spec["damage"], 9.0, target="player", health=spec["health"], uid=self.uid()))
            self.smoke.burst("smoke", x, y, math.radians(90 - h), 0.7, 6, (8, 26), (0.4, 0.8))
            self.anims.append(Anim("flare", ("danger",), 2, 20, x, y))
        tank.pods_loaded = False

    def mothership_beam(self, ms: Enemy) -> Beam:
        spec = ENEMY_WEAPONS["mothership_laser"]
        x, y = to_world(ms.x, ms.y, ms.heading, *EMITTER)
        beam = Beam("enemy", x, y, ms.heading, 420.0, 21.0, spec["dps"], spec["fire_time"])
        self.beams.append(beam)
        self.kick += 0.35
        return beam

    # ------------------------------------------------------------ damage

    def damage_enemy(self, e: Enemy, amount: float, x: float, y: float, flash: float = 1.0) -> None:
        """`flash` is how bright the white hit flash starts (a laser burns without flashing)."""
        if not e.targetable:
            return
        e.health -= amount
        e.flash = max(e.flash, flash)
        e.since_hit = 0.0
        if e.health <= 0:
            e.health = 0.0
            self.destroy(e)

    def push_enemy(self, e: Enemy, vx: float, vy: float) -> None:
        """Enemies only drift when something hits them hard: heavier ones barely move."""
        if e.kind == "mothership":
            return
        e.vx += vx / e.mass
        e.vy += vy / e.mass

    def damage_player(self, amount: float, x: float, y: float, kind: str = "shot", push: float = 0.0) -> str:
        """Returns "shield" or "armor": where the hit landed. `push` shoves the ship away from it."""
        ship = self.ship
        come_from = angle_to(x - ship.x, y - ship.y)          # direction of the hit, from the ship
        if push:
            fx, fy = forward_vector(come_from)
            ship.vx -= fx * push
            ship.vy -= fy * push
        if self.shield > 0:
            self.shield = max(0.0, self.shield - amount)
            self.shield_show = 0.45
            bx, by = to_world(ship.x, ship.y, come_from, 0.0, self.shield_radius - 1)
            self.anims.append(Anim("shield_hit", (), 4, 16, ship.x, ship.y, come_from,
                                   follow=lambda: (self.ship.x, self.ship.y, come_from)))
            self.sparks.burst("ion_spark", bx, by, math.radians(90 - come_from), 0.9,
                              4 + int(amount / 3), (25, 70), (0.12, 0.3))
            if self.shield <= 0:
                self.break_shield()
            self.kick += min(0.3, amount / 60)
            self.last_hit = (amount, "shield")
            return "shield"
        self.hull = max(0.0, self.hull - amount)
        self.ship_flash = min(1.0, 0.45 + amount / 30)
        self.anims.append(Anim("armor_hit", (), 4, 18, x, y))
        self.sparks.burst("spark", x, y, math.radians(90 - come_from), 0.8, 5 + int(amount / 2),
                          (30, 90), (0.15, 0.4))
        self.kick += min(0.5, 0.08 + amount / 40)
        self.last_hit = (amount, "armor")
        return "armor"

    def break_shield(self) -> None:
        """The bubble shatters into arcs that fly apart."""
        ship = self.ship
        self.shield = 0.0
        self.anims.append(Anim("shield_break", (), 4, 14, ship.x, ship.y,
                               follow=lambda: (self.ship.x, self.ship.y, 0.0)))
        self.sparks.burst("ion_spark", ship.x, ship.y, 0.0, math.pi, 24, (40, 90), (0.2, 0.45))
        self.kick += 0.3

    def player_blocks(self, x: float, y: float, pad: float = 0.5) -> bool:
        """Does this point touch your shield bubble (when it is up) or your hull?"""
        ship = self.ship
        if not self.ship_visible:
            return False
        if self.shield > 0:
            return dist(x, y, ship.x, ship.y) <= self.shield_radius + pad
        return shapes.hits(shapes.ship_mask(), ship.x, ship.y, ship.angle, x, y, pad)

    # ------------------------------------------------------------ destruction

    def destroy(self, e: Enemy) -> None:
        kind = e.kind
        if kind in ("infantry", "rapid"):
            self._pop(e, 25 if kind == "infantry" else 21, chunks=2, carry=0.5 if kind == "rapid" else 0.1)
            self.kick += 0.12
            e.alive = False
        elif kind == "guard":
            self._pop(e, 33, chunks=3, carry=0.2)
            for i in range(4 + e.ram):
                self._chunk("steel", e.x, e.y, 60, 120)
            self.rings.append(Ring("enemy", e.x, e.y, 6, 30, 0.35))
            self.kick += 0.3
            e.alive = False
        elif kind == "tank":
            e.dying = 0.0
            points = [(-6, 4), (7, -5), (0, 8), (-9, -7)]
            for i, (r, f) in enumerate(points):
                self.later(0.16 * i, lambda r=r, f=f: self._small_pop(e, r, f, "enemy", 17))
            for i, (r, f) in enumerate(TANK_PODS):
                self.later(0.28 + 0.2 * i, lambda r=r, f=f: self._small_pop(e, r, f, "danger", 17))
            self.later(0.8, lambda: self._finale(e, 49, rings=1, chunks=10, kick=0.7))
        elif kind == "mothership":
            e.dying = 0.0
            t = 0.0
            n = 0
            while t < 2.6:
                t += max(0.05, 0.22 - t * 0.07)
                n += 1
                self.later(t, lambda n=n: self._mothership_pop(e, n))
            self.later(2.75, lambda: self._finale(e, 65, rings=2, chunks=24, kick=1.0, flash=1.0))

    def _pop(self, e: Enemy, size: int, chunks: int, carry: float) -> None:
        vx, vy = e.vx * carry, e.vy * carry
        self.anims.append(Anim("explosion", ("enemy", size, e.uid % 3), 6, 14, e.x, e.y, vx=vx, vy=vy, drag=3))
        self.sparks.burst("alien_debris", e.x, e.y, 0.0, math.pi, 10, (20, 80), (0.3, 0.7), (vx, vy))
        for _ in range(chunks):
            self._chunk("enemy", e.x, e.y, 40, 100, (vx, vy))

    def _small_pop(self, e: Enemy, right: float, fwd: float, palette: str, size: int) -> None:
        x, y = e.point(right, fwd)
        self.anims.append(Anim("explosion", (palette, size, self.rng.randrange(3)), 6, 16, x, y))
        e.flash = 1.0
        self.kick += 0.1
        self.sparks.burst("alien_debris" if palette == "enemy" else "danger_spark", x, y, 0.0, math.pi, 6,
                          (20, 60), (0.2, 0.5))

    def _mothership_pop(self, e: Enemy, n: int) -> None:
        mask = e.mask
        h, w = mask.shape
        for _ in range(30):
            col, row = self.rng.randrange(w), self.rng.randrange(h)
            if mask[row, col]:
                break
        lx, ly = col - w / 2, h / 2 - row
        a = math.radians(e.sprite_angle)
        x = e.x + lx * math.cos(a) + ly * math.sin(a)
        y = e.y - lx * math.sin(a) + ly * math.cos(a)
        size = self.rng.choice([17, 21, 25, 33])
        self.anims.append(Anim("explosion", ("enemy", size, n % 3), 6, 16, x, y))
        self.sparks.burst("alien_debris", x, y, 0.0, math.pi, 5, (20, 70), (0.3, 0.6))
        if n % 3 == 0:
            self._chunk("enemy", x, y, 30, 90)
        e.flash = 0.8
        self.kick += 0.06

    def _finale(self, e: Enemy, size: int, rings: int, chunks: int, kick: float, flash: float = 0.0) -> None:
        offsets = [(0, 0)] if size < 60 else [(0, 0), (-38, 10), (40, 6), (0, -34)]
        for i, (ox, oy) in enumerate(offsets):
            self.anims.append(Anim("explosion", ("enemy", size, (e.uid + i) % 3), 6, 12, e.x + ox, e.y + oy,
                                   delay=0.06 * i))
        for i in range(rings):
            self.rings.append(Ring("enemy", e.x, e.y, 8, size * (1.0 + 0.6 * i), 0.4 + 0.2 * i))
        for _ in range(chunks):
            self._chunk("enemy", e.x, e.y, 50, 160)
        self.sparks.burst("alien_debris", e.x, e.y, 0.0, math.pi, 30, (30, 140), (0.4, 0.9))
        self.kick += kick
        self.screen_flash = max(self.screen_flash, flash)
        e.alive = False

    def _chunk(self, kind: str, x: float, y: float, smin: float, smax: float, carry=(0.0, 0.0)) -> None:
        a = self.rng.uniform(0, math.tau)
        s = self.rng.uniform(smin, smax)
        self.chunks.append(Chunk(kind, self.rng.randrange(4), x, y, carry[0] + math.cos(a) * s,
                                 carry[1] + math.sin(a) * s, self.rng.uniform(0, 360),
                                 self.rng.uniform(-720, 720), self.rng.uniform(0.5, 1.1)))

    # ------------------------------------------------------------ the update

    def step(self, dt: float) -> None:
        self.time += dt
        due = [fn for t, fn in self.timeline if t <= self.time]
        self.timeline = [(t, fn) for t, fn in self.timeline if t > self.time]
        for fn in due:
            fn()

        for e in self.enemies:
            e.clock += dt
            e.since_hit += dt
            e.flash = max(0.0, e.flash - dt * 12)     # a blink, so steady fire never bleaches a hull
            e.heat = max(0.0, e.heat - dt * 4)
            e.fade_in = min(1.0, e.fade_in + dt / 0.3)
            if e.dying >= 0:
                e.dying += dt
                e.flash = max(e.flash, 0.35 + 0.35 * math.sin(e.dying * 40))
            e.x += e.vx * dt
            e.y += e.vy * dt
            keep = math.exp(-2.5 * dt)          # a shove dies down; scripted movement sets its own speed
            e.vx *= keep
            e.vy *= keep
        self.enemies = [e for e in self.enemies if e.alive]

        self.ship_flash = max(0.0, self.ship_flash - dt * 6)
        self.shield_show = max(0.0, self.shield_show - dt)
        self.screen_flash = max(0.0, self.screen_flash - dt * 2.5)

        self._step_shots(dt)
        self._step_missiles(dt)
        self._step_beams(dt)
        self._step_effects(dt)

    # ------------------------------------------------------------ shots

    def _step_shots(self, dt: float) -> None:
        keep = []
        for s in self.shots:
            s.clock += dt
            x0, y0 = s.x, s.y
            s.x += s.vx * dt
            s.y += s.vy * dt
            s.life -= dt
            if s.owner == "player":
                alive = self._player_shot_hits(s, x0, y0)
            else:
                alive = self._enemy_shot_hits(s, x0, y0)
            if alive and s.life > 0:
                keep.append(s)
        self.shots = keep

    def _march(self, x0: float, y0: float, x1: float, y1: float, step: float = 1.0):
        n = max(1, int(math.ceil(dist(x0, y0, x1, y1) / step)))
        for i in range(1, n + 1):
            t = i / n
            yield x0 + (x1 - x0) * t, y0 + (y1 - y0) * t

    def _player_shot_hits(self, s: Shot, x0: float, y0: float) -> bool:
        # Your rounds can knock down incoming missiles.
        for m in self.missiles:
            if m.owner == "enemy" and m.health > 0 and self._segment_near(x0, y0, s.x, s.y, m.x, m.y, 4.0):
                m.health -= s.damage
                self.anims.append(Anim("flare", ("player",), 2, 24, m.x, m.y))
                if m.health <= 0:
                    self._missile_down(m)
                return False
        for e in self.enemies:
            if not e.targetable or e.uid in s.hit:
                continue
            reach = shapes.radius_of(e.mask) + s.pad
            if not self._segment_near(x0, y0, s.x, s.y, e.x, e.y, reach):
                continue
            for px, py in self._march(x0, y0, s.x, s.y):
                if shapes.hits(e.mask, e.x, e.y, e.sprite_angle, px, py, s.pad):
                    self._player_hit(s, e, px, py)
                    s.hit.add(e.uid)
                    s.pierce -= 1
                    break
            if s.pierce <= 0:
                return False
        return True

    def _player_hit(self, s: Shot, e: Enemy, x: float, y: float) -> None:
        back = math.atan2(-s.vy, -s.vx)
        if s.kind == "sniper":
            fwd = math.atan2(s.vy, s.vx)
            self.anims.append(Anim("flare", ("player",), 2, 14, x, y))
            # A bright line through the hull and debris out of the far side.
            fx, fy = math.cos(fwd), math.sin(fwd)
            span = shapes.radius_of(e.mask) * 1.6
            self.streaks.append(Streak(x - fx * 4, y - fy * 4, x + fx * span, y + fy * span))
            self.sparks.burst("ion_spark", x + fx * span * 0.6, y + fy * span * 0.6, fwd, 0.35, 8,
                              (60, 160), (0.12, 0.3))
            self.sparks.burst("alien_debris", x + fx * span * 0.5, y + fy * span * 0.5, fwd, 0.5, 8,
                              (40, 110), (0.2, 0.5))
            self.push_enemy(e, s.vx * 0.04, s.vy * 0.04)
            self.kick += 0.08
        else:
            self.anims.append(Anim("flare", ("player",), 2, 30, x, y))
            self.sparks.burst("ion_spark", x, y, back, 0.7, 3, (30, 90), (0.08, 0.2))
            self.sparks.burst("alien_debris", x, y, back, 0.9, 1, (20, 60), (0.15, 0.35))
        self.damage_enemy(e, s.damage, x, y, flash=1.0 if s.kind == "sniper" else 0.55)

    def _enemy_shot_hits(self, s: Shot, x0: float, y0: float) -> bool:
        ship = self.ship
        if not self.ship_visible:
            return True
        reach = (self.shield_radius if self.shield > 0 else 10.0) + s.pad
        if not self._segment_near(x0, y0, s.x, s.y, ship.x, ship.y, reach):
            return True
        for px, py in self._march(x0, y0, s.x, s.y):
            if self.player_blocks(px, py, s.pad):
                self.anims.append(Anim("flare", ("danger",), 2, 20, px, py))
                self.sparks.burst("danger_spark", px, py, math.atan2(-s.vy, -s.vx), 0.9, 4, (20, 70), (0.1, 0.3))
                self.damage_player(s.damage, px, py, push=s.damage * 1.5)
                return False
        return True

    @staticmethod
    def _segment_near(x0, y0, x1, y1, cx, cy, r) -> bool:
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((cx - x0) * dx + (cy - y0) * dy) / L2))
        px, py = x0 + dx * t, y0 + dy * t
        return (cx - px) ** 2 + (cy - py) ** 2 <= r * r

    # ------------------------------------------------------------ missiles

    def _step_missiles(self, dt: float) -> None:
        keep = []
        for m in self.missiles:
            m.clock += dt
            m.life -= dt
            # Steer toward the target at a limited turn rate, once clear of the rail.
            goal = self._missile_goal(m)
            if goal is not None and m.clock > 0.12:
                want = angle_to(goal[0] - m.x, goal[1] - m.y)
                diff = wrap_angle(want - m.heading)
                turn = m.turn_rate * dt
                m.heading = wrap_angle(m.heading + max(-turn, min(turn, diff)))
            if m.clock > 0.1:
                m.speed = min(m.max_speed, m.speed + m.accel * dt)
            fx, fy = forward_vector(m.heading)
            x0, y0 = m.x, m.y
            m.x += fx * m.speed * dt
            m.y += fy * m.speed * dt
            # Smoke trail: grey puffs for theirs, faint ion for yours.
            m.smoke += dt * (40 if m.owner == "enemy" else 50)
            while m.smoke >= 1:
                m.smoke -= 1
                tx, ty = m.x - fx * 5, m.y - fy * 5
                if m.owner == "enemy":
                    self.smoke.emit("smoke", tx, ty, self.rng.uniform(-6, 6), self.rng.uniform(-6, 6),
                                    self.rng.uniform(0.5, 0.9))
                else:
                    self.smoke.emit("exhaust", tx, ty, -fx * 30 + self.rng.uniform(-8, 8),
                                    -fy * 30 + self.rng.uniform(-8, 8), self.rng.uniform(0.15, 0.3))
            if m.health <= 0:
                continue
            if self._missile_contact(m, x0, y0) or m.life <= 0:
                self._missile_burst(m)
                continue
            keep.append(m)
        self.missiles = keep

    def _missile_goal(self, m: Missile):
        if m.owner == "enemy":
            return (self.ship.x, self.ship.y) if self.ship_visible else None
        t = m.target
        if not isinstance(t, Enemy) or not t.targetable:
            live = self.live_enemies
            if not live:
                return None
            t = m.target = min(live, key=lambda e: dist(e.x, e.y, m.x, m.y))
        return t.x, t.y

    def _missile_contact(self, m: Missile, x0: float, y0: float) -> bool:
        if m.owner == "enemy":
            for px, py in self._march(x0, y0, m.x, m.y, 1.5):
                if self.player_blocks(px, py, 1.5):
                    m.x, m.y = px, py
                    return True
            return False
        for e in self.enemies:
            if not e.targetable:
                continue
            if not self._segment_near(x0, y0, m.x, m.y, e.x, e.y, shapes.radius_of(e.mask) + 2):
                continue
            for px, py in self._march(x0, y0, m.x, m.y, 1.5):
                if shapes.hits(e.mask, e.x, e.y, e.sprite_angle, px, py, 1.5):
                    m.x, m.y = px, py
                    m.struck = e
                    return True
        return False

    def _missile_burst(self, m: Missile) -> None:
        if m.owner == "enemy":
            self.anims.append(Anim("explosion", ("danger", 21, m.uid % 3), 6, 16, m.x, m.y))
            self.sparks.burst("danger_spark", m.x, m.y, 0.0, math.pi, 10, (30, 90), (0.15, 0.4))
            if self.player_blocks(m.x, m.y, 4.0):
                self.damage_player(m.damage, m.x, m.y, "missile", push=40.0)
            return
        R = m.blast_radius
        self.anims.append(Anim("explosion", ("player", 33, m.uid % 3), 6, 15, m.x, m.y))
        self.rings.append(Ring("player", m.x, m.y, 4, R, 0.25))
        self.sparks.burst("ion_spark", m.x, m.y, 0.0, math.pi, 16, (40, 130), (0.15, 0.4))
        self.kick += 0.25
        for e in list(self.enemies):
            if not e.targetable:
                continue
            d = dist(m.x, m.y, e.x, e.y)
            a = math.atan2(e.y - m.y, e.x - m.x) if d > 0.01 else 0.0
            if e is m.struck:
                falloff = 1.0
            else:
                # Others caught in the blast take less the further their hull is from it.
                gap = max(0.0, d - shapes.radius_of(e.mask) * 0.5)
                if gap > R:
                    continue
                falloff = 1.0 - 0.6 * gap / R
            self.push_enemy(e, math.cos(a) * m.blast_push * falloff, math.sin(a) * m.blast_push * falloff)
            self.damage_enemy(e, m.damage * falloff, m.x, m.y)

    def _missile_down(self, m: Missile) -> None:
        m.health = 0
        self.anims.append(Anim("explosion", ("danger", 17, m.uid % 3), 6, 18, m.x, m.y))
        self.sparks.burst("danger_spark", m.x, m.y, 0.0, math.pi, 8, (20, 70), (0.15, 0.35))
        for _ in range(8):
            self.smoke.emit("smoke", m.x, m.y, self.rng.uniform(-20, 20), self.rng.uniform(-20, 20),
                            self.rng.uniform(0.5, 1.0))

    # ------------------------------------------------------------ beams

    def _step_beams(self, dt: float) -> None:
        keep = []
        for b in self.beams:
            b.t += dt
            fx, fy = forward_vector(b.heading)
            b.contacts = {}
            if b.owner == "player":
                # Your laser stays on the nose, so turning the ship sweeps it.
                b.x, b.y = to_world(self.ship.x, self.ship.y, self.ship.angle, *NOSE)
                b.heading = self.ship.angle
                fx, fy = forward_vector(b.heading)
                b.end = (b.x + fx * b.length, b.y + fy * b.length)
                if b.firing and self.ship_visible:
                    self._player_beam(b, fx, fy, dt)
            else:
                b.end = (b.x + fx * b.length, b.y + fy * b.length)
                if b.firing:
                    self._enemy_beam(b, fx, fy, dt)
            if not b.done:
                keep.append(b)
        self.beams = keep

    def _player_beam(self, b: Beam, fx: float, fy: float, dt: float) -> None:
        for e in self.enemies:
            if not e.targetable:
                continue
            r = shapes.radius_of(e.mask)
            if not self._segment_near(b.x, b.y, b.end[0], b.end[1], e.x, e.y, r + b.width):
                continue
            d = 0.0
            while d <= b.length:
                px, py = b.x + fx * d, b.y + fy * d
                if shapes.hits(e.mask, e.x, e.y, e.sprite_angle, px, py, b.width / 2):
                    b.contacts[e.uid] = (px, py)
                    e.heat = 1.0
                    if self.rng.random() < dt * 40:
                        self.sparks.burst("ion_spark", px, py, math.atan2(-fy, -fx), 1.0, 2, (30, 110), (0.1, 0.3))
                    if self.rng.random() < dt * 30:
                        self.sparks.burst("alien_debris", px, py, math.atan2(-fy, -fx), 1.2, 1, (20, 80), (0.2, 0.5))
                    self.damage_enemy(e, b.dps * dt, px, py, flash=0.0)
                    break
                d += 1.5

    def _beam_stop(self, b: Beam, fx: float, fy: float) -> tuple[float, float] | None:
        """Where the beam stops on your shield or hull, or None if it misses you."""
        if not self.ship_visible:
            return None
        ship = self.ship
        half = b.width / 2 - 2
        rx, ry = ship.x - b.x, ship.y - b.y
        along = rx * fx + ry * fy
        side = abs(rx * fy - ry * fx)          # how far the ship is from the beam's centre line
        if self.shield > 0:
            R = self.shield_radius
            if side > R + half or along < -R or along > b.length + R:
                return None
            # Head on, the beam ends where its centre line meets the bubble; a graze ends level with you.
            d = along - math.sqrt(max(0.0, R * R - min(side, R) ** 2))
            return b.x + fx * d, b.y + fy * d
        d = 0.0
        while d <= b.length:
            px, py = b.x + fx * d, b.y + fy * d
            if self.player_blocks(px, py, half):
                # The beam's edge has reached the hull; carry the end on to the hull itself if it is in line.
                for extra in range(0, int(half) + 3):
                    qx, qy = px + fx * extra, py + fy * extra
                    if self.player_blocks(qx, qy, 1.0):
                        return qx, qy
                return px, py
            d += 2.0
        return None

    def _enemy_beam(self, b: Beam, fx: float, fy: float, dt: float) -> None:
        stop = self._beam_stop(b, fx, fy)
        if stop is None:
            return
        px, py = stop
        b.end = (px, py)
        b.contacts[0] = (px, py)
        was = self.shield
        where = "shield" if self.shield > 0 else "armor"
        if where == "shield":
            self.shield = max(0.0, self.shield - b.dps * dt)
            self.shield_show = 0.3
            if self.shield <= 0 < was:
                self.break_shield()
            elif self.rng.random() < dt * 12:
                self.damage_player(0.0, px, py)       # the arc flash where the beam lands
        else:
            self.hull = max(0.0, self.hull - b.dps * dt)
            self.ship_flash = max(self.ship_flash, 0.7)
            if self.rng.random() < dt * 20:
                self.anims.append(Anim("armor_hit", (), 4, 18, px, py))
        self.sparks.burst("danger_spark", px, py, math.atan2(-fy, -fx), 1.1, 2, (30, 110), (0.1, 0.3))
        self.kick += dt * 1.2
        self.last_hit = (b.dps, where)

    # ------------------------------------------------------------ effects

    def _step_effects(self, dt: float) -> None:
        for a in self.anims:
            a.t += dt
            if a.follow is not None:
                a.x, a.y, a.angle = a.follow()
            elif a.vx or a.vy:
                a.x += a.vx * dt
                a.y += a.vy * dt
                k = math.exp(-a.drag * dt)
                a.vx *= k
                a.vy *= k
        self.anims = [a for a in self.anims if not a.done]
        for r in self.rings:
            r.t += dt
        self.rings = [r for r in self.rings if r.t < r.duration]
        for c in self.chunks:
            c.t += dt
            c.x += c.vx * dt
            c.y += c.vy * dt
            k = math.exp(-1.8 * dt)
            c.vx *= k
            c.vy *= k
            c.angle += c.spin * dt
        self.chunks = [c for c in self.chunks if c.t < c.life]
        for s in self.streaks:
            s.t += dt
        self.streaks = [s for s in self.streaks if s.t < s.life]
