"""Secure the Base, without graphics: the big map with home base and the mothership far away,
your mines, the mothership's waves, and enemies that have to find you. The screen in
`views/campaign.py` draws it; tests run it headless.

Sprint 5 version: the mothership launches waves but doesn't fight back yet and can't be destroyed,
home base can't be destroyed either, and there are no lives (you start again at home base).
"""

from __future__ import annotations

import math

from .. import sector
from ..field import wrap_delta
from ..flight import Controls, Ship, angle_to, wrap_angle
from ..settings import Tuning
from ..world import MAX_FRAME, PHYSICS_STEP
from .ai import Battle
from .arsenal import Arsenal
from .hunt import Fleet, Hunt
from .specs import ENEMIES, MINES, SANDBOX, WEAPONS
from .stage import Stage, Structure, dist

PLAYER_WEAPONS = ("auto", "sniper", "missile", "laser", "ram")
MINE_LIFT = 5.0         # a mine's centre sits this far off its asteroid's surface (its rig stands on the rock)


class SectorWorld:
    """The map: its size, its asteroid field, your ship, and where everything big sits."""

    def __init__(self, scale: float | None = None, seed: int | None = None):
        self.layout = sector.layout(scale=scale)
        self.width = self.layout.width
        self.height = self.layout.height
        self.field = sector.build_field(self.layout, seed=seed)
        self.spawn = self.layout.spawn
        self.ship = Ship(*self.spawn)


