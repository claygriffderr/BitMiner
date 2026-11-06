"""How enemies fight: infantry fly in squads, guards wall them off and ram you, rapid ships raid.

Enemies have no boosters. Each one flies straight at its steady speed toward the point its brain
picks, stops dead and turns on the spot, so all their movement is hard angles. Brains pick a new
point every `replan` seconds. Only a hit (a missile blast, a ram, a rock) gives them momentum.

Behaviour numbers come from `data/combat.json`; speeds, health and guns from `data/weapons.json`.
"""

from __future__ import annotations

import math
import random

from ..field import wrap_delta
from ..flight import angle_to, forward_vector, right_vector, wrap_angle
from . import shapes
from .specs import AI, ENEMIES, ENEMY_WEAPONS, WAVES
from .stage import ENEMY_GUN, SCOOP_REACH, Anim, Enemy, Lane, Stage, dist

FORMATIONS = ("line", "wedge", "arc")


def unit(dx: float, dy: float) -> tuple[float, float, float]:
    d = math.hypot(dx, dy)
    if d < 1e-9:
        return 0.0, 0.0, 0.0
    return dx / d, dy / d, d


# ---------------------------------------------------------------- brains

class Brain:
    """Flies one enemy. `goal` is the point it is heading for, or None to stay put."""

    kind = ""

    def __init__(self, battle: "Battle", e: Enemy):
        self.battle = battle
        self.e = e
        self.goal: tuple[float, float] | None = None
        self.cfg = AI[self.kind]
        self.speed = float(ENEMIES[e.kind]["speed"])
        e.brain = self

    @property
    def stage(self) -> Stage:
        return self.battle.stage

    def moved(self, dx: float, dy: float) -> None:
        """The stage moved this enemy to another copy of wrapping space: move the goal with it."""
        if self.goal is not None:
            self.goal = (self.goal[0] + dx, self.goal[1] + dy)

    def fly(self, dt: float, speed: float | None = None) -> bool:
        """Head straight for the goal, around rocks. True once there."""
        e = self.e
        if self.goal is None:
            e.mx = e.my = 0.0
            return True
        ux, uy, d = unit(self.goal[0] - e.x, self.goal[1] - e.y)
        if d < 0.75:
            e.mx = e.my = 0.0
            return True
        v = min(self.speed if speed is None else speed, d / max(dt, 1e-6))
        ux, uy = self.battle.avoid(e, ux, uy, min(d, AI["avoid"]["look"]))
        e.mx, e.my = ux * v, uy * v
        return False

    def face(self, x: float, y: float) -> None:
        e = self.e
        if abs(x - e.x) + abs(y - e.y) > 0.01:
            e.heading = angle_to(x - e.x, y - e.y)

    def face_travel(self) -> None:
        e = self.e
        if abs(e.mx) + abs(e.my) > 1.0:
            e.heading = angle_to(e.mx, e.my)

    def shoot(self, kind: str, lead: float, spread: float) -> None:
        """Fire at you, leading your movement by `lead` (0 to 1) and scattering by `spread` degrees."""
        st = self.stage
        e = self.e
        ship = st.ship
        spec = ENEMY_WEAPONS["infantry_laser" if kind == "infantry" else "rapid_laser"]
        gx, gy = e.point(*ENEMY_GUN[e.kind])
        t = dist(gx, gy, ship.x, ship.y) / spec["speed"]
        ax, ay = ship.x + ship.vx * t * lead, ship.y + ship.vy * t * lead
        h = angle_to(ax - gx, ay - gy) + self.battle.rng.gauss(0.0, spread)
        fx, fy = forward_vector(h)
        st.enemy_shot(e, kind, (gx + fx * 100, gy + fy * 100))
        st.events.append(("enemy_fire", e.kind))

    def clear_shot(self) -> bool:
        """Is there a straight line from this enemy's gun to you, with no rock in it?"""
        st = self.stage
        e = self.e
        gx, gy = e.point(*ENEMY_GUN.get(e.kind, (0.0, 0.0)))
        return st.rock_hit(gx, gy, st.ship.x, st.ship.y, 1.5) is None

    def step(self, dt: float) -> None:
        raise NotImplementedError


