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

from ..field import wrap_delta
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
    mx: float = 0.0              # the steady speed its pilot flies at (vx, vy is only a shove)
    my: float = 0.0
    ramming: bool = False        # a guard mid-dash: its ram does the hitting, not its hull
    age: float = 0.0
    brain: object = None         # what flies it in a real fight
    immune: bool = False         # hits spark off it but do no damage (the mothership, until it can fight back)

    @property
    def mass(self) -> float:
        return float(ENEMIES[self.kind]["mass"])

    @property
    def body_r(self) -> float:
        """A circle for bumping into rocks: a little inside the hull's farthest corner."""
        return shapes.reach(self.kind, self.ram if self.kind == "guard" else 0) * 0.8

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
    reach: float = 0.0           # how far it gets before a rock stops it (its length if none does)
    burst: float = 0.0           # seconds the charged laser opens extra wide

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

@dataclass
class Structure:
    """Something of yours that sits still and can be shot at: a drill on an asteroid, or home base."""
    kind: str                    # "drill" or "base"
    x: float
    y: float
    radius: float                # enemy shots within this of the centre hit it
    health: float
    max_health: float
    uid: int = 0
    rock: int = -1               # a drill's asteroid
    immune: bool = False         # shots spark off it but do no damage
    alive: bool = True
    flash: float = 0.0
    since_hit: float = 99.0
    clock: float = 0.0
    hold: float = 0.0            # a drill: ore dug out and waiting for you to pick it up
    hold_max: float = 0.0
    side: float = 0.0            # a drill: which way it faces out from its asteroid (heading, degrees)
    working: bool = False        # a drill: dug something this step
    lift: float = 0.0            # a drill: how far its centre sits from its asteroid's centre


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
        self.structures: list[Structure] = []
        self.timeline: list[tuple[float, Callable]] = []
        self.kick = 0.0              # screen shake waiting for the camera
        self.screen_flash = 0.0
        self.last_hit = None         # (amount, "shield" or "armor") for the HUD
        self._uid = 0
        self._gun = 0
        self.missiles_loaded = 0
        self.missile_stock: int | None = None     # missiles carried beyond the pods; None = no limit
        self.reload_missiles()
        self.charging = -1.0         # 0 to 1 while you charge the laser, else -1
        self.charge_cancel = 0.0     # 1 down to 0 after you let go of a charge early
        # A real fight (the sandbox) turns these on; the gallery leaves them off.
        self.field = None            # an AsteroidField: rocks block shots, beams and ships
        self.world = None            # (width, height) when space wraps around
        self.collide_bodies = False  # your hull bumps enemy hulls
        self.regen = False           # the shield recharges after a quiet spell
        self.can_die = False
        self.ship_mass = float(DEFENSE["mass"])
        self.bounce = 0.4
        self.armor = int(DEFENSE.get("armor", 0))
        self.ship_down = False
        self.invulnerable = 0.0      # seconds left of the blink after a respawn
        self.quiet = 99.0            # seconds since you last took damage
        self.events: list[tuple] = []   # what happened, for the HUD and the play log

    # ------------------------------------------------------------ setup

    def clear(self) -> None:
        for name in ("enemies", "shots", "missiles", "beams", "anims", "rings", "chunks", "streaks",
                     "lanes", "structures", "timeline"):
            getattr(self, name).clear()
        self.screen_flash = 0.0
        self.ship_flash = 0.0
        self.shield_show = 0.0
        self.reload_missiles()

    def reload_missiles(self) -> None:
        """Fill the pods: a full salvo, or as much as you carry when missiles are limited."""
        salvo = int(WEAPONS["missile"]["salvo"])
        if self.missile_stock is None:
            self.missiles_loaded = salvo
        else:
            total = self.missiles_loaded + self.missile_stock
            self.missiles_loaded = min(salvo, total)
            self.missile_stock = total - self.missiles_loaded
        self.missile_wait = 0.0        # until the next missile can launch
        self.missile_reload = 0.0      # reload time left; above 0 while the rack refills
        self.missile_idle = 0.0        # time since the last launch
        self._pod = 0

    @property
    def missile_ready(self) -> bool:
        return self.missiles_loaded > 0 and self.missile_wait <= 0 and self.missile_reload <= 0

    @property
    def missiles_total(self) -> int | None:
        """Missiles on the pods plus those carried, or None when they never run out."""
        return None if self.missile_stock is None else self.missiles_loaded + self.missile_stock

    def set_missiles(self, total: int) -> None:
        """Limit missiles to what you carry, starting with `total` (some of them on the pods)."""
        self.missiles_loaded = 0
        self.missile_stock = max(0, int(total))
        self.reload_missiles()

    def add_missiles(self, n: int) -> None:
        """Missiles bought at the station go on the pods straight away if there's room."""
        if self.missile_stock is None:
            return
        self.missile_stock += max(0, int(n))
        if self.missile_reload <= 0:
            self.reload_missiles()

    def uid(self) -> int:
        self._uid += 1
        return self._uid

    def recentre(self) -> None:
        """In wrapping space, bring everything to its copy nearest your ship, so every distance on
        the stage is the short way round."""
        if self.world is None:
            return
        W, H = self.world
        cx, cy = self.ship.x, self.ship.y

        def shift(o, xa="x", ya="y"):
            x, y = getattr(o, xa), getattr(o, ya)
            nx = cx + wrap_delta(x - cx, W)
            ny = cy + wrap_delta(y - cy, H)
            if nx != x or ny != y:
                setattr(o, xa, nx)
                setattr(o, ya, ny)
                return nx - x, ny - y
            return 0.0, 0.0

        for e in self.enemies:
            dx, dy = shift(e)
            if (dx or dy) and e.brain is not None and hasattr(e.brain, "moved"):
                e.brain.moved(dx, dy)
        for group in (self.shots, self.missiles, self.anims, self.rings, self.chunks, self.lanes, self.structures):
            for o in group:
                shift(o)
        for b in self.beams:
            dx, dy = shift(b)
            b.end = (b.end[0] + dx, b.end[1] + dy)
        for st_ in self.streaks:
            dx, dy = shift(st_, "x0", "y0")
            st_.x1 += dx
            st_.y1 += dy

    def _move_ship(self, dx: float, dy: float) -> None:
        ship = self.ship
        ship.x += dx
        ship.y += dy
        ship.ux += dx
        ship.uy += dy

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
        self.events.append(("fire", "auto"))

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
        self.events.append(("fire", "sniper"))

    def fire_missile(self, target: Enemy | None) -> bool:
        """Launch one missile, from the left and right pods in turn. Missiles leave `gap` seconds
        apart; when the salvo is spent the rack reloads. Returns False if none was ready."""
        if not self.missile_ready:
            return False
        w = WEAPONS["missile"]
        ship = self.ship
        right, fwd = PODS[self._pod % 2]
        self._pod += 1
        x, y = to_world(ship.x, ship.y, ship.angle, right, fwd)
        # Out sideways off the rail first, then the motor lights and it turns in.
        h = ship.angle + (-55 if right < 0 else 55)
        self.missiles.append(Missile(
            "player", x, y, h, w["launch_speed"], w["max_speed"], w["accel"], w["turn_rate"],
            w["damage"], w["range"] / w["max_speed"] * 1.6, target=target,
            blast_radius=w["blast_radius"], blast_push=w["blast_push"], uid=self.uid()))
        self.anims.append(Anim("muzzle", ("missile",), 2, 20, x, y, ship.angle,
                               follow=self._ship_follow(right, fwd)))
        self.smoke.burst("smoke", x, y, math.radians(90 - h), 0.9, 9, (8, 32), (0.35, 0.8))
        self.sparks.burst("ion_spark", x, y, math.radians(90 - h), 0.7, 4, (20, 60), (0.08, 0.18))
        # A thump: the launch rocks the ship away from the pod and back a little.
        rx, ry = right_vector(ship.angle)
        fx, fy = forward_vector(ship.angle)
        side = 1.0 if right < 0 else -1.0
        ship.vx += rx * side * 10 - fx * 8
        ship.vy += ry * side * 10 - fy * 8
        self.kick += 0.1
        self.missiles_loaded -= 1
        self.missile_wait = float(w["gap"])
        self.missile_idle = 0.0
        if self.missiles_loaded <= 0 and (self.missile_stock is None or self.missile_stock > 0):
            self.missile_reload = float(w["reload"])
        self.events.append(("fire", "missile"))
        return True

    def _step_rack(self, dt: float) -> None:
        w = WEAPONS["missile"]
        self.missile_wait = max(0.0, self.missile_wait - dt)
        self.missile_idle += dt
        if self.missile_reload > 0:
            self.missile_reload -= dt
            if self.missile_reload <= 0:
                self.reload_missiles()
        elif (self.missiles_loaded < int(w["salvo"]) and self.missile_idle >= w["reload"]
              and (self.missile_stock is None or self.missile_stock > 0)):
            # A part-used rack tops up once you have held fire for a reload's time.
            self.reload_missiles()

    def start_laser(self, burst: bool = False) -> Beam:
        """Fire the laser. With `burst` (after its charge-up) it skips the warm-up and opens with a
        flash and a shockwave."""
        w = WEAPONS["laser"]
        ship = self.ship
        x, y = to_world(ship.x, ship.y, ship.angle, *NOSE)
        beam = Beam("player", x, y, ship.angle, w["length"], 5.0, w["dps"], w["duration"],
                    warmup=0.0 if burst else w["warmup"])
        beam.reach = beam.length
        if burst:
            beam.burst = float(w.get("burst", 0.14))
            self.rings.append(Ring("player", x, y, 3, 26, 0.3))
            self.sparks.burst("ion_spark", x, y, math.radians(90 - ship.angle), 0.8, 14, (40, 140), (0.15, 0.4))
            self.kick += 0.35
            self.screen_flash = max(self.screen_flash, 0.12)
        self.beams.append(beam)
        self.events.append(("fire", "laser"))
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

    def ram_hit(self, g: Enemy, x: float, y: float, fx: float, fy: float) -> None:
        """A guard's scoop slams into you at (x, y), travelling along (fx, fy)."""
        spec = ENEMIES["guard"]
        self.damage_player(spec["ram_damage"], x, y, kind="ram", push=spec["ram_speed"] * 0.45, source="guard")
        self.sparks.burst("steel", x, y, math.atan2(-fy, -fx), 1.0, 14, (40, 130), (0.2, 0.5))
        self.sparks.burst("danger_spark", x, y, math.atan2(fy, fx), 0.9, 8, (30, 100), (0.15, 0.35))
        self.anims.append(Anim("flare", ("steel",), 2, 18, x, y))
        self.kick += 0.45
        # The guard bounces back off you.
        self.push_enemy(g, -fx * 150 * g.mass, -fy * 150 * g.mass)

    def ram_rock(self, g: Enemy, x: float, y: float, fx: float, fy: float, rock: int) -> None:
        """A guard's charge ends on a rock: the rock takes the shove and the guard bounces off."""
        spec = ENEMIES["guard"]
        f = self.field
        if f is not None:
            j = spec["ram_speed"] * g.mass * 0.5
            f.vx[rock] += fx * j / f.m[rock]
            f.vy[rock] += fy * j / f.m[rock]
        self.sparks.burst("steel", x, y, math.atan2(-fy, -fx), 1.0, 10, (30, 110), (0.2, 0.45))
        self.smoke.burst("dust", x, y, math.atan2(-fy, -fx), 1.0, 6, (10, 50), (0.3, 0.7))
        self.kick += 0.15
        self.push_enemy(g, -fx * 110 * g.mass, -fy * 110 * g.mass)
        self.events.append(("rock", "enemy", "ram"))

    def mothership_beam(self, ms: Enemy) -> Beam:
        spec = ENEMY_WEAPONS["mothership_laser"]
        x, y = to_world(ms.x, ms.y, ms.heading, *EMITTER)
        beam = Beam("enemy", x, y, ms.heading, 420.0, 21.0, spec["dps"], spec["fire_time"])
        beam.reach = beam.length
        self.beams.append(beam)
        self.kick += 0.35
        return beam

    # ------------------------------------------------------------ damage

    def damage_enemy(self, e: Enemy, amount: float, x: float, y: float, flash: float = 1.0,
                     source: str = "") -> None:
        """`flash` is how bright the white hit flash starts (a laser burns without flashing).
        `source` is what did it (auto, sniper, missile, laser, ram), for the play log."""
        if not e.targetable:
            return
        if e.immune:
            e.flash = max(e.flash, flash * 0.5)
            e.since_hit = 0.0
            return
        amount = min(amount, e.health)
        e.health -= amount
        e.flash = max(e.flash, flash)
        e.since_hit = 0.0
        self.events.append(("hit", source, e.kind, amount))
        if e.health <= 0:
            e.health = 0.0
            self.events.append(("kill", e.kind, source, e.age))
            self.destroy(e)

    def push_enemy(self, e: Enemy, vx: float, vy: float) -> None:
        """Enemies only drift when something hits them hard: heavier ones barely move."""
        if e.kind == "mothership":
            return
        e.vx += vx / e.mass
        e.vy += vy / e.mass

    def damage_structure(self, t: Structure, amount: float, x: float, y: float, source: str = "") -> None:
        """An enemy hit one of your drills (or your base)."""
        if not t.alive:
            return
        t.flash = 1.0
        t.since_hit = 0.0
        if t.immune:
            return
        amount = min(amount, t.health)
        t.health -= amount
        self.events.append(("struct_hit", t.kind, t.uid, amount, source))
        if t.health <= 0:
            t.health = 0.0
            t.alive = False
            self.events.append(("struct_lost", t.kind, t.uid))
            self.anims.append(Anim("explosion", ("player", 49, t.uid % 3), 6, 12, t.x, t.y))
            self.anims.append(Anim("explosion", ("player", 33, 1), 6, 14, t.x + 6, t.y - 4, delay=0.15))
            self.rings.append(Ring("player", t.x, t.y, 6, 36, 0.4))
            for _ in range(6):
                self._chunk("steel", t.x, t.y, 30, 110)
            self.sparks.burst("ion_spark", t.x, t.y, 0.0, math.pi, 20, (30, 120), (0.3, 0.7))
            self.smoke.burst("smoke", t.x, t.y, 0.0, math.pi, 14, (10, 50), (0.6, 1.2))

    def damage_player(self, amount: float, x: float, y: float, kind: str = "shot", push: float = 0.0,
                      source: str = "") -> str:
        """Returns "shield" or "armor": where the hit landed. `push` shoves the ship away from it.
        `source` is what did it (an enemy class, a rock), for the play log."""
        ship = self.ship
        come_from = angle_to(x - ship.x, y - ship.y)          # direction of the hit, from the ship
        if push:
            fx, fy = forward_vector(come_from)
            ship.vx -= fx * push
            ship.vy -= fy * push
        if self.invulnerable > 0 or self.ship_down:
            return "shield"
        if amount > 0:
            self.quiet = 0.0
        if self.shield > 0:
            taken = min(self.shield, amount)
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
            if taken > 0:
                self.events.append(("hurt", source or kind, kind, taken, "shield"))
            return "shield"
        amount *= self.armor_factor
        self.hull = max(0.0, self.hull - amount)
        self.ship_flash = min(1.0, 0.45 + amount / 30)
        self.anims.append(Anim("armor_hit", (), 4, 18, x, y))
        self.sparks.burst("spark", x, y, math.radians(90 - come_from), 0.8, 5 + int(amount / 2),
                          (30, 90), (0.15, 0.4))
        self.kick += min(0.5, 0.08 + amount / 40)
        self.last_hit = (amount, "armor")
        if amount > 0:
            self.events.append(("hurt", source or kind, kind, amount, "armor"))
        self._check_down(source or kind)
        return "armor"

    @property
    def armor_factor(self) -> float:
        """How much of a hull hit gets through your armor."""
        return max(0.0, 1.0 - self.armor * float(DEFENSE.get("armor_block", 0.0)))

    def _check_down(self, source: str) -> None:
        if self.hull > 0 or not self.can_die or self.ship_down:
            return
        self.ship_down = True
        self.ship_visible = False
        ship = self.ship
        self.events.append(("down", source))
        self.anims.append(Anim("explosion", ("player", 49, 1), 6, 12, ship.x, ship.y, vx=ship.vx * 0.3,
                               vy=ship.vy * 0.3, drag=2))
        self.anims.append(Anim("explosion", ("player", 33, 2), 6, 14, ship.x + 5, ship.y - 3, delay=0.12))
        self.rings.append(Ring("player", ship.x, ship.y, 6, 40, 0.4))
        for _ in range(8):
            self._chunk("steel", ship.x, ship.y, 40, 140, carry=(ship.vx * 0.4, ship.vy * 0.4))
        self.sparks.burst("ion_spark", ship.x, ship.y, 0.0, math.pi, 30, (40, 160), (0.3, 0.8))
        self.smoke.burst("smoke", ship.x, ship.y, 0.0, math.pi, 20, (10, 60), (0.6, 1.4))
        self.kick += 1.0
        self.screen_flash = max(self.screen_flash, 0.6)
        self.beams = [b for b in self.beams if b.owner != "player"]
        ship.vx = ship.vy = 0.0

    def respawn(self, x: float, y: float, invulnerable: float = 2.0) -> None:
        """Back in the fight with full shield and hull, blinking for a moment."""
        ship = self.ship
        self._move_ship(x - ship.x, y - ship.y)
        ship.vx = ship.vy = 0.0
        ship.angle = 0.0
        self.ship_down = False
        self.ship_visible = True
        self.shield = self.shield_max
        self.hull = self.hull_max
        self.invulnerable = invulnerable
        self.reload_missiles()
        self.rings.append(Ring("player", x, y, 30, 6, 0.35))

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
            e.age += dt
            if e.dying >= 0:
                e.dying += dt
                e.flash = max(e.flash, 0.35 + 0.35 * math.sin(e.dying * 40))
                e.mx = e.my = 0.0
            e.x += (e.vx + e.mx) * dt
            e.y += (e.vy + e.my) * dt
            keep = math.exp(-2.5 * dt)          # a shove dies down; scripted movement sets its own speed
            e.vx *= keep
            e.vy *= keep
        self.enemies = [e for e in self.enemies if e.alive]
        for t in self.structures:
            t.clock += dt
            t.since_hit += dt
            t.flash = max(0.0, t.flash - dt * 8)
        self.structures = [t for t in self.structures if t.alive]
        if self.collide_bodies:
            self._separate_enemies()
            if self.ship_visible:
                self._collide_ship_enemies()
        if self.field is not None:
            self._collide_enemy_rocks()

        self.ship_flash = max(0.0, self.ship_flash - dt * 6)
        self.shield_show = max(0.0, self.shield_show - dt)
        self.screen_flash = max(0.0, self.screen_flash - dt * 2.5)
        self.invulnerable = max(0.0, self.invulnerable - dt)
        self.quiet += dt
        if self.regen and not self.ship_down and self.quiet >= DEFENSE.get("shield_delay", 3.0):
            self.shield = min(self.shield_max, self.shield + DEFENSE.get("shield_regen", 10.0) * dt)

        self._step_rack(dt)
        self._step_shots(dt)
        self._step_missiles(dt)
        self._step_beams(dt)
        self._step_effects(dt)

    # ------------------------------------------------------------ bumping

    def _collide_ship_enemies(self) -> None:
        """Your hull against each enemy hull, pixel for pixel: the two push apart, trade momentum by
        mass, and each takes damage from how hard the hit was."""
        ship = self.ship
        pts = shapes.mask_points()
        fx, fy = forward_vector(ship.angle)
        rx, ry = right_vector(ship.angle)
        wx = ship.x + pts[:, 0] * rx + pts[:, 1] * fx
        wy = ship.y + pts[:, 0] * ry + pts[:, 1] * fy
        my_reach = shapes.reach()
        for e in self.enemies:
            if not e.alive or e.fade_in < 1.0 or e.ramming:
                continue
            ram = e.ram if e.kind == "guard" else 0
            if dist(ship.x, ship.y, e.x, e.y) > my_reach + shapes.reach(e.kind, ram) + 1:
                continue
            mask = e.mask
            inside = shapes.hits_many(mask, e.x, e.y, e.sprite_angle, wx, wy)
            if not inside.any():
                continue
            # Push apart along the line from your centre to the middle of the overlap.
            nx, ny = float(wx[inside].mean()) - ship.x, float(wy[inside].mean()) - ship.y
            n = math.hypot(nx, ny)
            if n < 1e-3:
                nx, ny = e.x - ship.x, e.y - ship.y
                n = math.hypot(nx, ny) or 1.0
            nx, ny = nx / n, ny / n
            inv_s = 1.0 / max(0.05, self.ship_mass)
            inv_e = 0.0 if e.kind == "mothership" else 1.0 / e.mass
            share_s = inv_s / (inv_s + inv_e)
            contact = (float(wx[inside].mean()), float(wy[inside].mean()))
            for _ in range(24):
                self._move_ship(-nx * share_s, -ny * share_s)
                wx -= nx * share_s
                wy -= ny * share_s
                e.x += nx * (1 - share_s)
                e.y += ny * (1 - share_s)
                if not shapes.hits_many(mask, e.x, e.y, e.sprite_angle, wx, wy).any():
                    break
            rel = (e.vx + e.mx - ship.vx) * nx + (e.vy + e.my - ship.vy) * ny
            if rel >= 0:
                continue
            j = -(1 + self.bounce) * rel / (inv_s + inv_e)
            ship.vx -= j * inv_s * nx
            ship.vy -= j * inv_s * ny
            e.vx += j * inv_e * nx
            e.vy += j * inv_e * ny
            self._bump_damage(j, inv_s, inv_e, e, *contact)

    def _bump_damage(self, j: float, inv_s: float, inv_e: float, e: Enemy | None, x: float, y: float) -> None:
        """Damage from a collision grows with how much it changed each side's speed."""
        spec = DEFENSE.get("impact", {})
        safe = spec.get("safe_speed", 120.0)
        hard = j * inv_s
        self.sparks.burst("spark", x, y, 0.0, math.pi, 2 + int(min(12, hard / 25)), (20, 90), (0.1, 0.3))
        if e is not None:
            self.sparks.burst("alien_debris", x, y, 0.0, math.pi, 1 + int(min(6, hard / 60)), (20, 70), (0.2, 0.4))
        self.kick += min(0.6, hard / 600)
        self.events.append(("bump", e.kind if e is not None else "rock", hard))
        if hard > safe:
            self.damage_player((hard - safe) * spec.get("player_damage", 0.05), x, y, kind="impact",
                               source=e.kind if e is not None else "rock")
        if e is not None:
            hit = j * inv_e if inv_e > 0 else 0.0
            if hit > safe:
                self.damage_enemy(e, (hit - safe) * spec.get("enemy_damage", 0.1), x, y, flash=0.8, source="ram")

    def bump_rock(self, impulse: float, x: float, y: float) -> None:
        """Your ship hit a rock (the field already bounced it): sparks, shake, and damage if hard."""
        self._bump_damage(impulse, 1.0 / max(0.05, self.ship_mass), 0.0, None, x, y)

    def _separate_enemies(self) -> None:
        """Enemy hulls don't stack: overlapping ones are eased apart, the lighter one moving more."""
        live = [e for e in self.enemies if e.alive and e.fade_in >= 1.0 and e.kind != "mothership"]
        for i, a in enumerate(live):
            for b in live[i + 1:]:
                dx, dy = b.x - a.x, b.y - a.y
                r = a.body_r + b.body_r
                d2 = dx * dx + dy * dy
                if d2 >= r * r:
                    continue
                d = math.sqrt(d2) or 0.01
                over = (r - d) * 0.5
                ia, ib = 1 / a.mass, 1 / b.mass
                nx, ny = (dx / d, dy / d) if d > 0.01 else (1.0, 0.0)
                a.x -= nx * over * ia / (ia + ib) * 2
                a.y -= ny * over * ia / (ia + ib) * 2
                b.x += nx * over * ib / (ia + ib) * 2
                b.y += ny * over * ib / (ia + ib) * 2

    def _collide_enemy_rocks(self) -> None:
        """Enemy hulls slide off rocks. Their steady flying never shoves a rock (they have no
        momentum to give); only a knock, from a blast or a bump, carries into it."""
        f = self.field
        for e in self.enemies:
            if not e.alive or e.kind == "mothership":
                continue
            r = e.body_r
            idx, dx, dy = f.near(e.x, e.y, r, r)
            for i, ddx, ddy in zip(idx, dx, dy):
                d = math.hypot(ddx, ddy)
                over = f.r[i] + r - d
                if over <= 0:
                    continue
                nx, ny = (ddx / d, ddy / d) if d > 1e-6 else (1.0, 0.0)
                e.x -= nx * over
                e.y -= ny * over
                rel = (f.vx[i] - e.vx) * nx + (f.vy[i] - e.vy) * ny
                if rel < -15:
                    inv_e, inv_a = 1 / e.mass, 1 / f.m[i]
                    j = -1.3 * rel / (inv_e + inv_a)
                    e.vx -= j * inv_e * nx
                    e.vy -= j * inv_e * ny
                    f.vx[i] += j * inv_a * nx
                    f.vy[i] += j * inv_a * ny

    def rock_hit(self, x0: float, y0: float, x1: float, y1: float, pad: float = 0.0):
        """Where the path from (x0, y0) to (x1, y1) first touches a rock: (x, y, rock) or None."""
        f = self.field
        if f is None or not len(f):
            return None
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        hx, hy = abs(x1 - x0) / 2 + pad, abs(y1 - y0) / 2 + pad
        idx, dx, dy = f.near(mx, my, hx, hy)
        if not len(idx):
            return None
        sx, sy = x1 - x0, y1 - y0
        L2 = sx * sx + sy * sy
        best = None
        for i, cdx, cdy in zip(idx, dx, dy):
            # Rock centre relative to the start of the path.
            cx, cy = mx + cdx - x0, my + cdy - y0
            r = f.r[i] + pad
            if L2 < 1e-9:
                if cx * cx + cy * cy <= r * r:
                    return x0, y0, int(i)
                continue
            # Solve |t*s - c| = r for the first t in [0, 1].
            b = -(cx * sx + cy * sy)
            c = cx * cx + cy * cy - r * r
            disc = b * b - L2 * c
            if disc < 0:
                continue
            t = (-b - math.sqrt(disc)) / L2
            if c <= 0:
                t = 0.0
            if 0.0 <= t <= 1.0 and (best is None or t < best[0]):
                best = (t, int(i))
        if best is None:
            return None
        t, i = best
        return x0 + sx * t, y0 + sy * t, i

    def _rock_spark(self, x: float, y: float, angle: float, owner: str) -> None:
        self.anims.append(Anim("flare", ("player" if owner == "player" else "danger",), 2, 26, x, y))
        self.smoke.burst("dust", x, y, angle, 0.9, 3, (10, 40), (0.2, 0.5))

    # ------------------------------------------------------------ shots

    def _step_shots(self, dt: float) -> None:
        keep = []
        for s in self.shots:
            s.clock += dt
            x0, y0 = s.x, s.y
            s.x += s.vx * dt
            s.y += s.vy * dt
            s.life -= dt
            rock = self.rock_hit(x0, y0, s.x, s.y, 0.5) if self.field is not None else None
            if rock is not None:
                # Only the part of the path before the rock can hit anything.
                s.x, s.y = rock[0], rock[1]
            if s.owner == "player":
                alive = self._player_shot_hits(s, x0, y0)
            else:
                alive = self._enemy_shot_hits(s, x0, y0)
            if alive and rock is not None:
                self._rock_spark(s.x, s.y, math.atan2(-s.vy, -s.vx), s.owner)
                self.events.append(("rock", s.owner, s.kind))
                alive = False
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
        self.damage_enemy(e, s.damage, x, y, flash=1.0 if s.kind == "sniper" else 0.55, source=s.kind)

    def _enemy_shot_hits(self, s: Shot, x0: float, y0: float) -> bool:
        for t in self.structures:
            if t.alive and self._segment_near(x0, y0, s.x, s.y, t.x, t.y, t.radius + s.pad):
                back = math.atan2(-s.vy, -s.vx)
                ux, uy, d = s.x - t.x, s.y - t.y, max(1e-6, math.hypot(s.x - t.x, s.y - t.y))
                px, py = t.x + ux / d * t.radius, t.y + uy / d * t.radius
                self.anims.append(Anim("flare", ("danger",), 2, 20, px, py))
                self.sparks.burst("danger_spark", px, py, back, 0.9, 3, (20, 70), (0.1, 0.3))
                self.damage_structure(t, s.damage, px, py, source=s.kind)
                return False
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
            rock = self.rock_hit(x0, y0, m.x, m.y, 1.0) if self.field is not None and m.clock > 0.05 else None
            if rock is not None:
                m.x, m.y = rock[0], rock[1]
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
            self.damage_enemy(e, m.damage * falloff, m.x, m.y, source="missile")

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
                self._beam_reach(b, fx, fy)
                b.end = (b.x + fx * b.reach, b.y + fy * b.reach)
                if b.firing and self.ship_visible:
                    self._player_beam(b, fx, fy, dt)
            else:
                self._beam_reach(b, fx, fy)
                b.end = (b.x + fx * b.reach, b.y + fy * b.reach)
                if b.firing:
                    self._enemy_beam(b, fx, fy, dt)
            if not b.done:
                keep.append(b)
        self.beams = keep

    def _beam_reach(self, b: Beam, fx: float, fy: float) -> None:
        """How far the beam gets. Rocks stop any beam, and the mothership's hull stops yours; every
        other hull it simply burns straight through."""
        b.reach = b.length
        if b.owner == "player":
            for e in self.enemies:
                if e.kind != "mothership" or not e.targetable:
                    continue
                r = shapes.radius_of(e.mask)
                if not self._segment_near(b.x, b.y, b.x + fx * b.reach, b.y + fy * b.reach, e.x, e.y, r + b.width):
                    continue
                d = max(0.0, (e.x - b.x) * fx + (e.y - b.y) * fy - r - b.width)
                while d <= b.reach:
                    if shapes.hits(e.mask, e.x, e.y, e.sprite_angle, b.x + fx * d, b.y + fy * d, b.width / 2):
                        b.reach = d + 1.0
                        break
                    d += 1.5
            for t in self.structures:
                if t.kind != "base" or not t.alive:
                    continue
                # Your own base stops your laser too.
                along = (t.x - b.x) * fx + (t.y - b.y) * fy
                side = abs((t.x - b.x) * fy - (t.y - b.y) * fx)
                R = t.radius + b.width / 2
                if side < R and along + R > 0:
                    d = max(0.0, along - math.sqrt(max(0.0, R * R - side * side)))
                    if d < b.reach:
                        b.reach = d
        if self.field is None:
            return
        hit = self.rock_hit(b.x, b.y, b.x + fx * b.reach, b.y + fy * b.reach, b.width / 2 - 1)
        if hit is not None:
            b.reach = max(0.0, dist(b.x, b.y, hit[0], hit[1]))
            if b.firing and self.rng.random() < 0.5:
                self.smoke.burst("dust", hit[0], hit[1], math.atan2(-fy, -fx), 1.0, 1, (10, 50), (0.2, 0.5))
                self.sparks.burst("ion_spark" if b.owner == "player" else "danger_spark", hit[0], hit[1],
                                  math.atan2(-fy, -fx), 1.0, 1, (20, 90), (0.1, 0.25))

    def _player_beam(self, b: Beam, fx: float, fy: float, dt: float) -> None:
        for e in self.enemies:
            if not e.targetable:
                continue
            r = shapes.radius_of(e.mask)
            if not self._segment_near(b.x, b.y, b.end[0], b.end[1], e.x, e.y, r + b.width):
                continue
            d = 0.0
            while d <= b.reach:
                px, py = b.x + fx * d, b.y + fy * d
                if shapes.hits(e.mask, e.x, e.y, e.sprite_angle, px, py, b.width / 2):
                    b.contacts[e.uid] = (px, py)
                    e.heat = 1.0
                    if self.rng.random() < dt * 40:
                        self.sparks.burst("ion_spark", px, py, math.atan2(-fy, -fx), 1.0, 2, (30, 110), (0.1, 0.3))
                    if self.rng.random() < dt * 30:
                        self.sparks.burst("alien_debris", px, py, math.atan2(-fy, -fx), 1.2, 1, (20, 80), (0.2, 0.5))
                    self.damage_enemy(e, b.dps * dt, px, py, flash=0.0, source="laser")
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
            if side > R + half or along < -R or along > b.reach + R:
                return None
            # Head on, the beam ends where its centre line meets the bubble; a graze ends level with you.
            d = along - math.sqrt(max(0.0, R * R - min(side, R) ** 2))
            return b.x + fx * d, b.y + fy * d
        d = 0.0
        while d <= b.reach:
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
        if self.invulnerable > 0:
            return
        self.quiet = 0.0
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
            self.hull = max(0.0, self.hull - b.dps * dt * self.armor_factor)
            self.ship_flash = max(self.ship_flash, 0.7)
            if self.rng.random() < dt * 20:
                self.anims.append(Anim("armor_hit", (), 4, 18, px, py))
            self._check_down("mothership")
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
