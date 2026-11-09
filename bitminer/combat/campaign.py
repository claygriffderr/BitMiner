"""Secure the Base, without graphics: the big map with home base and the mothership far away,
your drills, the space station's shop, the mothership's waves, and enemies that have to find you.
The screen in `views/campaign.py` draws it; tests run it headless.

You start with one drill, the auto cannon, starting armor and no shield. Drills dig ore out of
asteroids; you fly past to load it and sell it at home base, then spend the credits at the
station (home base) on more drills, weapons, missiles, health, 3-level upgrades (`gear.py`),
explosive mines and sentries (`defenses.py`). Every kill pays credits too.

Sprint 8 version: the mothership launches waves but doesn't fight back yet and can't be destroyed,
home base can't be destroyed either, and there are no lives (you start again at home base).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .. import sector
from ..field import wrap_delta
from ..flight import Controls, Ship, angle_to, wrap_angle
from ..graphics.images import rim_distance
from ..settings import Tuning
from ..world import MAX_FRAME, PHYSICS_STEP
from .ai import Battle
from .arsenal import Arsenal, hold_still
from .hunt import Fleet, Hunt
from .shop import Shop
from .defenses import Defenses
from .gear import Gear
from .specs import DRILLS, ENEMIES, SANDBOX, SHOP, WEAPONS
from .stage import Anim, Stage, Structure, dist

PLAYER_WEAPONS = ("auto", "sniper", "missile", "laser", "ram")     # hits that give away where you are
KILL_CREDITS = SHOP.get("kill_credits", {})     # what each enemy pays when you destroy it
DRILL_LIFT = 5.0        # a drill's centre sits this far out from the edge of its asteroid's picture (its legs on the rock)


class SectorWorld:
    """The map: its size, its asteroid field, your ship, and where everything big sits."""

    def __init__(self, scale: float | None = None, seed: int | None = None):
        self.layout = sector.layout(scale=scale)
        self.width = self.layout.width
        self.height = self.layout.height
        self.field = sector.build_field(self.layout, seed=seed)
        self.spawn = self.layout.spawn
        self.ship = Ship(*self.spawn)


@dataclass
class RockOre:
    """The ore left in an asteroid you have drilled. Every drill on it digs from the same ore."""
    left: float
    total: float
    ore: bool = True             # it glinted before it was worked out (for its crumbling picture)

    @property
    def drained(self) -> float:
        return 1.0 - self.left / self.total if self.total > 0 else 1.0


def crack_stage(drained: float) -> int:
    """0 to 3: how cracked an asteroid looks once `drained` (0 to 1) of its ore is gone."""
    return sum(1 for c in DRILLS["crack_at"] if drained >= float(c) - 1e-9)


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
        # Home base (the space station), near where you start, and the mothership far across the map.
        self.base = Structure("base", *lay.base, radius=float(DRILLS["base_radius"]), health=1.0,
                              max_health=1.0, uid=st.uid(), immune=True)
        st.structures.append(self.base)
        ms = st.spawn("mothership", *self._near_ship(lay.mothership), heading=180.0, warp=False)
        ms.immune = True              # it can't fight back yet, so it can't be beaten yet either
        self.mothership = ms
        self.battle.hunt = Hunt(self.battle, lay.base, ms)
        self.fleet = Fleet(self.battle, ms)
        # What you start with.
        start = SHOP["start"]
        self.arsenal = Arsenal(st, owned=list(start["weapons"]))
        st.set_missiles(int(start.get("missiles", 0)))
        if "missile" not in self.arsenal.owned and start.get("missiles", 0):
            self.arsenal.own("missile")
        self.gear = Gear(st)          # no shield, starting armor: upgrades come from the station
        self.defenses = Defenses(self)
        self.credits = int(start.get("credits", 0))
        self.drills_carried = int(start.get("drills", 1))
        self.drills: list[Structure] = []
        self.rocks: dict[int, RockOre] = {}
        self.shop = Shop(self)
        self.station_open = False
        self.pending: list[tuple] = []     # events from between steps (keys, the shop), for the next step
        self.respawn_in = 0.0
        self._down = False
        self.time = 0.0
        self.kills = 0
        self.downs = 0
        self.cargo = 0.0
        self.impacts = []

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

    # ------------------------------------------------------------ drills

    def drillable(self) -> tuple[int, float] | None:
        """The asteroid next to you that could take a drill on the side facing you, and that side
        (a heading out from its centre), or None. Doesn't care whether you have a drill to set."""
        st = self.stage
        f = st.field
        ship = st.ship
        if st.ship_down:
            return None
        reach = float(DRILLS["reach"])
        idx, dx, dy = f.near(ship.x, ship.y, reach + 50, reach + 50)
        best, bd = None, math.inf
        for i, ddx, ddy in zip(idx.tolist(), dx, dy):
            if f.gone[i] or f.size[i] < DRILLS["min_size"]:
                continue
            pool = self.rocks.get(i)
            if pool is not None:
                if pool.left <= 1e-6:
                    continue
            elif DRILLS["ore_only"] and not f.ore[i]:
                continue
            gap = math.hypot(ddx, ddy) - f.r[i]
            if gap > reach or gap >= bd:
                continue
            side = angle_to(-ddx, -ddy)
            if self._crowded(i, side):
                continue
            best, bd = (i, side), gap
        return best

    def _crowded(self, rock: int, side: float) -> bool:
        """Another drill already sits within `spacing` of this spot round the asteroid's edge."""
        r = float(self.stage.field.r[rock])
        need = float(DRILLS["spacing"])
        for d in self.drills:
            if d.rock == rock and abs(math.radians(wrap_angle(d.side - side))) * r < need:
                return True
        return False

    def drill_spot(self) -> int | None:
        """The asteroid a drill would go on if you pressed F now (you need one to set), or None."""
        if self.drills_carried <= 0:
            return None
        spot = self.drillable()
        return None if spot is None else spot[0]

    def place_drill(self) -> Structure | None:
        """Set one of your drills on the nearest asteroid that will take one, on the side facing you."""
        if self.drills_carried <= 0:
            return None
        spot = self.drillable()
        if spot is None:
            return None
        i, side = spot
        st = self.stage
        f = st.field
        pool = self.rocks.get(i)
        if pool is None:
            total = float(DRILLS["ore_per_area"]) * float(f.size[i]) ** 2
            pool = self.rocks[i] = RockOre(total, total, bool(f.ore[i]))
        d = Structure("drill", 0.0, 0.0, radius=float(DRILLS["radius"]), health=float(DRILLS["health"]),
                      max_health=float(DRILLS["health"]), uid=st.uid(), rock=i, hold_max=float(DRILLS["hold"]))
        d.side = side
        d.lift = rim_distance(int(f.size[i]), int(f.variant[i]), bool(f.ore[i]), side) + DRILL_LIFT
        self._stick(d)
        st.structures.append(d)
        self.drills.append(d)
        f.sites.setdefault(i, []).append(side)
        self.drills_carried -= 1
        st.events.append(("drill_set", d.uid, int(f.size[i])))
        return d

    def _stick(self, d: Structure) -> None:
        """Keep a drill on its asteroid's surface as the asteroid drifts."""
        f = self.stage.field
        cx, cy = self._near_ship((float(f.x[d.rock]), float(f.y[d.rock])))
        r = d.lift or float(f.r[d.rock]) + DRILL_LIFT
        a = math.radians(d.side)
        d.x, d.y = cx + math.sin(a) * r, cy + math.cos(a) * r

    def _step_drills(self, dt: float) -> None:
        st = self.stage
        f = st.field
        ship = st.ship
        rate = float(DRILLS["dig_rate"])
        cargo_max = float(DRILLS["cargo"])
        for d in list(self.drills):
            if not d.alive:
                self.drills.remove(d)       # destroyed by the enemy
                continue
            self._stick(d)
            pool = self.rocks[d.rock]
            dig = min(rate * dt, pool.left, d.hold_max - d.hold)
            d.working = dig > 0
            if dig > 0:
                pool.left -= dig
                d.hold += dig
            # Fly past to load what it has dug.
            if not st.ship_down and d.hold > 0 and dist(ship.x, ship.y, d.x, d.y) <= DRILLS["pickup"]:
                take = min(d.hold, cargo_max - self.cargo)
                if take > 0:
                    d.hold -= take
                    self.cargo += take
                    st.events.append(("load", d.uid, take))
        # Asteroids crack as they empty, and crumble once they're empty and you've unloaded their drills.
        for i, pool in list(self.rocks.items()):
            stage = crack_stage(pool.drained)
            if stage != int(f.wear[i]):
                f.wear[i] = stage
                st.events.append(("crack", i, stage))
            if pool.left <= 1e-6:
                on = [d for d in self.drills if d.rock == i]
                if all(d.hold <= 1e-6 for d in on):
                    self._crumble(i, on)
        st.structures = [t for t in st.structures if t.alive]
        # Sell what you carry at home base.
        if not st.ship_down and self.cargo > 0 and dist(ship.x, ship.y, self.base.x, self.base.y) <= DRILLS["unload"]:
            credits = int(round(self.cargo * float(DRILLS["credit_per_ore"])))
            st.events.append(("unload", self.cargo, credits))
            self.credits += credits
            self.cargo = 0.0

    def _crumble(self, i: int, drills: list[Structure]) -> None:
        """A worked-out asteroid breaks up and takes its drills with it."""
        st = self.stage
        f = st.field
        x, y = self._near_ship((float(f.x[i]), float(f.y[i])))
        pool = self.rocks.pop(i)
        sites = tuple(f.sites.get(i, ()))
        st.anims.append(Anim("crumble", (int(f.size[i]), int(f.variant[i]), pool.ore, int(f.wear[i]), sites, i),
                             int(DRILLS["crumble_frames"]), float(DRILLS["crumble_fps"]), x, y))
        n = int(f.size[i]) // 4
        st.smoke.burst("dust", x, y, 0.0, math.pi, n, (6, 26), (0.6, 1.4))
        for d in drills:
            d.alive = False
            self.drills.remove(d)
            st.events.append(("drill_used", d.uid))
        f.remove(i)
        st.events.append(("crumble", i, int(f.size[i])))

    # ------------------------------------------------------------ the station

    def near_station(self) -> bool:
        st = self.stage
        ship = st.ship
        return not st.ship_down and dist(ship.x, ship.y, self.base.x, self.base.y) <= SHOP["station"]["reach"]

    def open_station(self) -> bool:
        """Press E at the station: its screen opens (the game keeps running)."""
        if self.station_open or not self.near_station():
            return False
        self.station_open = True
        self.note(("station", "open"))
        return True

    def close_station(self) -> None:
        if self.station_open:
            self.station_open = False
            self.note(("station", "close"))

    def note(self, event: tuple) -> None:
        """Something that happened between steps (a key press, a purchase): it goes out with the
        next step's events."""
        self.pending.append(event)

    def test_credits(self) -> int:
        """A testing shortcut (the = key): add `test_credits` credits so every item can be tried
        without the grind. The play log marks it."""
        amount = int(SHOP.get("test_credits", 0))
        if amount:
            self.credits += amount
            self.note(("test_credits", amount))
        return amount

    def enemy_near(self) -> bool:
        """An enemy close enough that shopping now is a risk."""
        ship = self.stage.ship
        reach = float(SHOP["station"]["warn_range"])
        return any(e.alive and e.dying < 0 and e.kind != "mothership" and dist(ship.x, ship.y, e.x, e.y) <= reach
                   for e in self.stage.enemies)

    # ------------------------------------------------------------ the update

    def step(self, dt: float, controls: Controls, trigger: bool, cursor: tuple[float, float] | None = None,
             set_drill: bool = False, boost: bool = False, lay_mines: bool = False,
             place_sentry: bool = False) -> list:
        """Advance by dt seconds. Returns what happened on the stage this step (its events).
        `boost` and `lay_mines` are held keys (Shift, G); `set_drill` and `place_sentry` presses (F, R)."""
        dt = min(max(dt, 0.0), MAX_FRAME)
        st = self.stage
        st.events = []
        if dt == 0:
            return st.events
        st.events, self.pending = self.pending, []
        self.time += dt
        world = self.world
        field = world.field
        n = max(1, math.ceil(dt / PHYSICS_STEP - 1e-9))
        h = dt / n
        self.impacts = []
        if self.station_open:
            # Docked: the ship comes to rest by the station and the station screen has the keys.
            keep = math.exp(-float(SHOP["station"]["brake"]) * dt)
            st.ship.vx *= keep
            st.ship.vy *= keep
            controls = Controls()
            trigger = False
            set_drill = place_sentry = lay_mines = boost = False
        controls = hold_still(self.arsenal, controls, dt)
        moving = controls.forward or controls.back or controls.left or controls.right
        self.gear.step_boost(dt, boost and moving and not st.ship_down)
        tuning = self.gear.flight(self.tuning)
        st.ship_mass = max(0.05, tuning.mass)
        st.bounce = tuning.bounce
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
        if set_drill:
            self.place_drill()
        if place_sentry:
            self.defenses.place_sentry()
        self.fleet.step(dt)
        self.battle.step(dt)
        self.arsenal.step(dt, trigger and not st.ship_down, cursor)
        st.step(dt)
        self.defenses.step(dt, lay_mines)
        self._step_drills(dt)

        if any(ev[0] == "hit" and ev[1] in PLAYER_WEAPONS for ev in st.events):
            self.hunt.reveal()          # you hit one: now they all know where you are
        for ev in [ev for ev in st.events if ev[0] == "kill"]:
            self.kills += 1
            pay = int(KILL_CREDITS.get(ev[1], 0))
            if pay:
                self.credits += pay     # paid the moment it goes down
                st.events.append(("bounty", ev[1], pay, ev[4], ev[5]))
        if st.ship_down and not self._down:
            self.downs += 1
            self.respawn_in = float(SANDBOX["respawn"])
            self.cargo = 0.0            # what you were carrying is lost with the ship
            self.close_station()
        self._down = st.ship_down
        if self.station_open and not self.near_station():
            self.close_station()
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
        return {"cargo": round(self.cargo, 1), "credits": self.credits, "drills": len(self.drills),
                "drills_carried": self.drills_carried, "weapons": list(self.arsenal.owned),
                "missiles": self.stage.missiles_total, "known": self.hunt.known, "out": self.enemies_out(),
                "upgrades": dict(self.gear.levels), "mines": self.defenses.mines_carried,
                "mines_out": len(self.stage.mines), "sentries": [(s.gun, s.tier) for s in self.defenses.sentries],
                "boost": round(self.gear.boost, 2)}

    def marks(self, centre: tuple[float, float], half: tuple[float, float]) -> list:
        """Home base and each of your drills that are off screen: (dx, dy, kind, structure) from
        the view centre, for the dim arrows at the screen edge."""
        cx, cy = centre
        out = []
        for t in [self.base] + self.drills:
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