class InfantryBrain(Brain):
    """Holds its slot in the squad's formation, guns on you, firing whenever it has a clear shot."""

    kind = "infantry"

    def __init__(self, battle: "Battle", e: Enemy):
        super().__init__(battle, e)
        self.squad: Squad | None = None
        self.every = float(ENEMY_WEAPONS["infantry_laser"]["fire_every"])
        self.fire_in = battle.rng.uniform(0.3, 1.0) * self.every

    def step(self, dt: float) -> None:
        st = self.stage
        e = self.e
        ship = st.ship
        self.fly(dt)
        near = dist(e.x, e.y, ship.x, ship.y) < self.cfg["fire_range"] * 1.15
        if near and st.ship_visible:
            self.face(ship.x, ship.y)       # guns on you, even while it shuffles along
        else:
            self.face_travel()
        self.fire_in -= dt
        if self.fire_in > 0:
            return
        if not st.ship_visible or dist(e.x, e.y, ship.x, ship.y) > self.cfg["fire_range"]:
            self.fire_in = 0.2
            return
        if not self.clear_shot():
            self.fire_in = 0.25
            return
        self.shoot("infantry", self.cfg["aim_lead"], self.cfg["spread"])
        self.fire_in = self.every * self.battle.rng.uniform(0.8, 1.25)


