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
from .hunt import Task
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
        # Watching for being stuck: where it was when the watch began, and how far it meant to fly since.
        self.watch_from = (e.x, e.y)
        self.watch_t = 0.0
        self.watch_want = 0.0
        self.escape = 0.0             # seconds left breaking loose
        self.escape_dir = (0.0, 0.0)
        self.stuck_count = 0          # times in a row it got stuck
        self.detour: tuple[float, float] | None = None   # a point off to the side, round the rocks
        self.detour_t = 0.0
        self.detour_side = 0.0
        # Secure the Base: where it goes on its own while the enemy doesn't know where you are.
        self.task = Task(battle)
        self.aim: tuple[float, float, str] | None = None
        self.cruising = False         # its group has a long way to go: fly at cruise speed

    @property
    def stage(self) -> Stage:
        return self.battle.stage

    def moved(self, dx: float, dy: float) -> None:
        """The stage moved this enemy to another copy of wrapping space: move its points with it."""
        if self.goal is not None:
            self.goal = (self.goal[0] + dx, self.goal[1] + dy)
        if self.detour is not None:
            self.detour = (self.detour[0] + dx, self.detour[1] + dy)
        self.watch_from = (self.watch_from[0] + dx, self.watch_from[1] + dy)

    def fly(self, dt: float, speed: float | None = None) -> bool:
        """Head straight for the goal, around rocks. True once there."""
        e = self.e
        top = self.speed if speed is None else speed
        if self.escape > 0:
            # Breaking loose: straight out along the most open way it found.
            self.escape -= dt
            e.mx, e.my = self.escape_dir[0] * top, self.escape_dir[1] * top
            if self.escape <= 0:
                self._reset_watch()
                self._plan_detour()
            return False
        if self.detour is not None:
            # Out of the pocket: go round by the side before heading for the goal again.
            self.detour_t -= dt
            if self.goal is None or self.detour_t <= 0 or dist(e.x, e.y, *self.detour) < 12:
                self.detour = None
        target = self.detour if self.detour is not None else self.goal
        if target is None:
            e.mx = e.my = 0.0
            self._reset_watch()
            return True
        ux, uy, d = unit(target[0] - e.x, target[1] - e.y)
        if d < 0.75 and self.detour is None:
            e.mx = e.my = 0.0
            self._reset_watch()
            return True
        hunt = self.battle.hunt
        if hunt is not None and speed is None and (self.cruising or d > hunt.spec["cruise_from"]):
            top = max(top, hunt.spec["cruise_speed"])     # a long way to go: cruise
        v = min(top, d / max(dt, 1e-6))
        ux, uy = self.battle.avoid(e, ux, uy, min(d, AI["avoid"]["look"]))
        e.mx, e.my = ux * v, uy * v
        self._watch(dt, min(v * dt, d))
        return False

    def _reset_watch(self) -> None:
        self.watch_from = (self.e.x, self.e.y)
        self.watch_t = 0.0
        self.watch_want = 0.0

    def _watch(self, dt: float, want: float) -> None:
        """Every `stuck_check` seconds of trying to fly somewhere, see whether it actually got
        anywhere. Covering less than `stuck_ratio` of the way it meant to means it is stuck."""
        cfg = AI["avoid"]
        self.watch_t += dt
        self.watch_want += want
        if self.watch_t < cfg["stuck_check"]:
            return
        e = self.e
        moved = dist(e.x, e.y, *self.watch_from)
        if self.watch_want > 8.0 and moved < self.watch_want * cfg["stuck_ratio"]:
            self.break_loose()
        else:
            self.stuck_count = 0
        self._reset_watch()

    def open_ways(self, n: int, reach: float) -> list[tuple[float, float, float]]:
        """How far this enemy could fly in each of `n` directions before touching a rock (up to
        `reach`): (ux, uy, free). A rock it is already pressed against only blocks the ways into it."""
        e = self.e
        f = self.stage.field
        r = e.body_r + 1.0
        ways = [(math.cos(k * math.tau / n), math.sin(k * math.tau / n)) for k in range(n)]
        free = [reach] * n
        if f is not None and len(f):
            pad = reach + r
            idx, dx, dy = f.near(e.x, e.y, pad, pad)
            for i, cx, cy in zip(idx, dx, dy):
                R = f.r[i] + r
                inside = cx * cx + cy * cy <= R * R
                for k, (ux, uy) in enumerate(ways):
                    b = cx * ux + cy * uy
                    if b <= 0:
                        continue                      # the rock is behind this way
                    if inside:
                        free[k] = 0.0
                        continue
                    across = cx * cx + cy * cy - b * b
                    if across >= R * R:
                        continue
                    free[k] = min(free[k], max(0.0, b - math.sqrt(R * R - across)))
        return [(ux, uy, fr) for (ux, uy), fr in zip(ways, free)]

    def break_loose(self) -> None:
        """Stuck: look round for the most open way out and fly straight along it for up to
        `unstick_time` seconds. Each time in a row it gets stuck, it picks more loosely among the
        open ways (up to `unstick_swing` degrees off), so it doesn't keep trying the same."""
        st = self.stage
        e = self.e
        cfg = AI["avoid"]
        rng = self.battle.rng
        ways = self.open_ways(int(cfg["probe_ways"]), float(cfg["probe"]))
        best = max(w[2] for w in ways)
        loose = min(3, self.stuck_count)
        # Among the ways nearly as open as the best, take one at random (more freely when stuck again).
        keep = 0.9 - 0.15 * loose
        pick = [w for w in ways if w[2] >= best * keep]
        ux, uy, free = rng.choice(pick)
        a = math.atan2(uy, ux) + rng.uniform(-1.0, 1.0) * math.radians(cfg["unstick_swing"]) * loose / 3
        self.escape_dir = (math.cos(a), math.sin(a))
        top = max(1.0, self.speed)
        self.escape = min(cfg["unstick_time"] * (1 + 0.5 * loose), max(0.2, (free - 2.0) / top))
        self.stuck_count += 1
        self.detour = None
        st.events.append(("stuck", e.kind))

    def _plan_detour(self) -> None:
        """After breaking loose, pick a point `detour` off to one side of the straight way to the
        goal, so it goes round the rocks instead of straight back in: the side it broke out towards
        (the other side if it got stuck again straight after), or whichever side has a clear path."""
        e = self.e
        st = self.stage
        cfg = AI["avoid"]
        if self.goal is None or cfg.get("detour", 0) <= 0:
            return
        ux, uy, d = unit(self.goal[0] - e.x, self.goal[1] - e.y)
        if d < 1.0:
            return
        px, py = -uy, ux                      # square on to the way to the goal
        lean = px * self.escape_dir[0] + py * self.escape_dir[1]
        if self.stuck_count > 1 and self.detour_side:
            first = -self.detour_side         # that way failed: try the other
        elif abs(lean) > 0.2:
            first = 1.0 if lean > 0 else -1.0
        else:
            first = self.battle.rng.choice((-1.0, 1.0))
        far = cfg["detour"] * (1 + 0.5 * min(3, self.stuck_count - 1))
        pad = e.body_r + cfg["margin"]
        ahead = min(d, far)
        best = None
        # Off to the side and a little on, straight off to the side, then off to the side and back.
        for k in (0.5, 0.0, -0.5):
            for side in (first, -first):
                x = e.x + px * side * far + ux * ahead * k
                y = e.y + py * side * far + uy * ahead * k
                x, y = self.battle.free_point(x, y, pad)
                hit = st.rock_hit(e.x, e.y, x, y, e.body_r + 1.0)
                clear = 1.0 if hit is None else dist(e.x, e.y, hit[0], hit[1]) / max(1.0, dist(e.x, e.y, x, y))
                if best is None or clear > best[0] + 1e-6:
                    best = (clear, side, x, y)
                if hit is None:
                    break
            if best[0] >= 1.0:
                break
        _, side, x, y = best
        self.detour_side = side
        self.detour = (x, y)
        self.detour_t = cfg["detour_time"]

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
        ship = self.stage.ship
        self.shoot_at(kind, ship.x, ship.y, ship.vx, ship.vy, lead, spread)

    def shoot_at(self, kind: str, x: float, y: float, vx: float, vy: float, lead: float, spread: float) -> None:
        st = self.stage
        e = self.e
        spec = ENEMY_WEAPONS["infantry_laser" if kind == "infantry" else "rapid_laser"]
        gx, gy = e.point(*ENEMY_GUN[e.kind])
        t = dist(gx, gy, x, y) / spec["speed"]
        ax, ay = x + vx * t * lead, y + vy * t * lead
        h = angle_to(ax - gx, ay - gy) + self.battle.rng.gauss(0.0, spread)
        fx, fy = forward_vector(h)
        st.enemy_shot(e, kind, (gx + fx * 100, gy + fy * 100))
        st.events.append(("enemy_fire", e.kind))

    def clear_shot(self) -> bool:
        """Is there a straight line from this enemy's gun to you, with no rock in it?"""
        ship = self.stage.ship
        return self.clear_shot_to(ship.x, ship.y)

    def clear_shot_to(self, x: float, y: float, short: float = 0.0) -> bool:
        """No rock between its gun and (x, y), stopping `short` of it (a drill sits on its rock)."""
        st = self.stage
        e = self.e
        gx, gy = e.point(*ENEMY_GUN.get(e.kind, (0.0, 0.0)))
        if short > 0:
            ux, uy, d = unit(x - gx, y - gy)
            x, y = x - ux * min(short, d), y - uy * min(short, d)
        return st.rock_hit(gx, gy, x, y, 1.5) is None

    def own_aim(self, dt: float) -> tuple[float, float, str]:
        """Where it goes on its own while the enemy doesn't know where you are."""
        e = self.e
        self.aim = self.task.tick(dt, e.x, e.y)
        return self.aim

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
        if not self.battle.knows:
            self._step_unaware(dt)
            return
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

    def _step_unaware(self, dt: float) -> None:
        """Not knowing where you are: fly with the squad (or alone) and shoot any drill it raids."""
        e = self.e
        if self.squad is not None:
            x, y, kind = self.squad.aim
        else:
            x, y, kind = self.own_aim(dt)
            if kind == "raid":
                ux, uy, d = unit(e.x - x, e.y - y)
                stand = self.battle.hunt.spec["raid_standoff"]
                self.goal = self.battle.free_point(x + ux * stand, y + uy * stand, e.body_r + AI["avoid"]["margin"])
            else:
                self.goal = (x, y)
        self.fly(dt)
        in_range = kind == "raid" and dist(e.x, e.y, x, y) < self.cfg["fire_range"]
        if in_range:
            self.face(x, y)
        else:
            self.face_travel()
        self.fire_in -= dt
        if self.fire_in > 0:
            return
        if not in_range or not self.clear_shot_to(x, y, short=14.0):
            self.fire_in = 0.25
            return
        self.shoot_at("infantry", x, y, 0.0, 0.0, 0.0, self.cfg["spread"])
        self.fire_in = self.every * self.battle.rng.uniform(0.8, 1.25)