# ---------------------------------------------------------------- a pilot for scripted runs

class Autopilot:
    """A simple pilot for scripted runs: look round the station shop first, set drills on ore rocks
    near base, fly between them and home, buy another drill (and the sniper) when it can afford
    them, and fight whatever comes close."""

    BROWSE = 3.0          # seconds it spends looking round the station at the start
    SHOP_TIME = 0.6       # seconds it stays when it comes back to buy something

    def __init__(self) -> None:
        self.first = True
        self.opened = 0.0
        self.keys = {"boost": False, "mines": False, "sentry": False}    # held keys and presses this step

    def __call__(self, game: Campaign, clock: float) -> tuple[Controls, bool, tuple[float, float] | None, bool]:
        st = game.stage
        ship = st.ship
        keys = self.keys
        keys["boost"] = keys["mines"] = keys["sentry"] = False
        if st.ship_down:
            return Controls(), False, None, False
        live = [e for e in st.live_enemies if e.kind != "mothership"]
        near = [e for e in live if dist(ship.x, ship.y, e.x, e.y) < 360]
        defenses = game.defenses
        if defenses.carried and not game.station_open and dist(ship.x, ship.y, game.base.x, game.base.y) < 160:
            keys["sentry"] = not defenses.sentry_room(ship.x, ship.y)      # guard home base
        if near and not game.station_open:
            keys["mines"] = defenses.mines_carried > 0 and min(dist(ship.x, ship.y, e.x, e.y) for e in near) < 220
            e = min(near, key=lambda e: dist(ship.x, ship.y, e.x, e.y))
            d = dist(ship.x, ship.y, e.x, e.y)
            weapon = "sniper" if "sniper" in game.arsenal.owned and d > 200 else "auto"
            t = d / WEAPONS[weapon]["speed"]
            aim = angle_to(e.x + (e.vx + e.mx) * t - ship.x, e.y + (e.vy + e.my) * t - ship.y)
            game.arsenal.select(weapon)
            strafe = int(clock / 2.2) % 2 == 0
            controls = Controls(forward=d > 240, back=d < 110, left=strafe, right=not strafe, aim=aim)
            facing = abs(wrap_angle(aim - ship.angle)) < 12
            return controls, facing and d < 320, (e.x, e.y), False
        # The station: look round at the start, and come back to buy what it can afford.
        price = Shop.item("drill")["price"]
        wants = []
        if game.drills_carried == 0 and game.shop.can_buy("drill"):
            wants.append("drill")
        if game.shop.can_buy("sniper") and game.credits >= price + Shop.item("sniper")["price"]:
            wants.append("sniper")
        if "sniper" in game.arsenal.owned:
            for key in ("shield", "mine", "sentry_auto", "boost"):
                o = game.shop.offer(key)
                if not o.blocked and o.price is not None and game.credits >= o.price + price:
                    wants.append(key)
                    break
        if game.station_open:
            for key in wants:
                game.shop.buy(key)
            if clock - self.opened >= (self.BROWSE if self.first else self.SHOP_TIME):
                game.close_station()
                self.first = False
            return Controls(), False, None, False
        if self.first or wants:
            if game.open_station():
                self.opened = clock
                return Controls(), False, None, False
            return _fly_to(ship, (game.base.x, game.base.y), 20), False, None, False
        # Set the drills it carries, else ferry ore home.
        want = None
        if game.drills_carried > 0:
            if game.drill_spot() is not None:
                return Controls(aim=ship.angle), False, None, True
            f = st.field
            idx, dx, dy = f.near(ship.x, ship.y, 900, 900)
            cands = [(-int(f.size[i]), math.hypot(a, b), a, b) for i, a, b in zip(idx.tolist(), dx, dy)
                     if f.ore[i] and not f.gone[i] and f.size[i] >= DRILLS["min_size"]
                     and i not in game.rocks]
            if cands:
                _, _, a, b = min(cands)             # the biggest it can see, so a drill pays for itself
                want = (ship.x + a, ship.y + b)
        if want is None:
            loaded = [d for d in game.drills if d.hold >= 10 or (d.hold > 0 and not d.working)]
            if game.cargo >= DRILLS["cargo"] * 0.5 or not loaded:
                want = (game.base.x, game.base.y)
            else:
                d = min(loaded, key=lambda d: dist(ship.x, ship.y, d.x, d.y))
                a = math.radians(d.side)            # come at it from open space, not through its rock
                want = (d.x + math.sin(a) * 24, d.y + math.cos(a) * 24)
        keys["boost"] = dist(ship.x, ship.y, *want) > 500
        return _fly_to(ship, want, 8), False, None, False


def _fly_to(ship: Ship, want: tuple[float, float], close: float) -> Controls:
    d = dist(ship.x, ship.y, *want)
    aim = angle_to(want[0] - ship.x, want[1] - ship.y)
    facing = abs(wrap_angle(aim - ship.angle)) < 20
    fast = math.hypot(ship.vx, ship.vy)
    # Slow down as it gets close, so it comes to rest on the spot instead of short of it.
    return Controls(forward=facing and d > close and fast < min(200.0, 20 + d), back=fast > 30 + d, aim=aim)


def autopilot(game: Campaign, clock: float) -> tuple[Controls, bool, tuple[float, float] | None, bool]:
    """One autopilot per game (it remembers whether it has looked round the shop)."""
    pilot = getattr(game, "_autopilot", None)
    if pilot is None:
        pilot = game._autopilot = Autopilot()
    return pilot(game, clock)


__all__ = ["Campaign", "SectorWorld", "RockOre", "autopilot", "crack_stage", "ENEMIES"]