class GuardBrain(Brain):
    """Stands between you and the squad it guards. When it or an ally is in trouble, it rams you."""

    kind = "guard"

    def __init__(self, battle: "Battle", e: Enemy):
        super().__init__(battle, e)
        self.spec = ENEMIES["guard"]
        self.state = "wall"
        self.t = 0.0
        self.plan_in = 0.0
        self.cooldown = battle.rng.uniform(0.5, 1.5)
        self.alert = 0.0
        self.lane: Lane | None = None
        self.reach = 0.0
        self.travelled = 0.0
        self.guarding: Squad | None = None
        self.slot = (0, 1)           # its place in the wall: index and how many guards share it

    def tip(self) -> tuple[float, float]:
        return self.e.point(0.0, SCOOP_REACH - 1)

    def wants_to_ram(self) -> bool:
        st = self.stage
        e = self.e
        cfg = self.cfg
        ship = st.ship
        if self.cooldown > 0 or not st.ship_visible:
            return False
        d = dist(e.x, e.y, ship.x, ship.y)
        if d > cfg["ram_range"]:
            return False
        alone = self.guarding is None
        trouble = (e.health < cfg["low"] * e.max_health or self.alert > 0
                   or (alone and d < cfg["alone_ram"]))
        if not trouble:
            return False
        return st.rock_hit(e.x, e.y, ship.x, ship.y, 4.0) is None

    def plan_wall(self) -> None:
        st = self.stage
        e = self.e
        cfg = self.cfg
        ship = st.ship
        sq = self.guarding
        if sq is None or not sq.members:
            # Nothing to guard: close in on you, ready to ram.
            ux, uy, d = unit(e.x - ship.x, e.y - ship.y)
            if d < 1e-6:
                ux, uy = 0.0, 1.0
            keep = cfg["alone_ram"] * 0.8
            self.goal = (ship.x + ux * keep, ship.y + uy * keep)
            return
        cx, cy = sq.centre()
        ux, uy, d = unit(ship.x - cx, ship.y - cy)
        if d < 1e-6:
            ux, uy = 0.0, 1.0
        gap = min(cfg["wall_gap"], d * 0.5)
        i, n = self.slot
        side = (i - (n - 1) / 2) * cfg["spacing"]
        self.goal = (cx + ux * gap + uy * side, cy + uy * gap - ux * side)

    def step(self, dt: float) -> None:
        st = self.stage
        e = self.e
        cfg = self.cfg
        spec = self.spec
        ship = st.ship
        self.cooldown = max(0.0, self.cooldown - dt)
        self.alert = max(0.0, self.alert - dt)
        self.t += dt

        if self.state == "wall":
            self.plan_in -= dt
            if self.plan_in <= 0:
                self.plan_in = cfg["replan"]
                self.plan_wall()
            self.fly(dt)
            self.face(ship.x, ship.y)
            if self.wants_to_ram():
                self._enter("deploy")
                e.mx = e.my = 0.0
            return

        e.mx = e.my = 0.0
        if self.state == "deploy":
            # The scoop folds out in three steps and locks with a glint.
            self.face(ship.x, ship.y)
            e.ram = min(3, 1 + int(self.t / 0.12))
            if self.t >= 0.36:
                e.ram = 3
                tip = self.tip
                st.anims.append(Anim("glint", (), 4, 12, *tip(), follow=lambda: (*tip(), 0.0)))
                self._enter("glint")
        elif self.state == "glint":
            self.face(ship.x, ship.y)
            if self.t >= 0.2:
                if not st.ship_visible:
                    self._enter("fold")
                    return
                # The lane flashes along the path it is about to take, then the heading is locked.
                self.face(ship.x, ship.y)
                self.reach = dist(e.x, e.y, ship.x, ship.y) + 40
                self.lane = Lane("ram", e.x, e.y, e.heading, self.reach)
                st.lanes.append(self.lane)
                self._enter("warn")
        elif self.state == "warn":
            if self.t >= spec["warn_time"]:
                self._drop_lane()
                self.travelled = 0.0
                e.ramming = True
                st.events.append(("ram", "guard"))
                self._enter("dash")
        elif self.state == "dash":
            self._dash(dt)
        elif self.state == "recoil":
            if self.t >= 0.45:
                self._enter("fold")
        elif self.state == "fold":
            e.ram = max(0, 2 - int(self.t / 0.1))
            if self.t >= 0.3:
                e.ram = 0
                self.cooldown = cfg["ram_cooldown"]
                self.alert = 0.0
                self.plan_in = 0.0
                self._enter("wall")

    def _enter(self, state: str) -> None:
        self.state = state
        self.t = 0.0

    def _drop_lane(self) -> None:
        if self.lane is not None and self.lane in self.stage.lanes:
            self.stage.lanes.remove(self.lane)
        self.lane = None

    def _dash(self, dt: float) -> None:
        st = self.stage
        e = self.e
        speed = self.spec["ram_speed"]
        fx, fy = forward_vector(e.heading)
        step = speed * dt
        x0, y0 = self.tip()
        x1, y1 = x0 + fx * step, y0 + fy * step
        # You first, then any rock in the way.
        for i in range(1, 7):
            px, py = x0 + (x1 - x0) * i / 6, y0 + (y1 - y0) * i / 6
            if st.player_blocks(px, py, 1.0):
                e.x += px - x0
                e.y += py - y0
                st.ram_hit(e, px, py, fx, fy)
                self._end_dash()
                return
        rock = st.rock_hit(x0, y0, x1, y1, 1.0)
        if rock is not None:
            e.x += rock[0] - x0
            e.y += rock[1] - y0
            st.ram_rock(e, rock[0], rock[1], fx, fy, rock[2])
            self._end_dash()
            return
        e.mx, e.my = fx * speed, fy * speed
        self.travelled += step
        if self.travelled >= self.reach + 30:
            self._end_dash()

    def _end_dash(self) -> None:
        e = self.e
        e.mx = e.my = 0.0
        e.ramming = False
        self._enter("recoil")