class Campaign:
    def __init__(self, sparks, smoke, tuning: Tuning, scale: float | None = None, seed: int | None = None):
        self.tuning = tuning
        self.world = SectorWorld(scale, seed)
        lay = self.world.layout
        st = self.stage = Stage(sparks, smoke, seed=self.world.field.seed)
        st.ship = self.world.ship
        st.field = self.world.field
        st.world = (self.world.width, self.world.height)
        st.collide_bodies = True
        st.regen = True
        st.can_die = True
        self.battle = Battle(st, seed=self.world.field.seed)
        # Home base, near where you start, and the mothership far across the map.
        self.base = Structure("base", *lay.base, radius=float(MINES["base_radius"]), health=1.0,
                              max_health=1.0, uid=st.uid(), immune=True)
        st.structures.append(self.base)
        ms = st.spawn("mothership", *self._near_ship(lay.mothership), heading=180.0, warp=False)
        ms.immune = True              # it can't fight back yet, so it can't be beaten yet either
        self.mothership = ms
        self.battle.hunt = Hunt(self.battle, lay.base, ms)
        self.fleet = Fleet(self.battle, ms)
        self.arsenal = Arsenal(st)
        self.respawn_in = 0.0
        self._down = False
        self.time = 0.0
        self.kills = 0
        self.downs = 0
        self.cargo = 0.0
        self.credits = 0
        self.impacts = []
        self.mines: list[Structure] = []

    @property
    def ship(self) -> Ship:
        return self.stage.ship

    @property
    def hunt(self) -> Hunt:
        return self.battle.hunt

    @property
    def waves(self) -> Fleet:
        """The wave launcher, under the name the sandbox uses (for the play log and N key)."""
        return self.fleet

    def _near_ship(self, p: tuple[float, float]) -> tuple[float, float]:
        ship = self.stage.ship
        W, H = self.stage.world
        return ship.x + wrap_delta(p[0] - ship.x, W), ship.y + wrap_delta(p[1] - ship.y, H)

    # ------------------------------------------------------------ mines

    def mine_spot(self) -> int | None:
        """The asteroid a mine would go on if you pressed F now, or None."""
        st = self.stage
        f = st.field
        ship = st.ship
        if st.ship_down or len(self.mines) >= int(MINES["max"]):
            return None
        reach = float(MINES["reach"])
        idx, dx, dy = f.near(ship.x, ship.y, reach + 50, reach + 50)
        taken = {m.rock for m in self.mines}
        best, bd = None, math.inf
        for i, ddx, ddy in zip(idx.tolist(), dx, dy):
            if i in taken or f.size[i] < MINES["min_size"] or (MINES["ore_only"] and not f.ore[i]):
                continue
            gap = math.hypot(ddx, ddy) - f.r[i]
            if gap <= reach and gap < bd:
                best, bd = i, gap
        return best

    def place_mine(self) -> Structure | None:
        """Set a mine on the nearest asteroid that will take one, on the side facing you."""
        i = self.mine_spot()
        if i is None:
            return None
        st = self.stage
        f = st.field
        ship = st.ship
        rx, ry = self._near_ship((float(f.x[i]), float(f.y[i])))
        ore = float(MINES["ore_per_area"]) * float(f.size[i]) ** 2
        m = Structure("mine", rx, ry, radius=float(MINES["radius"]), health=float(MINES["health"]),
                      max_health=float(MINES["health"]), uid=st.uid(), rock=i, ore_left=ore, ore_max=ore,
                      hold_max=float(MINES["hold"]))
        m.side = angle_to(ship.x - rx, ship.y - ry)       # where on the rock it sits
        self._stick(m)
        st.structures.append(m)
        self.mines.append(m)
        st.events.append(("mine_set", m.uid, int(f.size[i])))
        return m

    def _stick(self, m: Structure) -> None:
        """Keep a mine on its asteroid's surface as the asteroid drifts."""
        f = self.stage.field
        cx, cy = self._near_ship((float(f.x[m.rock]), float(f.y[m.rock])))
        r = float(f.r[m.rock])
        a = math.radians(m.side)
        m.x, m.y = cx + math.sin(a) * (r + MINE_LIFT), cy + math.cos(a) * (r + MINE_LIFT)

    def _step_mines(self, dt: float) -> None:
        st = self.stage
        ship = st.ship
        rate = float(MINES["dig_rate"])
        cargo_max = float(MINES["cargo"])
        for m in list(self.mines):
            if not m.alive:
                self.mines.remove(m)
                continue
            self._stick(m)
            dig = min(rate * dt, m.ore_left, m.hold_max - m.hold)
            if dig > 0:
                m.ore_left -= dig
                m.hold += dig
            # Fly past to load what it has dug.
            if not st.ship_down and m.hold > 0 and dist(ship.x, ship.y, m.x, m.y) <= MINES["pickup"]:
                take = min(m.hold, cargo_max - self.cargo)
                if take > 0:
                    m.hold -= take
                    self.cargo += take
                    st.events.append(("load", m.uid, take))
            if m.ore_left <= 1e-6 and m.hold <= 1e-6:
                # The asteroid is worked out: the mine packs up.
                m.alive = False
                st.field.ore[m.rock] = False
                self.mines.remove(m)
                st.events.append(("mine_dry", m.uid))
        st.structures = [t for t in st.structures if t.alive]
        # Sell what you carry at home base.
        if not st.ship_down and self.cargo > 0 and dist(ship.x, ship.y, self.base.x, self.base.y) <= MINES["unload"]:
            credits = int(round(self.cargo * float(MINES["credit_per_ore"])))
            st.events.append(("unload", self.cargo, credits))
            self.credits += credits
            self.cargo = 0.0

    # ------------------------------------------------------------ the update

    def step(self, dt: float, controls: Controls, trigger: bool, cursor: tuple[float, float] | None = None,
             set_mine: bool = False) -> list:
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
        for _ in range(n):
            if not st.ship_down:
                st.ship.step(controls, tuning, h, world.width, world.height)
                self.impacts += field.collide_ship(st.ship, st.ship_mass, tuning.bounce)
            field.step(h)
        for hit in self.impacts:
            dv = hit.impulse / st.ship_mass
            if dv >= 12:
                st.bump_rock(hit.impulse, hit.x, hit.y)
                st.smoke.burst("dust", hit.x + hit.nx * 2, hit.y + hit.ny * 2, math.atan2(-hit.ny, -hit.nx),
                               1.0, int(min(14, max(2, dv / 18))), (8, 30 + dv * 0.2), (0.4, 1.0))

        st.recentre()
        if set_mine:
            self.place_mine()
        self.fleet.step(dt)
        self.battle.step(dt)
        self.arsenal.step(dt, trigger and not st.ship_down, cursor)
        st.step(dt)
        self._step_mines(dt)

        if any(ev[0] == "hit" and ev[1] in PLAYER_WEAPONS for ev in st.events):
            self.hunt.reveal()          # you hit one: now they all know where you are
        self.kills += sum(1 for ev in st.events if ev[0] == "kill")
        if st.ship_down and not self._down:
            self.downs += 1
            self.respawn_in = float(SANDBOX["respawn"])
            self.cargo = 0.0            # what you were carrying is lost with the ship
        self._down = st.ship_down
        if st.ship_down:
            self.respawn_in -= dt
            if self.respawn_in <= 0:
                # Back at home base.
                bx, by = self.base.x, self.base.y
                spawn = (bx + (self.world.spawn[0] - world.layout.base[0]),
                         by + (self.world.spawn[1] - world.layout.base[1]))
                st.respawn(*spawn, float(SANDBOX["invulnerable"]))
                self.arsenal.cooldown = 0.0
                self._down = False
                st.recentre()
                st.events.append(("respawn",))
        return st.events

    # ------------------------------------------------------------ for the HUD and the play log

    def log_extra(self) -> dict:
        """Campaign numbers each play log sample adds."""
        return {"cargo": round(self.cargo, 1), "credits": self.credits, "mines": len(self.mines),
                "known": self.hunt.known, "out": self.enemies_out()}

    def marks(self, centre: tuple[float, float], half: tuple[float, float]) -> list:
        """Home base and each of your mines that are off screen: (dx, dy, kind, structure) from
        the view centre, for the dim arrows at the screen edge."""
        cx, cy = centre
        out = []
        for t in [self.base] + self.mines:
            if not t.alive:
                continue
            dx, dy = t.x - cx, t.y - cy
            if abs(dx) <= half[0] and abs(dy) <= half[1]:
                continue
            out.append((dx, dy, t.kind, t))
        return out

    def enemies_out(self) -> int:
        return sum(1 for e in self.stage.enemies if e.alive and e.dying < 0 and e.kind != "mothership")

    def offscreen(self, centre: tuple[float, float], half: tuple[float, float]) -> list:
        """Enemies off screen but within `arrow_range`, nearest first: (enemy, distance)."""
        cx, cy = centre
        ship = self.stage.ship
        out = []
        for e in self.stage.enemies:
            if not e.alive or e.dying >= 0 or e.kind == "mothership":
                continue
            if abs(e.x - cx) <= half[0] and abs(e.y - cy) <= half[1]:
                continue
            d = dist(ship.x, ship.y, e.x, e.y)
            if d <= SANDBOX["arrow_range"]:
                out.append((e, d))
        out.sort(key=lambda p: p[1])
        return out[: int(SANDBOX["arrows"])]


