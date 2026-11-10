"""The balance simulator's player: a bot that plays Secure the Base through the same controls you
have (thrust, aim, fire and the F, R, Q, T, G and Shift keys), so the time everything takes is real.

What it does, most urgent first:

1. Fights any enemy that comes within reach, with the sniper at range and the auto cannon up close.
2. Flies to anything of its own that is under attack.
3. Goes to the station when it can afford the next thing on its shopping list (`plan` in
   `data/sim.json`), or needs a repair.
4. Sets out what it carries: the collector ring near home base, sentries on the ring's mounts (or
   by home base), drills on the best ore asteroid in reach (ones in the ring first).
5. Picks up drills floating free.
6. Tows ore asteroids into the ring while it has room.
7. Loads ore from its drills and sells it at home base.

A preset (`presets` in the data file) sets how well it aims, how fast it flies and how much time it
wastes. It can't judge fun: it keeps the numbers honest so playtests can be about feel.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from ..combat.campaign import Campaign
from ..combat.haul import FIELD_R, INNER, NODE_DIRS, OUTER
from ..combat.specs import DRILLS, SHOP, WEAPONS
from ..combat.stage import dist
from ..flight import Controls, angle_to, wrap_angle


TOW_GATE = 330.0          # how far out from the ring a towed rock is lined up with its spot
RING_STAND = OUTER + 70.0  # where it stands to defend the ring: outside it, clear of its rocks


@dataclass
class Act:
    """What the bot does this step: the same inputs the game screen passes to `Campaign.step`."""
    controls: Controls = field(default_factory=Controls)
    trigger: bool = False
    cursor: tuple[float, float] | None = None
    set_drill: bool = False
    boost: bool = False
    lay_mines: bool = False
    place_sentry: bool = False
    lasso: bool = False
    ring_key: bool = False


def parse_item(text: str) -> tuple[str, int | None]:
    """`sentry_missile:3` -> ("sentry_missile", 3); `drill` -> ("drill", None)."""
    key, _, tier = text.partition(":")
    return key, int(tier) if tier else None


class Bot:
    def __init__(self, game: Campaign, preset: dict, plan: dict, habits: dict, seed: int = 0):
        self.game = game
        self.p = preset
        self.h = habits
        self.rng = random.Random(seed)
        # The shopping list: (phase, key, tier) in order.
        self.plan = [(phase, *parse_item(item)) for phase, items in plan.items() for item in items]
        self.at = 0                       # the next thing on the list
        self.skipped: list[str] = []      # things the shop doesn't sell (yet)
        self.done_at: dict[str, float] = {}       # phase -> game seconds when its last item was bought
        self.drills_bought = 0
        self.job: tuple = ("idle",)
        self.job_t = 0.0
        self.think = 0.0
        self.pause = 0.0
        self.shop_t = 0.0
        self.avoid: dict[int, float] = {}         # asteroid -> game time until it is left alone
        self.aim_off = 0.0
        self.aim_t = 0.0
        self.alarm: tuple[float, float, float] | None = None       # x, y, until
        self.ring_site: tuple[float, float] | None = None
        self.keying = -1.0
        self.watch_from = (game.ship.x, game.ship.y)
        self.watch_t = 0.0
        self.escape = 0.0
        self.escape_dir = (0.0, 0.0)
        self.dt = 1 / 30
        self.grab_dir: tuple[float, float] | None = None      # the side it comes at a rock from, once
        self.grab_try = 0                                     # the first side didn't let it lasso that rock
        self.grab_t = 0.0
        self.tow_slot = -1                # the ring spot the rock on the lasso is headed for
        self.lined = False                # past the gate, flying down that spot's diagonal
        self.time_in: dict[str, float] = {}
        self.trace: list[tuple[float, str]] | None = None

    # ------------------------------------------------------------ small helpers

    @property
    def st(self):
        return self.game.stage

    @property
    def ship(self):
        return self.game.stage.ship

    @property
    def thrust(self) -> float:
        """How hard the ship's main engine pushes it, in pixels a second each second."""
        t = self.game.gear.flight(self.game.tuning)
        return float(t.thrust_main) / max(0.05, float(t.mass))

    def rock_pos(self, i: int) -> tuple[float, float]:
        return self.game.haul.rock_pos(i)

    def base_dist(self, x: float, y: float) -> float:
        return dist(x, y, self.game.base.x, self.game.base.y)

    def ring(self):
        haul = self.game.haul
        return haul.ring if haul.has_ring() else None

    def in_ring(self, rock: int) -> bool:
        ring = self.ring()
        return ring is not None and rock in ring.slots

    def left_alone(self, rock: int) -> bool:
        return self.avoid.get(rock, 0.0) > self.game.time

    def ore_left(self, i: int) -> float:
        """Ore still in asteroid i (0 if it has none or can't take a drill)."""
        f = self.st.field
        if f.gone[i] or f.size[i] < DRILLS["min_size"]:
            return 0.0
        pool = self.game.rocks.get(i)
        if pool is not None:
            return max(0.0, pool.left)
        if DRILLS["ore_only"] and not f.ore[i]:
            return 0.0
        return float(DRILLS["ore_per_area"]) * float(f.size[i]) ** 2

    def drills_on(self, i: int) -> int:
        return sum(1 for d in self.game.drills if d.rock == i)

    def set_job(self, *job) -> None:
        if job != self.job:
            if self.trace is not None:
                self.trace.append((self.game.time, " ".join(str(v) if not isinstance(v, float) else f"{v:.0f}"
                                                            for v in job)))
            self.job = job
            self.job_t = 0.0
            self.keying = -1.0
            self.grab_dir, self.grab_try, self.grab_t = None, 0, 0.0

    def rest(self) -> None:
        """A job is done: waste a little time, as people do."""
        mean = float(self.p["pause"])
        if mean > 0:
            self.pause = self.rng.expovariate(1.0 / mean)
        self.set_job("idle")
        self.think = 0.0

    def give_up(self, rock: int | None = None) -> None:
        if rock is not None:
            self.avoid[rock] = self.game.time + float(self.h["avoid"])
        self.set_job("idle")
        self.think = 0.0

    # ------------------------------------------------------------ the step

    def act(self, dt: float, events=()) -> Act:
        """What to do this step. `events` are what happened on the last step."""
        g = self.game
        st = g.stage
        self.dt = dt
        for ev in events:
            if ev[0] == "struct_hit" and ev[1] in ("drill", "sentry", "ring"):
                for t in st.structures:
                    if t.uid == ev[2] and t.alive:
                        x, y = t.x, t.y
                        if ev[1] == "ring":
                            # Not into the ring (nothing can be shot from in there): to its near side.
                            ox, oy = st.ship.x - x, st.ship.y - y
                            n = math.hypot(ox, oy) or 1.0
                            x, y = x + ox / n * RING_STAND, y + oy / n * RING_STAND
                        self.alarm = (x, y, g.time + float(self.h["alarm"]))
        act = Act()
        if st.ship_down:
            self.set_job("idle")
            self.pause = 0.0
            self.shop_t = 0.0
            name = "down"
        elif g.station_open:
            name = "shop"
            self._shopping(dt)
        else:
            foe = self._threat()
            if foe is not None:
                name = "fight"
                self._fight(act, foe, dt)
            elif self.pause > 0:
                name = "pause"
                self.pause -= dt
                self._go(act, (self.ship.x, self.ship.y), 1e9)
            else:
                self.think -= dt
                if self.think <= 0:
                    self.think = 0.5
                    self._plan()
                name = self.job[0]
                self.job_t += dt
                getattr(self, "_do_" + name)(act)
        self.time_in[name] = self.time_in.get(name, 0.0) + dt
        return act

    # ------------------------------------------------------------ flying

    def _go(self, act: Act, want: tuple[float, float], close: float = 10.0, cap: float | None = None,
            pad: float | None = None, ignore=(), slope: float | None = None, through: bool = False) -> float:
        """Fly to `want` and stop within `close` of it, round any asteroid in the way (`through`:
        don't slow down for it, just fly past). It brakes as late as its engine allows, or with
        `slope` on a gentler line (speed per pixel still to go) for towing. Sets the controls on
        `act` and returns how far there is to go."""
        g = self.game
        st = g.stage
        ship = st.ship
        wx, wy = g._near_ship(want)
        dx, dy = wx - ship.x, wy - ship.y
        d = math.hypot(dx, dy)
        cap = float(self.p["cruise"]) if cap is None else cap
        # Stuck against something? Break away sideways for a moment.
        self.watch_t += self.dt
        if self.watch_t >= 2.5:
            moved = dist(ship.x, ship.y, *self.watch_from)
            if d > close + 5 and moved < 12 and self.escape <= 0:
                a = self.rng.uniform(0, math.tau)
                self.escape = 1.0
                self.escape_dir = (math.cos(a), math.sin(a))
            self.watch_from = (ship.x, ship.y)
            self.watch_t = 0.0
        if self.escape > 0:
            self.escape -= self.dt
            vx, vy = self.escape_dir[0] * 140, self.escape_dir[1] * 140
        elif d <= close and not through:
            vx = vy = 0.0
        else:
            ux, uy = (dx / d, dy / d) if d > 1e-6 else (0.0, 1.0)
            ux, uy = self._around(ux, uy, d, float(ship.radius) + 6.0 if pad is None else pad, ignore)
            if through:
                v = cap
            elif slope is not None:
                v = min(cap, 20.0 + slope * (d - close))
            else:
                # Leave room to turn round and burn the speed off.
                room = max(0.0, d - close - ship.speed * 0.25)
                v = min(cap, 25.0 + math.sqrt(2.0 * 0.75 * self.thrust * room))
            vx, vy = ux * v, uy * v
        ex, ey = vx - ship.vx, vy - ship.vy
        if math.hypot(ex, ey) > 10.0:
            aim = angle_to(ex, ey)
            facing = abs(wrap_angle(aim - ship.angle)) < 20
            act.controls = Controls(forward=facing, aim=aim)
            act.boost = facing and d > 500 and ex * dx + ey * dy > 0
        else:
            act.controls = Controls(aim=angle_to(dx, dy) if d > 1.0 else ship.angle)
        return d

    def _around(self, ux: float, uy: float, d: float, pad: float, ignore) -> tuple[float, float]:
        """Swing round an asteroid in the way, on the side the path already leans to."""
        st = self.st
        ship = st.ship
        f = st.field
        look = min(d, 50.0 + ship.speed * 0.5)
        hit = st.rock_hit(ship.x, ship.y, ship.x + ux * look, ship.y + uy * look, pad)
        if hit is None or hit[2] in ignore:
            return ux, uy
        i = hit[2]
        rx, ry = self.rock_pos(i)
        cx, cy = rx - ship.x, ry - ship.y
        cd = math.hypot(cx, cy) or 1.0
        if ux * cy - uy * cx > 0:
            tx, ty = cy / cd, -cx / cd
        else:
            tx, ty = -cy / cd, cx / cd
        out = 0.5 if cd - float(f.r[i]) - pad < 6.0 else 0.0     # too close: lean away from it as well
        sx, sy = tx - cx / cd * out + ux * 0.15, ty - cy / cd * out + uy * 0.15
        n = math.hypot(sx, sy) or 1.0
        return sx / n, sy / n

    # ------------------------------------------------------------ fighting

    def _threat(self):
        st = self.st
        ship = st.ship
        reach = float(self.p["engage"])
        best, bd = None, reach
        for e in st.enemies:
            if not e.targetable or e.kind == "mothership":
                continue
            d = dist(ship.x, ship.y, e.x, e.y)
            if d < bd:
                best, bd = e, d
        return best

    def _fight(self, act: Act, foe, dt: float) -> None:
        g = self.game
        ship = self.ship
        if g.haul.rock >= 0:
            act.lasso = True              # drop what it's towing: you can't dodge with a rock in tow
        if self.job[0] in ("tow", "ring", "clear"):
            self.set_job("idle")
        d = dist(ship.x, ship.y, foe.x, foe.y)
        weapon = "sniper" if "sniper" in g.arsenal.owned and d > float(self.p["sniper_from"]) else "auto"
        g.arsenal.select(weapon)
        t = d / float(WEAPONS[weapon]["speed"])
        self.aim_t -= dt
        if self.aim_t <= 0:
            self.aim_t = 0.35
            self.aim_off = self.rng.gauss(0.0, float(self.p["aim_error"]))
        aim = angle_to(foe.x + (foe.vx + foe.mx) * t - ship.x, foe.y + (foe.vy + foe.my) * t - ship.y) + self.aim_off
        near, far = self.p["keep"]
        strafe = int(g.time / 2.2) % 2 == 0
        act.controls = Controls(forward=d > far, back=d < near, left=strafe, right=not strafe, aim=aim)
        ring = self.ring()
        if ring is not None:
            ox, oy = ship.x - ring.x, ship.y - ring.y
            if math.hypot(ox, oy) < RING_STAND - 30.0:
                # Inside the ring its rocks block every shot: get out through the nearest gap first.
                gx, gy = max(((1, 0), (-1, 0), (0, 1), (0, -1)), key=lambda v: v[0] * ox + v[1] * oy)
                act.controls = self._push(aim, gx, gy)
        act.trigger = abs(wrap_angle(aim - ship.angle)) < 10 and d < float(WEAPONS[weapon]["range"]) * 0.95
        act.cursor = (foe.x, foe.y)
        act.lay_mines = g.defenses.mines_carried > 0 and d < 200
        self.think = 0.0

    @staticmethod
    def _push(aim: float, x: float, y: float) -> Controls:
        """The thrusters that push the ship along (x, y) while its nose stays on `aim`."""
        a = math.radians(aim)
        fwd = x * math.sin(a) + y * math.cos(a)
        side = x * math.cos(a) - y * math.sin(a)
        return Controls(forward=fwd > 0.3, back=fwd < -0.3, right=side > 0.3, left=side < -0.3, aim=aim)

    # ------------------------------------------------------------ shopping

    def _next(self):
        """The next thing on the list the shop will sell: (phase, key, tier, offer), or None when
        the list is done. Things it can't sell (not in the shop yet, or already full) are passed over."""
        shop = self.game.shop
        while self.at < len(self.plan):
            phase, key, tier = self.plan[self.at]
            o = shop.offer(key, tier)
            if o.price is not None and not o.blocked:
                return phase, key, tier, o
            if o.blocked == "SOON" and key not in self.skipped:
                self.skipped.append(key)
            self._advance()
        return None

    def _advance(self) -> None:
        phase = self.plan[self.at][0]
        self.at += 1
        if self.at >= len(self.plan) or self.plan[self.at][0] != phase:
            self.done_at.setdefault(phase, self.game.time)

    def _lost_drills(self) -> int:
        """Drills it bought that the enemy has destroyed."""
        start = int(SHOP["start"].get("drills", 1))
        return max(0, start + self.drills_bought - self.game.shop.drills_owned())

    def _wants(self) -> list[str]:
        """What it would buy at the station right now."""
        g = self.game
        st = g.stage
        shop = g.shop
        out = []
        if st.hull < st.hull_max * float(self.p["repair_at"]) and shop.can_buy("repair"):
            out.append("repair")
        ring = self.ring()
        if ring is not None and ring.health < ring.max_health * 0.6 and shop.can_buy("ring"):
            out.append("ring_repair")
        if self._lost_drills() and shop.can_buy("drill"):
            out.append("drill_again")
        nxt = self._next()
        if nxt is not None and nxt[3].price <= g.credits:
            out.append(nxt[1])
        return out

    def _shopping(self, dt: float) -> None:
        """At the station: look round for `shop_seconds`, buy, and leave."""
        g = self.game
        shop = g.shop
        self.shop_t += dt
        if self.shop_t < float(self.p["shop_seconds"]):
            return
        st = g.stage
        if st.hull < st.hull_max * float(self.p["repair_at"]):
            while shop.can_buy("repair") and st.hull < st.hull_max - 1e-6:
                shop.buy("repair")
        ring = self.ring()
        if ring is not None and ring.health < ring.max_health * 0.6 and shop.can_buy("ring"):
            shop.buy("ring")
        while self._lost_drills() and shop.can_buy("drill"):
            shop.buy("drill")
            if self._lost_drills() == 0:
                break
        while True:
            nxt = self._next()
            if nxt is None or nxt[3].price > g.credits:
                break
            _, key, tier, _ = nxt
            if not shop.buy(key, tier):
                break
            if key == "drill":
                self.drills_bought += 1
            self._advance()
        g.close_station()
        self.shop_t = 0.0
        self.rest()

    # ------------------------------------------------------------ choosing a job

    def _plan(self) -> None:
        g = self.game
        st = g.stage
        ship = st.ship
        haul = g.haul
        name = self.job[0]
        if self.job_t > float(self.h["give_up"]) and name not in ("idle", "haul"):
            self.give_up(self.job[1] if name in ("drill", "tow") else None)
            name = "idle"
        # Carry on with a rock already on the lasso.
        if name in ("tow", "clear") and haul.rock == self.job[1]:
            return
        if haul.rock >= 0:
            self.set_job("drop")
            return
        if self.alarm is not None:
            x, y, until = self.alarm
            if until < g.time:
                self.alarm = None
            elif dist(ship.x, ship.y, x, y) > 250:
                self.set_job("defend", x, y)
                return
        if self._wants():
            self.set_job("shop")
            return
        if haul.rings_carried > 0:
            self.set_job("ring")
            return
        if g.defenses.carried:
            self.set_job("sentry")
            return
        loose = [ld for ld in st.loose if self.base_dist(ld.x, ld.y) < 3000]
        if loose:
            ld = min(loose, key=lambda ld: dist(ship.x, ship.y, ld.x, ld.y))
            self.set_job("loose", ld.uid)
            return
        ring = self.ring()
        if g.drills_carried > 0:
            i = self._drill_rock()
            if i is not None:
                self.set_job("drill", i)
                return
        junk = self._junk()
        if junk is not None:
            self.set_job("clear", junk)
            return
        if ring is not None and -1 in ring.slots and haul.level > 0:
            if name == "tow" and not self.left_alone(self.job[1]) and not st.field.gone[self.job[1]]:
                return
            i = self._tow_rock()
            if i is not None:
                self.set_job("tow", i)
                return
        if g.cargo > 0 or any(not self.in_ring(d.rock) for d in g.drills):
            self.set_job("haul")
            return
        self.set_job("idle")

    def _drill_rock(self) -> int | None:
        """The asteroid the next drill should go on: one held in the ring if there is one with ore,
        else the best ore asteroid within reach of home base (big, near, and where its drills already
        are, so they can be moved on together)."""
        g = self.game
        st = g.stage
        f = st.field
        ring = self.ring()
        if ring is not None:
            held = [i for i in ring.slots if i >= 0 and self.ore_left(i) > 1.0 and not self.left_alone(i)]
            if held:
                return min(held, key=lambda i: (self.drills_on(i), -self.ore_left(i)))
            if -1 in ring.slots and g.haul.level > 0 and self._tow_rock() is not None:
                return None               # wait for a rock in the ring instead
        for reach in self._reaches("mine_range"):
            idx, dx, dy = f.near(g.base.x, g.base.y, reach, reach)
            best, score = None, 0.0
            for i, a, b in zip(idx.tolist(), dx, dy):
                if self.left_alone(i):
                    continue
                ore = self.ore_left(i)
                if ore <= 1.0:
                    continue
                n = self.drills_on(i)
                each = ore / (n + 1)
                if each < 40.0:
                    continue              # not worth one more drill
                away = math.hypot(a, b)
                s = min(ore, 1000.0) * (1.5 if n else 1.0) / (away + 300.0)
                if s > score:
                    best, score = i, s
            if best is not None:
                return best
        return None

    def _reaches(self, key: str):
        """How far to look: `key` first, then wider and wider (by `range_grow`) up to `range_max`,
        for when the ore near home has been worked out."""
        reach = float(self.h[key])
        most = max(reach, float(self.h["range_max"]))
        while True:
            yield reach
            grow = float(self.h["range_grow"])
            if reach >= most or reach <= 0 or grow <= 1.0:
                return
            reach = min(most, reach * grow)

    def _junk(self) -> int | None:
        """A rock the ring caught that is no use there (no ore, or too small for a drill) and its
        lasso can pull out again."""
        g = self.game
        ring = self.ring()
        if ring is None or g.haul.level <= 0:
            return None
        f = g.stage.field
        most = g.haul.max_size(g.haul.level)
        for i in ring.slots:
            if i >= 0 and not f.gone[i] and f.size[i] <= most and self.ore_left(i) <= 1.0 \
                    and self.drills_on(i) == 0 and not self.left_alone(i):
                return i
        return None

    def _tow_rock(self) -> int | None:
        """The asteroid to tow into the ring next: ore, a size its lasso takes, near the ring, and
        best of all one its drills are already on."""
        g = self.game
        f = g.stage.field
        ring = self.ring()
        if ring is None:
            return None
        most = g.haul.max_size(g.haul.level)
        for reach in self._reaches("tow_range"):
            idx, dx, dy = f.near(ring.x, ring.y, reach, reach)
            best, score = None, 0.0
            for i, a, b in zip(idx.tolist(), dx, dy):
                if f.size[i] > most or i in ring.slots or self.left_alone(i):
                    continue
                ore = self.ore_left(i)
                if ore < 150.0:
                    continue
                s = (ore + 300.0 * self.drills_on(i)) / (math.hypot(a, b) + 500.0)
                if s > score:
                    best, score = i, s
            if best is not None:
                return best
        return None

    # ------------------------------------------------------------ the jobs

    def _do_idle(self, act: Act) -> None:
        """Nothing to do: wait by the ring, or by home base."""
        ring = self.ring()
        g = self.game
        want = (ring.x, ring.y + RING_STAND) if ring is not None else (g.base.x + 60.0, g.base.y - 60.0)
        self._go(act, want, 25.0)

    def _do_drop(self, act: Act) -> None:
        act.lasso = True
        self.set_job("idle")

    def _do_defend(self, act: Act) -> None:
        _, x, y = self.job
        if self._go(act, (x, y), 120.0) <= 120.0:
            self.alarm = None
            self.set_job("idle")

    def _do_shop(self, act: Act) -> None:
        g = self.game
        if not self._wants():
            self.set_job("idle")
            return
        if g.near_station() and self.ship.speed < 60:
            self.shop_t = 0.0
            g.open_station()
            return
        self._go(act, (g.base.x, g.base.y), 30.0)

    def _do_loose(self, act: Act) -> None:
        uid = self.job[1]
        ld = next((ld for ld in self.st.loose if ld.uid == uid), None)
        if ld is None:
            self.set_job("idle")
            self.think = 0.0
            return
        self._go(act, (ld.x, ld.y), float(DRILLS["float_pickup"]) * 0.6)

    def _free_side(self, i: int) -> float | None:
        """A side of asteroid i with room for a drill, as near the ship's side of it as there is."""
        g = self.game
        rx, ry = self.rock_pos(i)
        ship = self.ship
        first = angle_to(ship.x - rx, ship.y - ry)
        for k in range(0, 15):
            for sign in ((1,) if k == 0 else (1, -1)):
                side = wrap_angle(first + sign * k * 24.0)
                if not g._crowded(i, side):
                    return side
        return None

    def _do_drill(self, act: Act) -> None:
        g = self.game
        i = self.job[1]
        f = self.st.field
        if g.drills_carried <= 0 or self.ore_left(i) <= 1.0:
            self.set_job("idle")
            self.think = 0.0
            return
        spot = g.drillable()
        if spot is not None and (spot[0] == i or self.job_t > 25.0) and self.ship.speed < 80:
            act.set_drill = True
            self.think = 0.0
            return
        side = self._free_side(i)
        if side is None:
            self.give_up(i)
            return
        rx, ry = self.rock_pos(i)
        a = math.radians(side)
        r = float(f.r[i]) + 20.0
        self._go(act, (rx + math.sin(a) * r, ry + math.cos(a) * r), 8.0, ignore=(i,))

    def _do_haul(self, act: Act) -> None:
        """Load ore from the drills that have some and sell it at home base."""
        g = self.game
        ship = self.ship
        cargo_max = float(DRILLS["cargo"])
        outside = [d for d in g.drills if d.alive and not self.in_ring(d.rock)]
        ready = [d for d in outside if d.hold >= float(self.h["load_at"]) or (d.hold > 0 and not d.working)]
        full = g.cargo >= cargo_max - 1.0
        if full or (g.cargo >= float(self.h["home_at"])) or (g.cargo > 0 and not outside):
            self._go(act, (g.base.x, g.base.y), float(DRILLS["unload"]) * 0.6, through=True)
            return
        if not ready:
            if g.cargo > 0 and not any(d.working for d in outside):
                self._go(act, (g.base.x, g.base.y), float(DRILLS["unload"]) * 0.6, through=True)
                return
            ready = sorted(outside, key=lambda d: -d.hold)[:1]      # wait by the one that fills first
        if not ready:
            self.set_job("idle")
            return
        d = min(ready, key=lambda d: dist(ship.x, ship.y, d.x, d.y))
        a = math.radians(d.side)
        sx, sy = math.sin(a), math.cos(a)
        rx, ry = self.rock_pos(d.rock)
        ox, oy = ship.x - rx, ship.y - ry
        # Its own asteroid is only out of the way once the ship is round on the drill's side of it.
        near_side = ox * sx + oy * sy > 0.3 * math.hypot(ox, oy)
        self._go(act, (d.x + sx * 22.0, d.y + sy * 22.0), 24.0, ignore=(d.rock,) if near_side else ())

    # ------------------------------------------------------------ the ring

    def _ring_spot(self) -> tuple[float, float] | None:
        """Somewhere near home base with room for the ring, a little to spare all round, and as
        few loose rocks about as it can find (the ring catches any rock that drifts into it)."""
        g = self.game
        haul = g.haul
        f = g.stage.field
        near, far = self.h["ring_range"]
        r = float(near)
        best, fewest = None, 1e9
        while r <= float(far):
            start = self.rng.uniform(0, math.tau)
            for k in range(16):
                a = start + k * math.tau / 16
                x, y = g.base.x + math.cos(a) * r, g.base.y + math.sin(a) * r
                if not all(haul.ring_room(x + ox, y + oy) in ("", "ENEMY")
                           for ox, oy in ((0, 0), (22, 0), (-22, 0), (0, 22), (0, -22))):
                    continue
                rocks = len(f.near(x, y, 260.0, 260.0)[0]) + r / 300.0
                if rocks < fewest:
                    best, fewest = (x, y), rocks
            if best is not None and fewest < 2.0 + r / 300.0:
                break
            r += 60.0
        return best

    def _do_ring(self, act: Act) -> None:
        g = self.game
        haul = g.haul
        if haul.rings_carried <= 0:
            self.ring_site = None
            self.rest() if haul.has_ring() else self.set_job("idle")
            return
        if self.keying >= 0:
            # T is held (the outline shows); let go to set it down.
            self.keying += self.dt
            if self.keying < 0.25:
                act.ring_key = True
            elif self.keying > 0.5:
                self.keying = -1.0
                self.ring_site = None           # it didn't take: look for another spot
            self._go(act, (self.ship.x, self.ship.y), 1e9)
            return
        if self.ring_site is None:
            self.ring_site = self._ring_spot()
            if self.ring_site is None:
                self.set_job("idle")
                return
        if self._go(act, self.ring_site, 8.0) <= 8.0 and self.ship.speed < 25:
            self.keying = 0.0
            act.ring_key = True

    def _do_clear(self, act: Act) -> None:
        """Pull a useless rock out of the ring and leave it well outside."""
        g = self.game
        haul = g.haul
        f = self.st.field
        ship = self.ship
        i = self.job[1]
        ring = self.ring()
        if ring is None or f.gone[i] or (haul.rock != i and i not in ring.slots):
            self.set_job("idle")
            self.think = 0.0
            return
        rx, ry = self.rock_pos(i)
        ox, oy = rx - ring.x, ry - ring.y
        gap = math.hypot(ox, oy) or 1.0
        if haul.rock != i:
            t = haul.target()
            if t is not None and t[0] == i and t[1] and ship.speed < 120:
                act.lasso = True
                return
            r = float(f.r[i]) + 26.0
            self._go(act, (rx + ox / gap * r, ry + oy / gap * r), 8.0, ignore=(i,))
            return
        if gap > FIELD_R + 140.0:
            act.lasso = True
            self.set_job("idle")
            self.think = 0.0
            return
        sx, sy = ship.x - ring.x, ship.y - ring.y
        n = math.hypot(sx, sy) or 1.0
        self._go(act, (ring.x + sx / n * (n + 300.0), ring.y + sy / n * (n + 300.0)), 0.0,
                 cap=float(self.p["tow_speed"]), ignore=(i,), through=True)

    def _do_sentry(self, act: Act) -> None:
        g = self.game
        if not g.defenses.carried:
            self.rest()
            return
        haul = g.haul
        ring = self.ring()
        if ring is not None and haul.free_mount():
            if self._go(act, (ring.x, ring.y), INNER * 0.5) <= INNER * 0.9:
                act.place_sentry = True
            return
        # No ring (or its mounts are full): guard home base.
        if g.defenses.sentry_room(self.ship.x, self.ship.y) == "" and 110 < self.base_dist(self.ship.x, self.ship.y) < 240:
            act.place_sentry = True
            return
        n = len(g.defenses.sentries)
        a = n * 2.4
        self._go(act, (g.base.x + math.cos(a) * 170.0, g.base.y + math.sin(a) * 170.0), 12.0)

    def _do_tow(self, act: Act) -> None:
        """Fetch an asteroid on the lasso and bring it into the ring along a free spot's diagonal,
        so the ring catches it in that spot."""
        g = self.game
        haul = g.haul
        st = self.st
        f = st.field
        ship = st.ship
        i = self.job[1]
        ring = self.ring()
        if ring is None or f.gone[i] or -1 not in ring.slots or i in ring.slots:
            if haul.rock >= 0:
                act.lasso = True
            self.set_job("idle")
            self.think = 0.0
            return
        rx, ry = self.rock_pos(i)
        r = float(f.r[i])
        if haul.rock != i:
            # Go and get it.
            t = haul.target()
            if t is not None and t[0] == i and t[1] and ship.speed < 120:
                act.lasso = True
                self.job_t = 0.0
                return
            ux, uy = ship.x - rx, ship.y - ry
            n = math.hypot(ux, uy) or 1.0
            if self.grab_dir is not None:
                ux, uy, n = self.grab_dir[0], self.grab_dir[1], 1.0
            left = self._go(act, (rx + ux / n * (r + 28.0), ry + uy / n * (r + 28.0)), 8.0, ignore=(i,))
            self.tow_slot = -1
            if left <= 10.0 and ship.speed < 30:
                # In place, but Q would take some nearer rock: come at this one from another side.
                self.grab_t += self.dt
                if self.grab_t > 1.0:
                    self.grab_t = 0.0
                    self.grab_try += 1
                    if self.grab_try > 5:
                        self.give_up(i)
                        return
                    a = math.atan2(uy / n, ux / n) + math.radians(70.0)
                    self.grab_dir = (math.cos(a), math.sin(a))
            return
        # Towing it home: to a gate out along a free spot's diagonal, then straight down the
        # diagonal, so the rock swings in behind and arrives lined up with its spot.
        free = [k for k, j in enumerate(ring.slots) if j < 0]
        if self.tow_slot not in free:
            self.tow_slot = min(free, key=lambda k: dist(ship.x, ship.y, ring.x + NODE_DIRS[k][0] * TOW_GATE,
                                                         ring.y + NODE_DIRS[k][1] * TOW_GATE))
            self.lined = False
        dx, dy = NODE_DIRS[self.tow_slot]
        gap = dist(rx, ry, ring.x, ring.y)
        if gap + float(f.size[i]) / 4 <= FIELD_R - 8.0:
            act.lasso = True              # inside the field: let go and the ring takes it
            self.tow_slot = -1
            self.rest()
            return
        speed = float(self.p["tow_speed"])
        along = (ship.x - ring.x) * dx + (ship.y - ring.y) * dy
        if self.escape > 0:
            self.lined = False            # it got stuck: come round again
        if not self.lined:
            gate = (ring.x + dx * TOW_GATE, ring.y + dy * TOW_GATE)
            if self._go(act, gate, 20.0, cap=speed, pad=r + 10.0, ignore=(i,), slope=0.8) <= 30.0:
                self.lined = True
            return
        off = abs((rx - ring.x) * dy - (ry - ring.y) * dx)        # how far the rock is off the diagonal
        if off > 30.0 and gap < 190.0:
            self.lined = False            # it would clip a rock the ring already holds
            return
        ahead = along - 120.0
        self._go(act, (ring.x + dx * ahead, ring.y + dy * ahead), 0.0, cap=min(speed, 110.0) if along < 240.0 else speed,
                 pad=8.0, ignore=(i,), through=True)
