"""Hauling in Secure the Base (sprint 10): the lasso, the collector ring and drills that float free.
No graphics: `graphics/combat_draw.py` draws it from what's here.

- Lasso (3 levels from the station, Tools page): Q grabs the nearest asteroid in reach on a force
  beam of fixed length from the back of your ship, if your level can tow one that big; Q again lets
  go. The rock can't get nearer or further, so it never hits you, and it keeps its momentum when
  you let go. While it's fast it hurts any enemy it hits.
- Collector ring (from the station): hold T to see where it would go and let go of T to place it
  round your ship. It catches up to 4 asteroids that drift (or are towed) into it and holds them
  still; drills on them sell their ore by themselves whenever they fill up. Press R inside it to
  mount a sentry on it: mounted sentries share the ring's health and break with it. Enemies can't
  fly into it (the stage keeps their hulls outside its band); they shoot it from outside.
- Drills aren't used up any more: when a worked-out asteroid crumbles they float free, and one you
  fly near flies in to your ship and goes back in your hold.

Numbers live in the `haul` block of `data/combat.json`, the lasso's levels and the ring's price in
`data/shop.json`, and the TOW WEIGHT and THROW POWER sliders. The ring's size comes from its art.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from art import haul as ART

from ..field import wrap_delta
from ..flight import forward_vector
from .defenses import Sentry
from .specs import DRILLS, HAUL, SENTRIES, SHOP
from .stage import Anim, Structure, dist

# The ring's shape, from its art.
RING_RADIUS = (ART.R_IN + ART.R_OUT) / 2      # the middle of its band
RING_HOOP = (ART.R_OUT - ART.R_IN) / 2        # half the band's width: shots within this of RING_RADIUS hit it
INNER = float(ART.R_IN)                        # inside the band: where R mounts a sentry
OUTER = float(ART.PAD_R + ART.PAD_HALF)        # the outside edge of its mounts
FIELD_R = float(ART.FIELD_R)                   # an asteroid mostly inside this is caught
MOUNT_R = float(ART.PAD_R)
NODE_R = float(ART.NODE_R)
SLOT_R = float(ART.SLOT_R)


def _game_dir(screen_deg: float) -> tuple[float, float]:
    """A direction from the art (screen degrees, y down) in game axes (y up)."""
    a = math.radians(screen_deg)
    return math.cos(a), -math.sin(a)


MOUNT_DIRS = tuple(_game_dir(a) for a in ART.MOUNT_ANGLES)     # top, right, bottom, left
NODE_DIRS = tuple(_game_dir(a) for a in ART.NODE_ANGLES)       # the diagonals; rocks settle on these too


@dataclass
class LooseDrill:
    """A drill floating free after its asteroid crumbled, until you fly near it and it flies in."""
    x: float
    y: float
    vx: float
    vy: float
    angle: float                 # which way it points (heading, degrees); it turns slowly
    spin: float                  # degrees a second
    uid: int = 0
    clock: float = 0.0
    homing: bool = False         # near enough to your ship: flying in to it


@dataclass
class CollectorRing(Structure):
    """The collector ring: a Structure (enemy shots hit its band) that holds asteroids."""
    slots: list = field(default_factory=lambda: [-1] * int(HAUL["slots"]))     # asteroid held in each spot
    mounts: list = field(default_factory=lambda: [None] * len(MOUNT_DIRS))     # sentry on each mount
    lit: list = field(default_factory=lambda: [0.0] * len(NODE_DIRS))         # seconds each node stays gold
    pulses: list = field(default_factory=list)       # gold flying to a node: [dx, dy, node, t, credits]

    def slot_point(self, k: int) -> tuple[float, float]:
        dx, dy = NODE_DIRS[k % len(NODE_DIRS)]
        return self.x + dx * SLOT_R, self.y + dy * SLOT_R

    def node_point(self, k: int) -> tuple[float, float]:
        dx, dy = NODE_DIRS[k]
        return self.x + dx * NODE_R, self.y + dy * NODE_R

    def mount_point(self, k: int) -> tuple[float, float]:
        dx, dy = MOUNT_DIRS[k]
        return self.x + dx * MOUNT_R, self.y + dy * MOUNT_R

    @property
    def held(self) -> int:
        return sum(1 for i in self.slots if i >= 0)


def lasso_spec() -> dict:
    return SHOP["upgrades"]["lasso"]


def ring_wall() -> float:
    """How far from the ring's centre enemy hulls are kept (0: they can fly in)."""
    return RING_RADIUS + RING_HOOP + float(HAUL["keep_out_pad"]) if HAUL["keep_out"] else 0.0


