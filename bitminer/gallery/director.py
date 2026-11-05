"""Runs one gallery scene at a time on a combat stage, and loops it.

A scene is a script: a generator that sets up targets or attackers and then yields how many
seconds to wait before its next step. While it waits the stage keeps running, along with any
"brains" the script gave its enemies (small functions called every frame to move or aim them).

In auto mode the ship holds its post and a pilot aims and fires for you. In free-fly you fly the
ship with the flight tuning and fire the selected weapon yourself; enemy attacks still come at
wherever the ship is.

Pure Python with no graphics, so the scenes can be tested without a window.
"""

from __future__ import annotations

import math
from typing import Callable, Iterator

from ..combat.specs import GALLERY, WEAPONS
from ..combat.stage import Enemy, Stage, dist
from ..flight import Controls, angle_to, wrap_angle

ARENA = (440.0, 300.0)       # free-fly keeps the ship within this far of the centre
POST_SPRING = 14.0           # how hard the auto pilot pulls the ship back to its post
POST_DAMP = 7.0
REST = 0.9                   # pause after a scene's script ends, before it starts again
MAX_REST = 4.0               # never wait longer than this for effects to finish

Script = Iterator[float]


class Director:
    def __init__(self, stage: Stage, tuning, centre: tuple[float, float]):
        self.stage = stage
        self.tuning = tuning
        self.centre = centre
        self.scene = None
        self.auto = True
        self.weapon = "auto"          # free-fly weapon
        self.time = 0.0               # seconds since the scene (re)started
        self.loops = 0
        self.post = centre
        self.post_fn: Callable[[], tuple[float, float]] | None = None   # a moving post, if set
        self.aim: object = None       # where the pilot points the ship: an angle, a point or an Enemy
        self.brains: list[Callable[[float], None]] = []
        self.script: Script | None = None
        self.wait = 0.0
        self.rest = 0.0
        self.cooldown = 0.0
        self.beam = None
        self.finished = 0             # scene runs finished since start, for recording

    # ------------------------------------------------------------ scenes

    def start(self, scene, keep_ship: bool = False) -> None:
        """Begin `scene` from the top. In free-fly the ship stays where it is."""
        st = self.stage
        self.scene = scene
        st.clear()
        st.time = 0.0
        self.time = 0.0
        self.brains = []
        self.aim = None
        self.beam = None
        self.cooldown = 0.0
        self.post = self.centre
        self.post_fn = None
        st.ship_visible = True
        if self.auto and not keep_ship:
            st.ship.x, st.ship.y = self.centre
            st.ship.vx = st.ship.vy = 0.0
            st.ship.angle = 0.0
        defense = scene.defense
        st.shield = st.shield_max if defense == "shield" else (
            float(GALLERY["shield_breaks_at"]) if defense == "shield_breaks" else 0.0)
        st.hull = st.hull_max
        self.script = scene.script(self)
        self.wait = 0.0
        self.rest = 0.0

    def restart(self) -> None:
        if self.scene is not None:
            self.start(self.scene, keep_ship=not self.auto)

    @property
    def running(self) -> bool:
        return self.script is not None

    # ------------------------------------------------------------ helpers for scripts

    def at(self, dx: float, dy: float) -> tuple[float, float]:
        """A point relative to the arena centre."""
        return self.centre[0] + dx, self.centre[1] + dy

    def spawn(self, kind: str, dx: float, dy: float, health: float | None = None, heading: float | None = None,
              warp: bool = True) -> Enemy:
        x, y = self.at(dx, dy)
        if heading is None:
            heading = angle_to(self.stage.ship.x - x, self.stage.ship.y - y)
        return self.stage.spawn(kind, x, y, heading=heading, health=health, warp=warp)

    def brain(self, fn: Callable[[float], None]) -> None:
        self.brains.append(fn)

    def face_ship(self, e: Enemy, rate: float = 360.0, dt: float = 0.0) -> None:
        want = angle_to(self.stage.ship.x - e.x, self.stage.ship.y - e.y)
        if rate <= 0 or dt <= 0:
            e.heading = want
        else:
            step = rate * dt
            e.heading = wrap_angle(e.heading + max(-step, min(step, wrap_angle(want - e.heading))))

    def anchor(self, e: Enemy, point_fn: Callable[[], tuple[float, float]], stiff: float = 9.0,
               face: str | None = "ship") -> None:
        """Keep `e` near a (possibly moving) point with a spring, so hits can still shove it."""
        damp = 2 * math.sqrt(stiff) * 0.9

        def think(dt: float) -> None:
            if not e.alive or e.dying >= 0:
                return
            ax, ay = point_fn()
            e.vx += ((ax - e.x) * stiff - e.vx * damp) * dt
            e.vy += ((ay - e.y) * stiff - e.vy * damp) * dt
            if face == "ship":
                self.face_ship(e)
            elif face == "motion" and math.hypot(e.vx, e.vy) > 15:
                e.heading = angle_to(e.vx, e.vy)
        self.brain(think)

    def aim_error(self) -> float:
        """How far the ship's nose is from where the pilot wants it, in degrees."""
        want = self._aim_angle()
        return 0.0 if want is None else abs(wrap_angle(want - self.stage.ship.angle))

    def lead(self, x: float, y: float, vx: float, vy: float, speed: float) -> tuple[float, float]:
        """Where to aim a shot of `speed` so it meets something at (x, y) moving at (vx, vy)."""
        ship = self.stage.ship
        t = dist(ship.x, ship.y, x, y) / max(1.0, speed)
        for _ in range(2):
            px, py = x + vx * t, y + vy * t
            t = dist(ship.x, ship.y, px, py) / max(1.0, speed)
        return x + vx * t, y + vy * t

    # Your weapons, as the auto pilot uses them. They do nothing in free-fly, where you fire.

    def fire(self, weapon: str, target: Enemy | None = None) -> None:
        if not self.auto:
            return
        self._fire(weapon, target)

    def _fire(self, weapon: str, target: Enemy | None = None) -> None:
        st = self.stage
        if weapon == "auto":
            st.fire_auto()
        elif weapon == "sniper":
            st.fire_sniper()
        elif weapon == "missile":
            st.fire_missiles(target)
        elif weapon == "laser":
            self.beam = st.start_laser()

    # ------------------------------------------------------------ the frame

    def step(self, dt: float, controls: Controls | None = None, trigger: bool = False,
             cursor: tuple[float, float] | None = None) -> None:
        """Advance everything by dt. `controls`, `trigger` and `cursor` (a world point) are free-fly input."""
        st = self.stage
        self.time += dt
        self.cooldown = max(0.0, self.cooldown - dt)

        if self.script is not None:
            self.wait -= dt
            while self.script is not None and self.wait <= 0:
                try:
                    self.wait += float(next(self.script))
                except StopIteration:
                    self.script = None
        for think in list(self.brains):
            think(dt)

        if self.auto:
            self._pilot(dt)
        else:
            self._free_fly(dt, controls or Controls(), trigger, cursor)
        st.step(dt)

        if self.script is None:
            self.rest += dt
            quiet = not (st.shots or st.missiles or st.beams or any(e.dying >= 0 for e in st.enemies))
            if (self.rest >= REST and quiet) or self.rest >= MAX_REST:
                self.finished += 1
                self.loops += 1
                self.restart()

    def _aim_angle(self) -> float | None:
        ship = self.stage.ship
        a = self.aim
        if a is None:
            return None
        if isinstance(a, (int, float)):
            return float(a)
        if isinstance(a, Enemy):
            if not a.alive:
                return None
            return angle_to(a.x - ship.x, a.y - ship.y)
        if callable(a):
            a = a()
            if a is None:
                return None
            if isinstance(a, (int, float)):
                return float(a)
        return angle_to(a[0] - ship.x, a[1] - ship.y)

    def _pilot(self, dt: float) -> None:
        """Hold the post and turn toward the aim, at the tuned turn rate."""
        ship = self.stage.ship
        want = self._aim_angle()
        if want is not None:
            step = self.tuning.turn_rate * dt
            ship.angle = wrap_angle(ship.angle + max(-step, min(step, wrap_angle(want - ship.angle))))
        px, py = self.post_fn() if self.post_fn else self.post
        ship.vx += ((px - ship.x) * POST_SPRING - ship.vx * POST_DAMP) * dt
        ship.vy += ((py - ship.y) * POST_SPRING - ship.vy * POST_DAMP) * dt
        ship.x += ship.vx * dt
        ship.y += ship.vy * dt
        ship.ux += ship.vx * dt
        ship.uy += ship.vy * dt

    def _free_fly(self, dt: float, controls: Controls, trigger: bool, cursor) -> None:
        st = self.stage
        ship = st.ship
        ship.step(controls, self.tuning, dt, 1e9, 1e9)
        # Walls keep the fight in view: the ship bounces softly off the edge of the arena.
        cx, cy = self.centre
        if abs(ship.x - cx) > ARENA[0]:
            edge = cx + math.copysign(ARENA[0], ship.x - cx)
            ship.ux += edge - ship.x
            ship.x = edge
            ship.vx = -ship.vx * 0.4
        if abs(ship.y - cy) > ARENA[1]:
            edge = cy + math.copysign(ARENA[1], ship.y - cy)
            ship.uy += edge - ship.y
            ship.y = edge
            ship.vy = -ship.vy * 0.4
        if not trigger or self.cooldown > 0:
            return
        w = WEAPONS[self.weapon]
        if self.weapon == "laser":
            if self.beam is not None and not self.beam.done:
                return
            self._fire("laser")
            self.cooldown = w["warmup"] + w["duration"] + 0.35
            return
        target = None
        if self.weapon == "missile":
            live = st.live_enemies
            if live:
                cx_, cy_ = cursor or (ship.x, ship.y)
                target = min(live, key=lambda e: dist(e.x, e.y, cx_, cy_))
        self._fire(self.weapon, target)
        self.cooldown = 1.0 / w["fire_rate"]


def wait_until(cond: Callable[[], bool], limit: float = 99.0, tick: float = 1 / 60) -> Script:
    """Yield frames until `cond()` is true or `limit` seconds pass."""
    t = 0.0
    while not cond() and t < limit:
        yield tick
        t += tick


def health_for(weapon: str, target: str) -> float:
    """Gallery health: enough for one showing of `weapon` to destroy one `target`."""
    w = WEAPONS[weapon]
    g = GALLERY
    if weapon == "auto":
        return g["auto_seconds"][target] * w["fire_rate"] * w["damage"]
    if weapon == "sniper":
        return g["sniper_hits"][target] * w["damage"] - 1
    if weapon == "missile":
        return g["missile_hits"][target] * w["damage"] - 1
    return g["laser_seconds"][target] * w["dps"]