class RapidBrain(Brain):
    """Waits behind you, dives past one side firing a burst, carries on out, and comes round again."""

    kind = "rapid"

    def __init__(self, battle: "Battle", e: Enemy):
        super().__init__(battle, e)
        self.gun = ENEMY_WEAPONS["rapid_laser"]
        self.state = "hold"
        self.t = 0.0
        self.plan_in = 0.0
        self.offset = battle.rng.uniform(-1.0, 1.0) * self.cfg["hold_spread"]   # degrees off straight behind you
        self.rest = battle.rng.uniform(*self.cfg["rest"])
        self.fired = 0
        self.shot_in = 0.0

    def step(self, dt: float) -> None:
        st = self.stage
        e = self.e
        cfg = self.cfg
        ship = st.ship
        self.t += dt
        if self.state == "hold":
            self.plan_in -= dt
            if self.plan_in <= 0:
                self.plan_in = cfg["replan"]
                fx, fy = forward_vector(ship.angle + 180.0 + self.offset)
                self.goal = (ship.x + fx * cfg["hold_range"], ship.y + fy * cfg["hold_range"])
            there = self.fly(dt)
            if there or dist(e.x, e.y, *self.goal) < 30:
                self.rest -= dt
                self.face(ship.x, ship.y)
            else:
                self.face_travel()
            if self.rest <= 0 and st.ship_visible:
                self._dive()
            return
        # Diving.
        there = self.fly(dt)
        self.face_travel()
        dx, dy = ship.x - e.x, ship.y - e.y
        hx, hy = forward_vector(e.heading)
        ahead = dx * hx + dy * hy > 0
        if (st.ship_visible and self.fired < self.gun["burst"] and ahead
                and math.hypot(dx, dy) < cfg["fire_range"]):
            self.shot_in -= dt
            if self.shot_in <= 0:
                self.shoot("rapid", cfg["aim_lead"], cfg["spread"])
                self.fired += 1
                self.shot_in = self.gun["burst_gap"]
        if there or self.t > cfg["pass_time"]:
            self.state = "hold"
            self.t = 0.0
            self.plan_in = 0.0
            self.offset = self.battle.rng.uniform(-1.0, 1.0) * cfg["hold_spread"]
            self.rest = self.battle.rng.uniform(*self.cfg["rest"])

    def _dive(self) -> None:
        st = self.stage
        e = self.e
        cfg = self.cfg
        ship = st.ship
        rng = self.battle.rng
        d = dist(e.x, e.y, ship.x, ship.y)
        lead = d / max(1.0, self.speed) * 0.5
        px, py = ship.x + ship.vx * lead, ship.y + ship.vy * lead
        ux, uy, _ = unit(px - e.x, py - e.y)
        side = rng.choice((-1.0, 1.0))
        px, py = px + uy * cfg["pass_offset"] * side, py - ux * cfg["pass_offset"] * side
        ux, uy, _ = unit(px - e.x, py - e.y)
        self.goal = (px + ux * cfg["overshoot"], py + uy * cfg["overshoot"])
        self.state = "dive"
        self.t = 0.0
        self.fired = 0
        self.shot_in = 0.0


BRAINS = {"infantry": InfantryBrain, "guard": GuardBrain, "rapid": RapidBrain}


# ---------------------------------------------------------------- squads

