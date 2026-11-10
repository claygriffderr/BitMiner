"""Explosive mines and sentries in Secure the Base. No graphics.

Mines: hold G to lay the mines you carry just behind your ship, one after another (hold still
for a pile, keep flying for a line). A mine arms after a moment, and goes off only when an enemy
flies right over it: every enemy in its blast takes damage that falls off evenly from the middle
to the edge. Your mines never hurt you, your drills or your sentries.

Sentries: press R to place the next sentry you carry where your ship is (inside your collector ring,
R mounts it on the ring instead: see `haul.py`). It never moves, turns
its turret toward the nearest enemy it can see in range and fires its own shots (diamond pellets,
ring-headed sniper rounds or darker missiles). Enemies can damage and destroy it.

Numbers come from the `mines` and `sentries` blocks of `data/combat.json`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..flight import angle_to, forward_vector, wrap_angle
from .specs import MINES, SENTRIES
from .stage import Anim, Enemy, Structure, dist

RETARGET = 0.25            # seconds between a sentry's looks round for the nearest enemy
TURRET_REACH = 7.0         # where a sentry's shots leave its turret, out from its centre


@dataclass
class Mine:
    x: float
    y: float
    uid: int = 0
    age: float = 0.0
    state: str = "laid"          # laid (not armed yet), armed, triggered
    fuse: float = 0.0
    clock: float = 0.0
    gone: bool = False


@dataclass
class Sentry(Structure):
    """A sentry: a Structure (enemies shoot it like a drill) with a turret."""
    gun: str = "auto"            # auto, sniper or missile
    tier: int = 1
    angle: float = 0.0           # where the turret points (heading, degrees)
    cool: float = 0.0            # seconds until it can fire again
    look: float = 0.0            # seconds until it looks for a new target
    target: Enemy | None = None
    salvo: int = 0               # missile sentry: missiles left in this salvo
    fired: float = 0.0           # seconds since it last fired, for the muzzle light
    loaded: int = 4              # missile sentry: pods showing loaded (art)


def sentry_spec(gun: str) -> dict:
    return SENTRIES[gun]


class Defenses:
    def __init__(self, game) -> None:
        self.game = game
        self.mines_carried = 0
        self.carried: list[tuple[str, int]] = []      # sentries you carry, (gun, tier), placed in order
        self.sentries: list[Sentry] = []
        self.lay_wait = 0.0

    @property
    def stage(self):
        return self.game.stage

    @property
    def mines(self) -> list[Mine]:
        return self.stage.mines

    # ------------------------------------------------------------ mines

    def lay_mine(self) -> Mine | None:
        """Drop a mine behind your ship, if you carry one and the last one has had time to fall."""
        st = self.stage
        if self.mines_carried <= 0 or self.lay_wait > 0 or st.ship_down:
            return None
        ship = st.ship
        fx, fy = forward_vector(ship.angle)
        back = float(MINES["behind"])
        spread = float(MINES["pile_spread"])
        x = ship.x - fx * back + st.rng.uniform(-spread, spread)
        y = ship.y - fy * back + st.rng.uniform(-spread, spread)
        m = Mine(x, y, uid=st.uid())
        self.mines.append(m)
        self.mines_carried -= 1
        self.lay_wait = float(MINES["lay_gap"])
        st.events.append(("mine_laid", m.uid))
        return m

    def _step_mines(self, dt: float) -> None:
        st = self.stage
        reach = float(MINES["trigger"])
        for m in self.mines:
            m.age += dt
            m.clock += dt
            if m.state == "laid" and m.age >= float(MINES["arm_time"]):
                m.state = "armed"
            elif m.state == "armed":
                wide = reach + 60.0          # further than any hull that could set it off
                for e in st.enemies:
                    dx, dy = e.x - m.x, e.y - m.y
                    if dx > wide or dx < -wide or dy > wide or dy < -wide:
                        continue
                    if e.targetable and e.kind != "mothership" and math.hypot(dx, dy) <= e.body_r * 0.6 + reach:
                        m.state = "triggered"
                        m.fuse = float(MINES["fuse"])
                        m.clock = 0.0
                        st.events.append(("mine_triggered", m.uid))
                        break
            elif m.state == "triggered":
                m.fuse -= dt
                if m.fuse <= 0:
                    self._blast(m)
        st.mines = [m for m in self.mines if not m.gone]

    def _blast(self, m: Mine) -> None:
        """Every enemy in reach takes damage falling off evenly to the edge. Only enemies."""
        st = self.stage
        m.gone = True
        R = float(MINES["blast_radius"])
        frames, fps = int(MINES["blast_frames"]), float(MINES["blast_fps"])
        st.anims.append(Anim("mine_blast", (int(R),), frames, fps, m.x, m.y))
        st.sparks.burst("ion_spark", m.x, m.y, 0.0, math.pi, 26, (60, 200), (0.2, 0.5))
        st.smoke.burst("smoke", m.x, m.y, 0.0, math.pi, 10, (10, 50), (0.6, 1.2))
        st.kick += 0.35
        st.events.append(("mine_blast", m.uid))
        for e in list(st.enemies):
            if not e.targetable:
                continue
            d = max(0.0, dist(m.x, m.y, e.x, e.y) - e.body_r * 0.5)
            if d >= R:
                continue
            falloff = 1.0 - d / R
            a = math.atan2(e.y - m.y, e.x - m.x) if d > 0.01 else 0.0
            push = float(MINES["push"]) * falloff
            st.push_enemy(e, math.cos(a) * push, math.sin(a) * push)
            st.damage_enemy(e, float(MINES["damage"]) * falloff, m.x, m.y, source="mine")

    # ------------------------------------------------------------ sentries

    def sentry_room(self, x: float, y: float) -> str:
        """Why a sentry can't go at (x, y), or "" if it can."""
        st = self.stage
        clear = float(SENTRIES["clearance"])
        r = float(SENTRIES["radius"])
        if sum(1 for s in self.sentries if s.host is None) >= int(SENTRIES["max_out"]):
            return "MAX"
        f = st.field
        if f is not None and len(f):
            idx, dx, dy = f.near(x, y, r + 40, r + 40)
            for i, ddx, ddy in zip(idx, dx, dy):
                if math.hypot(ddx, ddy) < f.r[i] + r + 2:
                    return "ROCK"
        for t in st.structures:
            if not t.alive:
                continue
            if t.hoop > 0:
                # The collector ring: only its band (and the mounts on it) is in the way.
                if abs(dist(x, y, t.x, t.y) - t.radius) < t.hoop + r + clear:
                    return "CROWDED"
                continue
            gap = t.radius + r + clear if t.kind != "drill" else r + clear
            if dist(x, y, t.x, t.y) < gap:
                return "CROWDED"
        return ""

    def place_sentry(self) -> Sentry | None:
        """Set down the next sentry you carry where your ship is."""
        st = self.stage
        if not self.carried or st.ship_down:
            return None
        ship = st.ship
        why = self.sentry_room(ship.x, ship.y)
        if why:
            st.events.append(("no_room", "sentry", why))
            return None
        gun, tier = self.carried.pop(0)
        health = float(sentry_spec(gun)["health"][tier - 1])
        s = Sentry("sentry", ship.x, ship.y, radius=float(SENTRIES["radius"]), health=health, max_health=health,
                   uid=st.uid(), gun=gun, tier=tier, angle=ship.angle)
        self.sentries.append(s)
        st.structures.append(s)
        st.events.append(("sentry_set", gun, tier, s.uid))
        return s

    def _pick(self, s: Sentry, spec: dict) -> Enemy | None:
        st = self.stage
        reach = float(spec["range"])
        best, bd = None, math.inf
        wide = reach + 80.0                  # the mothership's hull counts from its edge
        for e in st.enemies:
            dx, dy = e.x - s.x, e.y - s.y
            if dx > wide or dx < -wide or dy > wide or dy < -wide or not e.targetable:
                continue
            d = math.hypot(dx, dy)
            if d > reach + (e.body_r if e.kind == "mothership" else 0.0) or d >= bd:
                continue
            if st.rock_hit(s.x, s.y, e.x, e.y) is not None:
                continue
            best, bd = e, d
        return best

    def _step_sentry(self, s: Sentry, dt: float) -> None:
        st = self.stage
        spec = sentry_spec(s.gun)
        # Like your own guns: while it is firing, the wait for the next shot carries its overshoot
        # over, so it fires at its set rate at any frame rate.
        waiting = s.cool > 0
        s.cool -= dt
        if not waiting:
            s.cool = max(0.0, s.cool)        # time spent ready with nothing to shoot isn't saved up
        s.look -= dt
        s.fired += dt
        t = s.target
        reach = float(spec["range"])
        # A target that dies or gets away is replaced at once; with nothing to shoot it looks
        # round every RETARGET seconds, not every step.
        lost = t is not None and (not t.targetable or dist(s.x, s.y, t.x, t.y) > reach * 1.1)
        if lost or s.look <= 0:
            s.target = t = self._pick(s, spec)
            s.look = RETARGET
        if t is None:
            s.cool = max(0.0, s.cool)
            return
        # Lead the target by its speed (missiles steer themselves).
        tx, ty = t.x, t.y
        if s.gun != "missile":
            d = dist(s.x, s.y, tx, ty)
            lead = d / float(spec["speed"])
            tx += (t.mx + t.vx) * lead
            ty += (t.my + t.vy) * lead
        want = angle_to(tx - s.x, ty - s.y)
        diff = wrap_angle(want - s.angle)
        turn = float(spec["turn_rate"]) * dt
        s.angle = wrap_angle(s.angle + max(-turn, min(turn, diff)))
        if abs(wrap_angle(want - s.angle)) > float(spec["aim_cone"]):
            s.cool = max(0.0, s.cool)
            return
        if s.cool > 0:
            return
        late = min(dt, -s.cool)
        fx, fy = forward_vector(s.angle)
        mx, my = s.x + fx * TURRET_REACH, s.y + fy * TURRET_REACH
        if s.gun == "missile":
            if s.salvo <= 0:
                s.salvo = int(spec["salvo"])
            side = 1 if s.salvo % 2 else -1
            st.sentry_missile(mx, my, s.angle + side * 40, t, spec)
            s.salvo -= 1
            s.loaded = s.salvo
            s.cool += float(spec["gap"]) if s.salvo > 0 else float(spec["reload"])
        else:
            st.sentry_shot(s.gun, mx, my, s.angle, spec, lead=late)
            s.cool += 1.0 / float(spec["fire_rate"])
        s.fired = 0.0

    def _step_sentries(self, dt: float) -> None:
        for s in self.sentries:
            if s.alive:
                self._step_sentry(s, dt)
            if s.gun == "missile" and s.salvo <= 0 and s.cool <= 0:
                s.loaded = int(sentry_spec("missile")["salvo"])
        self.sentries = [s for s in self.sentries if s.alive]

    # ------------------------------------------------------------ the update

    def step(self, dt: float, laying: bool) -> None:
        self.lay_wait = max(0.0, self.lay_wait - dt)
        if laying:
            self.lay_mine()
        self._step_mines(dt)
        self._step_sentries(dt)

    @property
    def sentries_carried(self) -> int:
        return len(self.carried)