def autopilot(game: Campaign, clock: float) -> tuple[Controls, bool, tuple[float, float] | None, bool]:
    """A simple pilot for scripted runs: set mines on ore rocks near base, fly between them and
    home, and fight whatever comes close. Returns controls, trigger, cursor and whether to set a mine."""
    st = game.stage
    ship = st.ship
    if st.ship_down:
        return Controls(), False, None, False
    live = [e for e in st.live_enemies if e.kind != "mothership"]
    near = [e for e in live if dist(ship.x, ship.y, e.x, e.y) < 360]
    if near:
        e = min(near, key=lambda e: dist(ship.x, ship.y, e.x, e.y))
        d = dist(ship.x, ship.y, e.x, e.y)
        t = d / WEAPONS["auto"]["speed"]
        aim = angle_to(e.x + (e.vx + e.mx) * t - ship.x, e.y + (e.vy + e.my) * t - ship.y)
        game.arsenal.select("auto")
        strafe = int(clock / 2.2) % 2 == 0
        controls = Controls(forward=d > 240, back=d < 110, left=strafe, right=not strafe, aim=aim)
        facing = abs(wrap_angle(aim - ship.angle)) < 12
        return controls, facing and d < 320, (e.x, e.y), False
    # Set mines while there are slots, else ferry ore home.
    want = None
    if len(game.mines) < int(MINES["max"]):
        spot = game.mine_spot()
        if spot is not None:
            return Controls(aim=ship.angle), False, None, True
        f = st.field
        idx, dx, dy = f.near(ship.x, ship.y, 900, 900)
        taken = {m.rock for m in game.mines}
        cands = [(math.hypot(a, b), a, b) for i, a, b in zip(idx.tolist(), dx, dy)
                 if f.ore[i] and f.size[i] >= MINES["min_size"] and i not in taken]
        if cands:
            _, a, b = min(cands)
            want = (ship.x + a, ship.y + b)
    if want is None:
        loaded = [m for m in game.mines if m.hold >= 10 or (m.hold > 0 and m.ore_left <= 0)]
        if game.cargo >= MINES["cargo"] * 0.5 or not loaded:
            want = (game.base.x, game.base.y)
        else:
            m = min(loaded, key=lambda m: dist(ship.x, ship.y, m.x, m.y))
            a = math.radians(m.side)            # come at it from open space, not through its rock
            want = (m.x + math.sin(a) * 24, m.y + math.cos(a) * 24)
    d = dist(ship.x, ship.y, *want)
    aim = angle_to(want[0] - ship.x, want[1] - ship.y)
    facing = abs(wrap_angle(aim - ship.angle)) < 20
    fast = math.hypot(ship.vx, ship.vy)
    # Slow down as it gets close, so it comes to rest on the spot instead of short of it.
    return (Controls(forward=facing and d > 8 and fast < min(200.0, 20 + d), back=fast > 30 + d, aim=aim),
            False, None, False)


__all__ = ["Campaign", "SectorWorld", "autopilot", "ENEMIES"]