class Squad:
    """Infantry flying together in a formation that keeps `standoff` from you and drifts round you."""

    def __init__(self, battle: "Battle", members: list[Enemy], formation: str):
        self.battle = battle
        self.members = list(members)
        self.formation = formation if formation in FORMATIONS else "line"
        self.cfg = AI["infantry"]
        ship = battle.stage.ship
        cx, cy = self.centre()
        self.bearing = angle_to(cx - ship.x, cy - ship.y)     # where it sits around you
        self.turn = battle.rng.choice((-1.0, 1.0))
        self.plan_in = 0.0
        for m in self.members:
            m.brain.squad = self

    def centre(self) -> tuple[float, float]:
        live = self.members
        if not live:
            return self.battle.stage.ship.x, self.battle.stage.ship.y
        return sum(m.x for m in live) / len(live), sum(m.y for m in live) / len(live)

    @property
    def width(self) -> float:
        return max(0, len(self.members) - 1) * self.cfg["spacing"]

    def join(self, other: "Squad") -> None:
        for m in other.members:
            m.brain.squad = self
        self.members += other.members
        other.members = []
        self.plan_in = 0.0

    def step(self, dt: float) -> None:
        self.plan_in -= dt
        if self.plan_in <= 0:
            self.plan_in = self.cfg["replan"] * self.battle.rng.uniform(0.85, 1.15)
            self.plan()

    def plan(self) -> None:
        cfg = self.cfg
        rng = self.battle.rng
        ship = self.battle.stage.ship
        if rng.random() < cfg.get("orbit_flip", 0.0):
            self.turn = -self.turn
        self.bearing = wrap_angle(self.bearing + self.turn * cfg["orbit"] * cfg["replan"])
        # Keep clear of the other squads round you.
        for other in self.battle.squads:
            if other is self or not other.members:
                continue
            need = math.degrees((self.width / 2 + other.width / 2 + cfg["squad_gap"]) / cfg["standoff"])
            diff = wrap_angle(self.bearing - other.bearing)
            if abs(diff) < need:
                push = (need - abs(diff)) * 0.5
                self.bearing = wrap_angle(self.bearing + (push if diff > 0 else -push if diff < 0 else push * self.turn))
        slots = self.slots(ship.x, ship.y)
        # Fill the slots in order across the formation, so nobody crosses another's path.
        rx, ry = right_vector(self.bearing + 180.0)
        order = sorted(self.members, key=lambda m: (m.x - ship.x) * rx + (m.y - ship.y) * ry)
        for m, slot in zip(order, slots):
            m.brain.goal = slot

    def slots(self, sx: float, sy: float) -> list[tuple[float, float]]:
        """Formation points, left to right as seen from the squad looking at you."""
        cfg = self.cfg
        n = len(self.members)
        R, gap = cfg["standoff"], cfg["spacing"]
        if self.formation == "arc":
            step = math.degrees(gap / R)
            pts = []
            for i in range(n):
                fx, fy = forward_vector(self.bearing - (i - (n - 1) / 2) * step)
                pts.append((sx + fx * R, sy + fy * R))
            return pts
        fx, fy = forward_vector(self.bearing)
        ax, ay = sx + fx * R, sy + fy * R
        face = self.bearing + 180.0                 # the formation looks at you
        tx, ty = forward_vector(face)
        rx, ry = right_vector(face)
        offsets = []
        if self.formation == "line":
            offsets = [((i - (n - 1) / 2) * gap, 0.0) for i in range(n)]
        else:   # wedge: the leader nearest you, the rest trailing back on both sides
            for i in range(n):
                k = (i + 1) // 2
                side = -1 if i % 2 else 1
                offsets.append((side * k * gap * 0.8, -k * gap * 0.7))
            offsets.sort()
        return [(ax + r * rx + f * tx, ay + r * ry + f * ty) for r, f in offsets]


# ---------------------------------------------------------------- the battle