class Haul:
    def __init__(self, game) -> None:
        self.game = game
        self.rock = -1               # the asteroid on the lasso, or -1
        self.latch = 1.0             # 0 to 1 while the grip closes round a rock you just grabbed
        self.length = 0.0            # the beam's length now: it eases to its set length after a grab
        self.flying: set[int] = set()            # asteroids you let go of that are still fast enough to hurt
        self.cool: dict[tuple[int, int], float] = {}   # (asteroid, enemy) -> seconds before it can hurt it again
        self.ring: CollectorRing | None = None   # your ring, once placed
        self.rings_carried = 0
        self.placing = False         # T held: the ring's outline shows where it would go
        self.room = ""               # why the ring can't go here ("" if it can), while placing
        self._t_was = False

    @property
    def stage(self):
        return self.game.stage

    # ------------------------------------------------------------ the lasso

    @property
    def level(self) -> int:
        return self.game.gear.level("lasso")

    @staticmethod
    def max_size(level: int) -> int:
        """The biggest asteroid (diameter) a lasso of this level tows; 0 with no lasso."""
        sizes = lasso_spec()["max_size"]
        return 0 if level <= 0 else int(sizes[min(level, len(sizes)) - 1])

    @staticmethod
    def level_for(size: int) -> int | None:
        """The lowest lasso level that tows an asteroid this big, or None if none does."""
        for lv, most in enumerate(lasso_spec()["max_size"], start=1):
            if size <= int(most):
                return lv
        return None

    def tail(self) -> tuple[float, float]:
        """Where the beam leaves your ship."""
        ship = self.stage.ship
        fx, fy = forward_vector(ship.angle)
        back = float(HAUL["tail"])
        return ship.x - fx * back, ship.y - fy * back

    def set_length(self, i: int) -> float:
        """How far the beam holds asteroid i's centre from your ship's tail."""
        return float(HAUL["beam"]) + float(self.stage.field.size[i]) / 2

    def rock_pos(self, i: int) -> tuple[float, float]:
        """Asteroid i's centre, in the copy of the map nearest your ship."""
        st = self.stage
        f = st.field
        ship = st.ship
        return (ship.x + wrap_delta(float(f.x[i]) - ship.x, f.width),
                ship.y + wrap_delta(float(f.y[i]) - ship.y, f.height))

    def target(self) -> tuple[int, bool] | None:
        """The asteroid Q would grab now (the nearest one in reach), and whether your lasso can tow it."""
        st = self.stage
        if st.ship_down or self.level <= 0 or self.rock >= 0:
            return None
        f = st.field
        ship = st.ship
        reach = float(HAUL["grab_reach"])
        idx, dx, dy = f.near(ship.x, ship.y, reach + 50, reach + 50)
        best, bd = None, math.inf
        for i, ddx, ddy in zip(idx.tolist(), dx, dy):
            if f.gone[i]:
                continue
            gap = math.hypot(ddx, ddy) - float(f.size[i]) / 2
            if gap <= reach and gap < bd:
                best, bd = i, gap
        if best is None:
            return None
        return best, int(f.size[best]) <= self.max_size(self.level)

    def toggle(self) -> None:
        """Q: grab the asteroid in reach, or let go of the one you're towing."""
        st = self.stage
        if self.rock >= 0:
            self.let_go()
            return
        if st.ship_down:
            return
        if self.level <= 0:
            st.events.append(("lasso", "none"))
            return
        t = self.target()
        if t is None:
            st.events.append(("lasso", "nothing"))
            return
        i, ok = t
        f = st.field
        if not ok:
            st.events.append(("lasso", "heavy", self.level_for(int(f.size[i])) or 3, int(f.size[i])))
            return
        self.rock = i
        self.latch = 0.0
        ax, ay = self.tail()
        rx, ry = self.rock_pos(i)
        self.length = max(1.0, math.hypot(rx - ax, ry - ay))
        self.flying.discard(i)
        ring = self.ring
        if ring is not None and i in ring.slots:
            ring.slots[ring.slots.index(i)] = -1       # pulled out of the ring
        st.events.append(("lasso", "grab", i, int(f.size[i])))

    def let_go(self, quiet: bool = False) -> None:
        i = self.rock
        if i < 0:
            return
        self.rock = -1
        st = self.stage
        f = st.field
        if f.gone[i]:
            return
        speed = math.hypot(float(f.vx[i]), float(f.vy[i]))
        if speed >= float(HAUL["throw_min_speed"]):
            self.flying.add(i)
        if not quiet:
            st.events.append(("lasso", "let_go", i, round(speed, 1)))

    def constrain(self, h: float) -> None:
        """Hold the towed asteroid at the beam's length from your ship's tail, trading momentum
        between the two by weight (the rock's weighted by TOW WEIGHT). Runs every physics step."""
        i = self.rock
        if i < 0:
            return
        st = self.stage
        f = st.field
        ship = st.ship
        if f.gone[i] or st.ship_down:
            self.let_go(quiet=True)
            return
        want = self.set_length(i)
        rate = abs(want - self.length) / max(1e-6, float(HAUL["latch_time"])) + 30.0
        if self.length < want:
            self.length = min(want, self.length + rate * h)
        else:
            self.length = max(want, self.length - rate * h)
        ax, ay = self.tail()
        dx = wrap_delta(float(f.x[i]) - ax, f.width)
        dy = wrap_delta(float(f.y[i]) - ay, f.height)
        d = math.hypot(dx, dy)
        if d < 1e-6:
            dx, dy, d = 0.0, -1.0, 1.0
        nx, ny = dx / d, dy / d
        inv_s = 1.0 / max(0.05, st.ship_mass)
        inv_r = 1.0 / max(1e-4, float(f.m[i]) * max(0.01, self.game.tuning.tow_weight))
        w = inv_s + inv_r
        err = d - self.length
        # Positions: both move along the beam until it is exactly the right length.
        ship.x = (ship.x + nx * err * inv_s / w) % f.width
        ship.y = (ship.y + ny * err * inv_s / w) % f.height
        ship.ux += nx * err * inv_s / w
        ship.uy += ny * err * inv_s / w
        f.x[i] = (float(f.x[i]) - nx * err * inv_r / w) % f.width
        f.y[i] = (float(f.y[i]) - ny * err * inv_r / w) % f.height
        # Speeds: no closing or opening along the beam.
        rel = (float(f.vx[i]) - ship.vx) * nx + (float(f.vy[i]) - ship.vy) * ny
        j = -rel / w
        f.vx[i] += j * inv_r * nx
        f.vy[i] += j * inv_r * ny
        ship.vx -= j * inv_s * nx
        ship.vy -= j * inv_s * ny
        f._refile(i)

    def fast_rocks(self) -> list[tuple[int, float]]:
        """Asteroids on or off the lasso fast enough to hurt, with how far past that speed (0 to 1)."""
        f = self.stage.field
        low = float(HAUL["throw_min_speed"])
        out = []
        for i in sorted(self.flying | ({self.rock} if self.rock >= 0 else set())):
            if f.gone[i]:
                continue
            speed = math.hypot(float(f.vx[i]), float(f.vy[i]))
            if speed >= low:
                out.append((i, min(1.0, (speed - low) / low)))
        return out

    def _hits(self, dt: float) -> None:
        """Fast asteroids from the lasso hurt the enemies they hit."""
        st = self.stage
        f = st.field
        for key in list(self.cool):
            self.cool[key] -= dt
            if self.cool[key] <= 0:
                del self.cool[key]
        for i in list(self.flying):
            if f.gone[i] or math.hypot(float(f.vx[i]), float(f.vy[i])) < float(HAUL["throw_min_speed"]) * 0.5:
                self.flying.discard(i)
        rocks = list(self.flying) + ([self.rock] if self.rock >= 0 else [])
        if not rocks:
            return
        low = float(HAUL["throw_min_speed"])
        power = float(HAUL["throw_damage"]) * max(0.0, self.game.tuning.throw_power)
        for i in rocks:
            rx, ry = self.rock_pos(i)
            r = float(f.r[i])
            m = float(f.m[i])
            for e in st.enemies:
                if not e.targetable or (i, e.uid) in self.cool:
                    continue
                d = math.hypot(e.x - rx, e.y - ry)
                if d > r + e.body_r:
                    continue
                nx, ny = ((e.x - rx) / d, (e.y - ry) / d) if d > 1e-6 else (1.0, 0.0)
                closing = (float(f.vx[i]) - e.vx - e.mx) * nx + (float(f.vy[i]) - e.vy - e.my) * ny
                if closing < low:
                    continue
                self.cool[(i, e.uid)] = float(HAUL["hit_cooldown"])
                dmg = power * m * (closing - low)
                if e.kind == "mothership":
                    dmg = min(dmg, float(HAUL["mothership_cap"]))
                cx, cy = rx + nx * r, ry + ny * r
                # The rock gives up some of its speed, and that push goes into the enemy.
                slow = float(HAUL["hit_slow"])
                lost = closing * slow
                f.vx[i] -= nx * lost
                f.vy[i] -= ny * lost
                shove = min(m * lost, 220.0 * e.mass)
                st.push_enemy(e, nx * shove, ny * shove)
                st.sparks.burst("steel", cx, cy, math.atan2(-ny, -nx), 1.0, 8, (30, 110), (0.15, 0.4))
                st.sparks.burst("alien_debris", cx, cy, math.atan2(ny, nx), 1.0, 5, (20, 80), (0.2, 0.5))
                st.smoke.burst("dust", cx, cy, math.atan2(-ny, -nx), 1.0, 5, (10, 50), (0.3, 0.7))
                st.anims.append(Anim("flare", ("player",), 2, 20, cx, cy))
                st.kick += min(0.5, 0.1 + dmg / 200)
                st.events.append(("rock_hit", e.kind, round(dmg, 1), i))
                if dmg > 0:
                    st.damage_enemy(e, dmg, cx, cy, source="rock")

    # ------------------------------------------------------------ the collector ring

    def has_ring(self) -> bool:
        return self.ring is not None and self.ring.alive

    def ring_room(self, x: float, y: float) -> str:
        """Why the ring can't go round (x, y), or "" if it can: ROCK (an asteroid across its band or
        more than it holds inside), BASE (too near home base), CROWDED (a sentry in the way) or ENEMY
        (an enemy where the ring would keep it out)."""
        st = self.stage
        f = st.field
        base = self.game.base
        if dist(x, y, base.x, base.y) < float(HAUL["clear_of_base"]):
            return "BASE"
        reach = OUTER + 60
        idx, dx, dy = f.near(x, y, reach, reach)
        inside = 0
        for i, ddx, ddy in zip(idx.tolist(), dx, dy):
            if f.gone[i]:
                continue
            d = math.hypot(ddx, ddy)
            r = float(f.size[i]) / 2
            if d - r >= OUTER:
                continue
            if d + r <= FIELD_R:
                inside += 1
                continue
            return "ROCK"
        if inside > int(HAUL["slots"]):
            return "ROCK"
        for t in st.structures:
            if not t.alive or t.kind == "drill":
                continue
            if dist(x, y, t.x, t.y) < OUTER + t.radius:
                return "CROWDED"
        wall = ring_wall()
        if wall > 0:
            for e in st.enemies:
                if e.alive and dist(x, y, e.x, e.y) < wall + e.body_r:
                    return "ENEMY"
        return ""

    def place_ring(self) -> CollectorRing | None:
        """Set the ring you carry down round your ship, if there's room."""
        st = self.stage
        if self.rings_carried <= 0 or st.ship_down:
            return None
        ship = st.ship
        why = self.ring_room(ship.x, ship.y)
        if why:
            st.events.append(("no_room", "ring", why))
            return None
        health = float(HAUL["health"])
        ring = CollectorRing("ring", ship.x, ship.y, radius=RING_RADIUS, health=health, max_health=health,
                             uid=st.uid(), hoop=RING_HOOP, wall=ring_wall())
        st.structures.append(ring)
        self.ring = ring
        self.rings_carried -= 1
        st.events.append(("ring_set", ring.uid))
        return ring

    def repair_ring(self, share: float) -> None:
        ring = self.ring
        if ring is not None and ring.alive:
            ring.health = min(ring.max_health, ring.health + ring.max_health * share)

    def mount_sentry(self) -> Sentry | None:
        """R inside the ring: the next sentry you carry goes on the next free mount. None when you're
        not inside your ring or its mounts are full (then R places a sentry the usual way)."""
        st = self.stage
        g = self.game
        d = g.defenses
        ring = self.ring
        if not self.has_ring() or not d.carried or st.ship_down:
            return None
        ship = st.ship
        if dist(ship.x, ship.y, ring.x, ring.y) > INNER:
            return None
        free = [k for k, s in enumerate(ring.mounts) if s is None or not s.alive]
        if not free:
            return None
        k = free[0]
        gun, tier = d.carried.pop(0)
        x, y = ring.mount_point(k)
        s = Sentry("sentry", x, y, radius=float(SENTRIES["radius"]), health=1.0, max_health=1.0, uid=st.uid(),
                   gun=gun, tier=tier, angle=ship.angle, host=ring)
        ring.mounts[k] = s
        d.sentries.append(s)
        st.structures.append(s)
        st.events.append(("sentry_set", gun, tier, s.uid, "ring"))
        return s

    def ring_inside(self) -> bool:
        """Your ship is inside your ring."""
        ship = self.stage.ship
        return self.has_ring() and dist(ship.x, ship.y, self.ring.x, self.ring.y) <= INNER

    def free_mount(self) -> bool:
        return self.has_ring() and any(s is None or not s.alive for s in self.ring.mounts)

    def _ring_lost(self, ring: CollectorRing) -> None:
        """It broke: its mounted sentries go with it, and what it held drifts where it is."""
        st = self.stage
        for k, s in enumerate(ring.mounts):
            if s is not None and s.alive:
                s.alive = False
                st.events.append(("struct_lost", "sentry", s.uid))
                st.anims.append(Anim("explosion", ("player", 33, k % 3), 6, 14, s.x, s.y, delay=0.1 * k))
            ring.mounts[k] = None
        g = self.game
        for p in ring.pulses:          # gold already on its way still pays
            g.credits += int(p[4])
        ring.pulses.clear()
        ring.slots = [-1] * len(ring.slots)
        self.ring = None

    def _step_ring(self, dt: float) -> None:
        ring = self.ring
        if ring is None:
            return
        if not ring.alive:
            self._ring_lost(ring)
            return
        st = self.stage
        f = st.field
        g = self.game
        for k in range(len(ring.lit)):
            ring.lit[k] = max(0.0, ring.lit[k] - dt)
        # Catch loose asteroids that drift into the field.
        if -1 in ring.slots:
            idx, dx, dy = f.near(ring.x, ring.y, FIELD_R, FIELD_R)
            for i, ddx, ddy in zip(idx.tolist(), dx, dy):
                if f.gone[i] or i == self.rock or i in ring.slots or -1 not in ring.slots:
                    continue
                d = math.hypot(ddx, ddy)
                if d + float(f.size[i]) / 4 > FIELD_R:
                    continue
                free = [k for k, j in enumerate(ring.slots) if j < 0]
                k = min(free, key=lambda k: dist(ring.x + ddx, ring.y + ddy, *ring.slot_point(k)))
                ring.slots[k] = i
                self.flying.discard(i)
                st.events.append(("ring_caught", i, int(f.size[i])))
        # Ease each held asteroid to its spot and hold it there.
        ease = float(HAUL["ease"])
        top = float(HAUL["ease_speed"])
        for k, i in enumerate(ring.slots):
            if i < 0:
                continue
            if f.gone[i]:
                ring.slots[k] = -1
                continue
            sx, sy = ring.slot_point(k)
            rx, ry = self.rock_pos(i)
            ex, ey = sx - rx, sy - ry
            gap = math.hypot(ex, ey)
            if gap < 0.5:
                f.x[i] = sx % f.width
                f.y[i] = sy % f.height
                f.vx[i] = f.vy[i] = 0.0
            else:
                v = min(top, gap * ease)
                f.vx[i] = ex / gap * v
                f.vy[i] = ey / gap * v
            f._refile(i)
        # Drills on held asteroids sell their ore when they fill up (or their asteroid runs dry).
        price = float(DRILLS["credit_per_ore"])
        held = set(i for i in ring.slots if i >= 0)
        for d in g.drills:
            if not d.alive or d.rock not in held or d.hold <= 1e-6:
                continue
            pool = g.rocks.get(d.rock)
            dry = pool is not None and pool.left <= 1e-6
            if d.hold < d.hold_max - 1e-6 and not dry:
                continue
            credits = int(round(d.hold * price))
            d.hold = 0.0
            node = min(range(len(NODE_DIRS)), key=lambda n: dist(d.x, d.y, *ring.node_point(n)))
            ring.pulses.append([d.x - ring.x, d.y - ring.y, node, 0.0, credits])
            st.events.append(("ring_sell", d.uid, credits))
        keep = []
        span = float(HAUL["pulse_time"])
        for p in ring.pulses:
            p[3] += dt / span
            if p[3] >= 1.0:
                node = p[2]
                ring.lit[node] = float(HAUL["node_lit"])
                g.credits += int(p[4])
                nx, ny = ring.node_point(node)
                st.events.append(("ring_sale", int(p[4]), nx, ny))
            else:
                keep.append(p)
        ring.pulses = keep

    # ------------------------------------------------------------ drills floating free

    def float_free(self, d: Structure, rock_v: tuple[float, float]) -> LooseDrill:
        """A drill whose asteroid crumbled pops off it and floats free."""
        st = self.stage
        a = math.radians(d.side)
        pop = float(DRILLS["float_speed"])
        spin = st.rng.choice((-1.0, 1.0)) * st.rng.uniform(30.0, 60.0)
        ld = LooseDrill(d.x, d.y, rock_v[0] + math.sin(a) * pop, rock_v[1] + math.cos(a) * pop, d.side, spin,
                        uid=st.uid())
        st.loose.append(ld)
        st.events.append(("drill_loose", ld.uid))
        return ld

    def _step_loose(self, dt: float) -> None:
        st = self.stage
        g = self.game
        ship = st.ship
        keep = math.exp(-float(DRILLS["float_damper"]) * dt)
        reach = float(DRILLS["float_pickup"])
        grab = float(DRILLS["float_grab"])
        pull = float(DRILLS["float_pull"])
        out = []
        for ld in st.loose:
            ld.clock += dt
            ld.angle = (ld.angle + ld.spin * dt) % 360.0
            d = dist(ship.x, ship.y, ld.x, ld.y)
            # Within reach it flies in to your ship, through any asteroid in between (so one stuck
            # under a rock still comes), always a little quicker than you fly.
            ld.homing = not st.ship_down and (ld.homing or d <= reach)
            if ld.homing:
                move = (pull + math.hypot(ship.vx, ship.vy)) * dt
                if d > 1e-6:
                    k = min(1.0, move / d)
                    ld.vx, ld.vy = (ship.x - ld.x) / d * pull + ship.vx, (ship.y - ld.y) / d * pull + ship.vy
                    ld.x += (ship.x - ld.x) * k
                    ld.y += (ship.y - ld.y) * k
                d = dist(ship.x, ship.y, ld.x, ld.y)
            else:
                ld.x += ld.vx * dt
                ld.y += ld.vy * dt
                ld.vx *= keep
                ld.vy *= keep
            if ld.homing and d <= grab:
                g.drills_carried += 1
                st.anims.append(Anim("flare", ("player",), 2, 16, ld.x, ld.y))
                st.events.append(("drill_back", ld.uid))
                continue
            out.append(ld)
        st.loose = out

    # ------------------------------------------------------------ each step

    def step(self, dt: float, grab: bool, ring_key: bool) -> None:
        """After the physics: the Q press, the T key (held), throws hitting enemies, the ring and
        loose drills."""
        st = self.stage
        if self.rock >= 0:
            self.latch = min(1.0, self.latch + dt / max(1e-6, float(HAUL["latch_time"])))
        if grab:
            self.toggle()
        # T: hold to see where the ring would go, let go to place it.
        pressed = ring_key and not self._t_was
        self._t_was = ring_key
        if pressed and self.rings_carried <= 0:
            st.events.append(("ring_none", "placed" if self.has_ring() else "none"))
        if self.rings_carried > 0 and not st.ship_down:
            if ring_key:
                self.placing = True
                self.room = self.ring_room(st.ship.x, st.ship.y)
            elif self.placing:
                self.placing = False
                self.place_ring()
        else:
            self.placing = False
        self._hits(dt)
        self._step_ring(dt)
        self._step_loose(dt)

    def log(self) -> dict:
        ring = self.ring
        return {"lasso": self.level, "towing": int(self.stage.field.size[self.rock]) if self.rock >= 0 else 0,
                "ring": round(ring.health) if ring is not None and ring.alive else (-1 if self.rings_carried else 0),
                "ring_rocks": ring.held if ring is not None else 0, "loose": len(self.stage.loose)}
