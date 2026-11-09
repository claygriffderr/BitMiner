"""The combat sandbox without graphics: your ship in the asteroid field, the waves, your weapons
and respawns. The sandbox screen draws it; tests and the build machine run it headless.
"""

from __future__ import annotations

import math

from ..flight import Controls, angle_to, wrap_angle
from ..settings import Tuning
from ..world import MAX_FRAME, PHYSICS_STEP, FlightWorld
from .ai import Battle, Waves
from .arsenal import Arsenal, hold_still
from .specs import SANDBOX, WEAPONS
from .stage import Stage, dist


class Sandbox:
    def __init__(self, sparks, smoke, tuning: Tuning, seed: int | None = None):
        seed = int(SANDBOX.get("seed", 7)) if seed is None else seed
        self.tuning = tuning
        self.world = FlightWorld(seed=seed)
        st = self.stage = Stage(sparks, smoke, seed=seed)
        st.ship = self.world.ship
        st.field = self.world.field
        st.world = (self.world.width, self.world.height)
        st.collide_bodies = True
        st.regen = True
        st.can_die = True
        self.battle = Battle(st, seed=seed)
        self.waves = Waves(self.battle)
        self.arsenal = Arsenal(st)
        self.respawn_in = 0.0
        self._down = False
        self.time = 0.0
        self.kills = 0
        self.downs = 0
        self.impacts = []        # rock hits this step, for the dust and sparks

    @property
    def ship(self):
        return self.stage.ship

    def step(self, dt: float, controls: Controls, trigger: bool, cursor: tuple[float, float] | None = None) -> list:
        """Advance by dt seconds. Returns what happened on the stage this step (its events)."""
        dt = min(max(dt, 0.0), MAX_FRAME)
        st = self.stage
        st.events = []
        if dt == 0:
            return st.events
        self.time += dt
        tuning = self.tuning
        st.ship_mass = max(0.05, tuning.mass)
        st.bounce = tuning.bounce
        world = self.world
        field = world.field
        n = max(1, math.ceil(dt / PHYSICS_STEP - 1e-9))
        h = dt / n
        self.impacts = []
        controls = hold_still(self.arsenal, controls, dt)
        for _ in range(n):
            if not st.ship_down:
                st.ship.step(controls, tuning, h, world.width, world.height)
                self.impacts += field.collide_ship(st.ship, st.ship_mass, tuning.bounce)
            field.step(h)
        for hit in self.impacts:
            dv = hit.impulse / st.ship_mass
            if dv >= 12:                                # resting contact and grazes don't count
                st.bump_rock(hit.impulse, hit.x, hit.y)
                st.smoke.burst("dust", hit.x + hit.nx * 2, hit.y + hit.ny * 2, math.atan2(-hit.ny, -hit.nx),
                               1.0, int(min(14, max(2, dv / 18))), (8, 30 + dv * 0.2), (0.4, 1.0))

        st.recentre()
        self.waves.step(dt)
        self.battle.step(dt)
        self.arsenal.step(dt, trigger and not st.ship_down, cursor)
        st.step(dt)

        self.kills += sum(1 for ev in st.events if ev[0] == "kill")
        if st.ship_down and not self._down:
            self.downs += 1
            self.respawn_in = float(SANDBOX["respawn"])
        self._down = st.ship_down
        if st.ship_down:
            self.respawn_in -= dt
            if self.respawn_in <= 0:
                st.respawn(st.ship.x, st.ship.y, float(SANDBOX["invulnerable"]))
                self.arsenal.cooldown = 0.0
                self._down = False
                st.events.append(("respawn",))
        return st.events

    # ------------------------------------------------------------ for the HUD

    def offscreen(self, centre: tuple[float, float], half: tuple[float, float]) -> list:
        """Enemies off screen but within `arrow_range`, nearest first: (enemy, distance)."""
        cx, cy = centre
        ship = self.stage.ship
        out = []
        for e in self.stage.enemies:
            if not e.alive or e.dying >= 0:
                continue
            if abs(e.x - cx) <= half[0] and abs(e.y - cy) <= half[1]:
                continue
            d = dist(ship.x, ship.y, e.x, e.y)
            if d <= SANDBOX["arrow_range"]:
                out.append((e, d))
        out.sort(key=lambda p: p[1])
        return out[: int(SANDBOX["arrows"])]


def autopilot(sb: Sandbox, clock: float) -> tuple[Controls, bool, tuple[float, float] | None]:
    """A simple pilot for scripted runs: face the nearest enemy, keep some distance, strafe, fire."""
    st = sb.stage
    ship = st.ship
    live = st.live_enemies
    if not live or st.ship_down:
        return Controls(forward=clock % 6 < 1.5, aim=wrap_angle(clock * 20)), False, None
    e = min(live, key=lambda e: dist(ship.x, ship.y, e.x, e.y))
    d = dist(ship.x, ship.y, e.x, e.y)
    speed = WEAPONS["auto"]["speed"]
    t = d / speed
    aim = angle_to(e.x + (e.vx + e.mx) * t - ship.x, e.y + (e.vy + e.my) * t - ship.y)
    strafe = int(clock / 2.2) % 2 == 0
    crowd = sum(1 for o in live if dist(ship.x, ship.y, o.x, o.y) < 260)
    want = "missile" if crowd >= 5 and st.missile_ready else "auto"
    if int(clock / 9) % 3 == 2:
        want = "sniper"
    sb.arsenal.select(want)
    controls = Controls(forward=d > 260, back=d < 110, left=strafe, right=not strafe, aim=aim)
    facing = abs(wrap_angle(aim - ship.angle)) < 12
    return controls, facing and d < 320, (e.x, e.y)