class Battle:
    """Every enemy brain on a stage, plus the squads infantry fly in."""

    def __init__(self, stage: Stage, seed: int = 1):
        self.stage = stage
        self.rng = random.Random(seed)
        self.squads: list[Squad] = []
        self._flying: list[Enemy] = []

    def clear(self) -> None:
        self.squads = []
        self._flying = []

    # ------------------------------------------------------------ adding enemies

    def add(self, kind: str, x: float, y: float, heading: float = 180.0, warp: bool = True) -> Enemy:
        e = self.stage.spawn(kind, x, y, heading=heading, warp=warp)
        if kind in BRAINS:
            BRAINS[kind](self, e)
        return e

    def add_group(self, kind: str, count: int, x: float, y: float, formation: str = "line",
                  warp: bool = True) -> list[Enemy]:
        """A group arriving at (x, y), already in formation and facing you."""
        ship = self.stage.ship
        face = angle_to(ship.x - x, ship.y - y)
        rx, ry = right_vector(face)
        fx, fy = forward_vector(face)
        if kind == "infantry":
            gap = AI["infantry"]["spacing"]
            if formation == "wedge":
                offs = [(((i + 1) // 2) * (-1 if i % 2 else 1) * gap * 0.8, -((i + 1) // 2) * gap * 0.7)
                        for i in range(count)]
            else:
                offs = [((i - (count - 1) / 2) * gap, 0.0) for i in range(count)]
        elif kind == "guard":
            gap = AI["guard"]["spacing"] * 1.4
            offs = [((i - (count - 1) / 2) * gap, 20.0) for i in range(count)]
        else:
            offs = [((i - (count - 1) / 2) * 40.0, -abs(i - (count - 1) / 2) * 16.0) for i in range(count)]
        members = []
        for r, f in offs:
            px, py = self.clear_spot(x + r * rx + f * fx, y + r * ry + f * fy, kind)
            members.append(self.add(kind, px, py, heading=face, warp=warp))
        if kind == "infantry" and members:
            self.squads.append(Squad(self, members, formation))
        return members

    def clear_spot(self, x: float, y: float, kind: str) -> tuple[float, float]:
        """Nudge a spawn point out of any rock, outward from you."""
        st = self.stage
        f = st.field
        if f is None or not len(f):
            return x, y
        r = shapes.reach(kind) + 2
        ship = st.ship
        ux, uy, _ = unit(x - ship.x, y - ship.y)
        if ux == uy == 0.0:
            ux, uy = 0.0, 1.0
        for _ in range(16):
            idx, dx, dy = f.near(x, y, r, r)
            if not any(math.hypot(a, b) < f.r[i] + r for i, a, b in zip(idx, dx, dy)):
                break
            x, y = x + ux * 12, y + uy * 12
        return x, y

    # ------------------------------------------------------------ steering

    def avoid(self, e: Enemy, ux: float, uy: float, ahead: float) -> tuple[float, float]:
        """Swing round a rock in the way, on the side the path already leans to."""
        st = self.stage
        f = st.field
        if f is None or ahead <= 0:
            return ux, uy
        r = e.body_r + AI["avoid"]["margin"]
        hit = st.rock_hit(e.x, e.y, e.x + ux * ahead, e.y + uy * ahead, r)
        if hit is None:
            return ux, uy
        i = hit[2]
        cx = wrap_delta(f.x[i] - e.x, f.width)
        cy = wrap_delta(f.y[i] - e.y, f.height)
        cd = math.hypot(cx, cy) or 1.0
        if ux * cy - uy * cx > 0:      # rock to the left of the path: pass it on the right
            tx, ty = cy / cd, -cx / cd
        else:
            tx, ty = -cy / cd, cx / cd
        sx, sy = tx + ux * 0.25, ty + uy * 0.25
        n = math.hypot(sx, sy) or 1.0
        return sx / n, sy / n

    # ------------------------------------------------------------ the update

    def step(self, dt: float) -> None:
        st = self.stage
        flying = [e for e in st.enemies if e.alive and e.dying < 0 and e.brain is not None]
        alive = set(id(e) for e in flying)
        fallen = [e for e in self._flying if id(e) not in alive]
        self._flying = flying
        for e in fallen:
            if isinstance(e.brain, GuardBrain):
                e.brain._drop_lane()        # a guard shot down mid-warning takes its lane with it

        for sq in self.squads:
            sq.members = [m for m in sq.members if id(m) in alive]
        self.squads = [sq for sq in self.squads if sq.members]
        # A lone infantry ship joins the nearest squad.
        for sq in list(self.squads):
            if len(sq.members) == 1 and len(self.squads) > 1:
                cx, cy = sq.centre()
                others = [o for o in self.squads if o is not sq and o.members]
                best = min(others, key=lambda o: dist(cx, cy, *o.centre()))
                best.join(sq)
        self.squads = [sq for sq in self.squads if sq.members]

        self._assign_guards(flying, fallen)
        for sq in self.squads:
            sq.step(dt)
        for e in flying:
            if e.fade_in < 1.0:
                e.mx = e.my = 0.0
                continue
            e.brain.step(dt)

    def _assign_guards(self, flying: list[Enemy], fallen: list[Enemy]) -> None:
        cfg = AI["guard"]
        guards = [e for e in flying if e.kind == "guard"]
        if not guards:
            return
        by_squad: dict[int, list[Enemy]] = {}
        centres = [(sq, sq.centre()) for sq in self.squads]
        for g in guards:
            b: GuardBrain = g.brain
            best = None
            if centres:
                best = min(centres, key=lambda c: dist(g.x, g.y, *c[1]))[0]
            b.guarding = best
            if best is not None:
                by_squad.setdefault(id(best), []).append(g)
            # Trouble nearby puts it on alert.
            for e in flying:
                if (e.kind != "guard" and e.health < cfg["ally_low"] * e.max_health
                        and dist(g.x, g.y, e.x, e.y) < cfg["ally_radius"]):
                    b.alert = cfg["alert"]
                    break
            for e in fallen:
                if e.kind != "guard" and dist(g.x, g.y, e.x, e.y) < cfg["ally_radius"]:
                    b.alert = cfg["alert"]
                    break
        ship = self.stage.ship
        for members in by_squad.values():
            # Order the wall across the line to you, so guards don't swap sides.
            sq = members[0].brain.guarding
            cx, cy = sq.centre()
            ux, uy, _ = unit(ship.x - cx, ship.y - cy)
            members.sort(key=lambda g: (g.x - cx) * uy - (g.y - cy) * ux)
            for i, g in enumerate(members):
                g.brain.slot = (i, len(members))


# ---------------------------------------------------------------- waves

class Waves:
    """Sends the waves listed in `combat.json` on a timer, whether or not you cleared the last one."""

    def __init__(self, battle: Battle, spec: dict | None = None):
        self.battle = battle
        self.spec = spec or WAVES
        self.launched = 0
        self.timer = float(self.spec["first"])
        self.name = ""

    @property
    def number(self) -> int:
        """The wave you are fighting (0 before the first)."""
        return self.launched

    def call_now(self) -> None:
        self.timer = 0.0

    def step(self, dt: float) -> None:
        self.timer -= dt
        if self.timer > 0:
            return
        live = sum(1 for e in self.battle.stage.enemies if e.alive and e.dying < 0)
        if live >= self.spec.get("cap", 10 ** 6):
            self.timer = 1.0
            return
        self.launch()

    def launch(self) -> None:
        spec = self.spec
        battle = self.battle
        st = battle.stage
        rng = battle.rng
        ship = st.ship
        waves = spec["list"]
        wave = waves[self.launched % len(waves)]
        lap = self.launched // len(waves)
        groups = wave["groups"]
        bearing = rng.uniform(0.0, 360.0)
        R = spec["spawn_distance"]
        for gi, g in enumerate(groups):
            kind = g["kind"]
            count = int(g["count"]) + lap * int(spec.get("grow", 0))
            if kind == "rapid":
                b = ship.angle + 180.0 + rng.uniform(-1.0, 1.0) * spec.get("raid_spread", 50)   # from behind you
            else:
                b = bearing + (gi - (len(groups) - 1) / 2) * spec.get("group_spread", 28)
            fx, fy = forward_vector(b)
            battle.add_group(kind, count, ship.x + fx * R, ship.y + fy * R, g.get("formation", "line"))
        self.launched += 1
        self.name = wave["name"]
        self.timer = float(wave.get("next", spec["every"]))
        st.events.append(("wave", self.launched, self.name))