class GuardBrain(Brain):
    """Walls off the squad it guards so the infantry can shoot over it. It only rams you once that
    squad is down to a couple of ships (or it has none to guard), aiming right up to the last moment."""

    kind = "guard"

    def __init__(self, battle: "Battle", e: Enemy):
        super().__init__(battle, e)
        self.spec = ENEMIES["guard"]
        self.state = "wall"
        self.t = 0.0
        self.plan_in = 0.0
        self.cooldown = battle.rng.uniform(0.5, 1.5)
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
        if self.cooldown > 0 or not st.ship_visible or not self.battle.knows:
            return False
        d = dist(e.x, e.y, ship.x, ship.y)
        if d > cfg["ram_range"]:
            return False
        sq = self.guarding
        if sq is None or not sq.members:
            if d > cfg["alone_ram"]:
                return False
        elif len(sq.members) > cfg["ram_when_left"]:
            return False                   # the squad can still fight: hold the wall
        return st.rock_hit(e.x, e.y, ship.x, ship.y, 4.0) is None

    def plan_wall(self) -> None:
        st = self.stage
        e = self.e
        cfg = self.cfg
        ship = st.ship
        sq = self.guarding
        knows = self.battle.knows
        if sq is None or not sq.members:
            if not knows:
                # Nothing to guard and no idea where you are: go where it is sent on its own.
                x, y, kind = self.aim or (e.x, e.y, "travel")
                if kind == "raid":
                    ux, uy, d = unit(e.x - x, e.y - y)
                    stand = self.battle.hunt.spec["raid_standoff"]
                    x, y = x + ux * stand, y + uy * stand
                self.goal = self.battle.free_point(x, y, e.body_r + AI["avoid"]["margin"])
                return
            # Nothing to guard: close in on you, ready to ram.
            ux, uy, d = unit(e.x - ship.x, e.y - ship.y)
            if d < 1e-6:
                ux, uy = 0.0, 1.0
            keep = cfg["alone_ram"] * 0.8
            self.goal = (ship.x + ux * keep, ship.y + uy * keep)
            return
        self.cruising = sq.cruising
        cx, cy = sq.centre()
        tx, ty = (ship.x, ship.y) if knows else sq.aim[:2]       # the wall faces the threat, or the way ahead
        ux, uy, d = unit(tx - cx, ty - cy)
        if d < 1e-6:
            ux, uy = 0.0, 1.0
        gap = min(cfg["wall_gap"], d * 0.5)
        # The guards share out the squad's width between them, each covering its own stretch.
        across = [(m.x - cx) * uy - (m.y - cy) * ux for m in sq.members]
        i, n = self.slot
        width = max(max(across) - min(across), n * cfg["spacing"])
        mid = (max(across) + min(across)) / 2
        side = mid + ((i + 0.5) / n - 0.5) * width
        x, y = cx + ux * gap + uy * side, cy + uy * gap - ux * side
        self.goal = self.battle.free_point(x, y, e.body_r + AI["avoid"]["margin"])

    def step(self, dt: float) -> None:
        st = self.stage
        e = self.e
        cfg = self.cfg
        spec = self.spec
        ship = st.ship
        self.cooldown = max(0.0, self.cooldown - dt)
        self.t += dt

        if self.state == "wall":
            knows = self.battle.knows
            if not knows and (self.guarding is None or not self.guarding.members):
                self.own_aim(dt)
            self.plan_in -= dt
            if self.plan_in <= 0:
                self.plan_in = cfg["replan"]
                self.plan_wall()
            self.fly(dt)
            if knows:
                self.face(ship.x, ship.y)
            else:
                self.face_travel()
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
                # The lane flashes along the path it is about to take.
                self.face(ship.x, ship.y)
                self.reach = dist(e.x, e.y, ship.x, ship.y) + 40
                self.lane = Lane("ram", e.x, e.y, e.heading, self.reach)
                st.lanes.append(self.lane)
                self._enter("warn")
        elif self.state == "warn":
            lock_at = spec["warn_time"] - cfg["lock_time"]
            if self.t < lock_at and st.ship_visible:
                # It keeps turning to follow you (at `track_turn`) until the lane locks.
                want = angle_to(ship.x - e.x, ship.y - e.y)
                turn = cfg["track_turn"] * dt
                e.heading = wrap_angle(e.heading + max(-turn, min(turn, wrap_angle(want - e.heading))))
                self.reach = dist(e.x, e.y, ship.x, ship.y) + 40
            if self.lane is not None:
                self.lane.x, self.lane.y = e.x, e.y
                self.lane.heading = e.heading
                self.lane.length = self.reach
                self.lane.locked = self.t >= lock_at
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
        if self.battle.knows:
            tx, ty, tvx, tvy, behind = ship.x, ship.y, ship.vx, ship.vy, ship.angle + 180.0
            visible = st.ship_visible
        else:
            tx, ty, kind = self.own_aim(dt)
            if kind != "raid":
                # No idea where you are and no drill to raid: go where it is sent.
                if self.state != "hold":
                    self.state = "hold"
                    self.t = 0.0
                self.goal = (tx, ty)
                self.fly(dt)
                self.face_travel()
                return
            tvx = tvy = 0.0
            behind = self.offset * 3.0          # raids come in from all sides
            visible = True
        if self.state == "hold":
            self.plan_in -= dt
            if self.plan_in <= 0 or self.goal is None:
                self.plan_in = cfg["replan"]
                fx, fy = forward_vector(behind + self.offset)
                self.goal = self.battle.free_point(tx + fx * cfg["hold_range"], ty + fy * cfg["hold_range"],
                                                   e.body_r + AI["avoid"]["margin"])
            there = self.fly(dt)
            if there or dist(e.x, e.y, *self.goal) < 30:
                self.rest -= dt
                self.face(tx, ty)
            else:
                self.face_travel()
            if self.rest <= 0 and visible:
                self._dive(tx, ty, tvx, tvy)
            return
        # Diving.
        there = self.fly(dt)
        self.face_travel()
        dx, dy = tx - e.x, ty - e.y
        hx, hy = forward_vector(e.heading)
        ahead = dx * hx + dy * hy > 0
        if (visible and self.fired < self.gun["burst"] and ahead
                and math.hypot(dx, dy) < cfg["fire_range"]):
            self.shot_in -= dt
            if self.shot_in <= 0:
                self.shoot_at("rapid", tx, ty, tvx, tvy, cfg["aim_lead"], cfg["spread"])
                self.fired += 1
                self.shot_in = self.gun["burst_gap"]
        if there or self.t > cfg["pass_time"]:
            self.state = "hold"
            self.t = 0.0
            self.plan_in = 0.0
            self.offset = self.battle.rng.uniform(-1.0, 1.0) * cfg["hold_spread"]
            self.rest = self.battle.rng.uniform(*self.cfg["rest"])

    def _dive(self, tx: float, ty: float, tvx: float, tvy: float) -> None:
        e = self.e
        cfg = self.cfg
        rng = self.battle.rng
        d = dist(e.x, e.y, tx, ty)
        lead = d / max(1.0, self.speed) * 0.5
        px, py = tx + tvx * lead, ty + tvy * lead
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
        # What it is doing: "hunt" (round you), or while the enemy doesn't know where you are,
        # "travel", "search", "raid" (round a drill) or "home".
        self.task = Task(battle)
        self.aim: tuple[float, float, str] = (ship.x, ship.y, "hunt")
        self.mode = "hunt"
        self.cruising = False
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
        hunt = self.battle.hunt
        if hunt is None or hunt.known:
            ship = self.battle.stage.ship
            self.aim = (ship.x, ship.y, "hunt")
        else:
            self.aim = self.task.tick(dt, *self.centre())
        self.plan_in -= dt
        if self.plan_in <= 0 or self.aim[2] != self.mode:
            self.plan_in = self.cfg["replan"] * self.battle.rng.uniform(0.85, 1.15)
            self.plan()

    def plan(self) -> None:
        cfg = self.cfg
        rng = self.battle.rng
        tx, ty, kind = self.aim
        cx, cy = self.centre()
        if kind != self.mode:
            self.mode = kind
            self.bearing = angle_to(cx - tx, cy - ty)
        margin = AI["avoid"]["margin"]
        if kind not in ("hunt", "raid"):
            # On the move: in formation, facing the way it is going.
            hunt = self.battle.hunt
            ux, uy, d = unit(tx - cx, ty - cy)
            lead = min(d, hunt.spec["march_lead"])
            face = angle_to(ux, uy) if d > 1e-6 else angle_to(tx - cx, ty - cy)
            ax, ay = cx + ux * lead, cy + uy * lead
            slots = self.slots(ax, ay, R=0.0, bearing=face + 180.0)
            rx, ry = right_vector(face)
            order = sorted(self.members, key=lambda m: (m.x - cx) * rx + (m.y - cy) * ry)
            self.cruising = d > hunt.spec["cruise_from"]
            for m, slot in zip(order, slots):
                m.brain.goal = self.battle.free_point(slot[0], slot[1], m.body_r + margin)
                m.brain.cruising = self.cruising
            return
        self.cruising = False
        for m in self.members:
            m.brain.cruising = False
        R = cfg["standoff"] if kind == "hunt" else self.battle.hunt.spec["raid_standoff"]
        if rng.random() < cfg.get("orbit_flip", 0.0):
            self.turn = -self.turn
        self.bearing = wrap_angle(self.bearing + self.turn * cfg["orbit"] * cfg["replan"])
        # Keep clear of the other squads round the same target.
        for other in self.battle.squads:
            if other is self or not other.members or other.mode != kind:
                continue
            if kind == "raid" and other.task.drill is not self.task.drill:
                continue
            need = math.degrees((self.width / 2 + other.width / 2 + cfg["squad_gap"]) / R)
            diff = wrap_angle(self.bearing - other.bearing)
            if abs(diff) < need:
                push = (need - abs(diff)) * 0.5
                self.bearing = wrap_angle(self.bearing + (push if diff > 0 else -push if diff < 0 else push * self.turn))
        slots = self.slots(tx, ty, R=R)
        # Fill the slots in order across the formation, so nobody crosses another's path.
        rx, ry = right_vector(self.bearing + 180.0)
        order = sorted(self.members, key=lambda m: (m.x - tx) * rx + (m.y - ty) * ry)
        for m, slot in zip(order, slots):
            m.brain.goal = self.battle.free_point(slot[0], slot[1], m.body_r + margin)

    def slots(self, sx: float, sy: float, R: float | None = None,
              bearing: float | None = None) -> list[tuple[float, float]]:
        """Formation points, left to right as seen from the squad looking at (sx, sy), `R` out
        from it at `bearing` (the squad's own, unless given)."""
        cfg = self.cfg
        n = len(self.members)
        R = cfg["standoff"] if R is None else R
        gap = cfg["spacing"]
        bearing = self.bearing if bearing is None else bearing
        if self.formation == "arc" and R > gap:
            step = math.degrees(gap / R)
            pts = []
            for i in range(n):
                fx, fy = forward_vector(bearing - (i - (n - 1) / 2) * step)
                pts.append((sx + fx * R, sy + fy * R))
            return pts
        fx, fy = forward_vector(bearing)
        ax, ay = sx + fx * R, sy + fy * R
        face = bearing + 180.0                      # the formation looks at you
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
        self.hunt = None            # a Hunt when enemies must find you; None and they always know

    def clear(self) -> None:
        self.squads = []
        self._flying = []

    @property
    def knows(self) -> bool:
        """Do the enemies know where you are?"""
        return self.hunt is None or self.hunt.known

    def heading_home(self, e: Enemy) -> bool:
        if self.knows or e.brain is None:
            return False
        sq = getattr(e.brain, "squad", None)
        if sq is not None:
            return sq.aim[2] == "home"
        if isinstance(e.brain, GuardBrain) and e.brain.guarding is not None and e.brain.guarding.members:
            return e.brain.guarding.aim[2] == "home"
        return e.brain.aim is not None and e.brain.aim[2] == "home"

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

    def free_point(self, x: float, y: float, r: float) -> tuple[float, float]:
        """The nearest point to (x, y) where a hull `r` across doesn't overlap a rock, so nobody
        is sent to a spot it can never reach."""
        f = self.stage.field
        if f is None or not len(f):
            return x, y
        for _ in range(3):
            idx, dx, dy = f.near(x, y, r, r)
            moved = False
            for i, ddx, ddy in zip(idx, dx, dy):
                d = math.hypot(ddx, ddy)
                over = f.r[i] + r - d
                if over > 0:
                    nx, ny = (ddx / d, ddy / d) if d > 1e-6 else (1.0, 0.0)
                    x, y = x - nx * over, y - ny * over
                    moved = True
            if not moved:
                break
        return x, y

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
        if self.hunt is not None:
            self.hunt.step(dt)
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

        self._assign_guards(flying)
        for sq in self.squads:
            sq.step(dt)
        for e in flying:
            if e.fade_in < 1.0:
                e.mx = e.my = 0.0
                continue
            e.brain.step(dt)
        self._dock(flying)

    def _dock(self, flying: list[Enemy]) -> None:
        """Ships that gave up the search and reached the mothership go back inside."""
        hunt = self.hunt
        if hunt is None or hunt.known:
            return
        home = hunt.home()
        if home is None:
            return
        for e in flying:
            if not e.alive or not self.heading_home(e):
                continue
            hx, hy = hunt.near_copy(home, (e.x, e.y))
            if dist(e.x, e.y, hx, hy) <= hunt.spec["dock"]:
                e.alive = False
                if isinstance(e.brain, GuardBrain):
                    e.brain._drop_lane()
                self.stage.events.append(("docked", e.kind))

    def _assign_guards(self, flying: list[Enemy]) -> None:
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
        for members in by_squad.values():
            # Order the wall across the line to you (or the way ahead), so guards don't swap sides.
            sq = members[0].brain.guarding
            cx, cy = sq.centre()
            ux, uy, _ = unit(sq.aim[0] - cx, sq.aim[1] - cy)
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
