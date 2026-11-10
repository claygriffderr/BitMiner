"""What the enemy knows in Secure the Base, and the mothership's waves.

Enemies only know where you are while one of them can see you (or you hit one of them); then every
one of them knows. When none has seen you for a few seconds they lose you: each group flies to
where you were last seen, searches round it, and eventually gives up and flies home to the
mothership. They also remember any of your drills, sentries or collector ring they come across, and
raid those.

The mothership launches its waves on a timer, each one built from a threat budget (`Fleet`).

Numbers live in `data/combat.json` (the `hunt` and `fleet` blocks).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ..field import wrap_delta
from ..flight import angle_to, forward_vector
from .specs import FLEET, HUNT
from .stage import Enemy, Structure, dist

if TYPE_CHECKING:
    from .ai import Battle


class Hunt:
    """What all the enemies know, shared between them."""

    def __init__(self, battle: "Battle", base: tuple[float, float], mothership: Enemy | None = None,
                 spec: dict | None = None):
        self.battle = battle
        self.spec = spec or HUNT
        self.mothership = mothership
        self.known = False
        self.last_seen = base         # where they think you are; before anyone sees you, your base
        self.since_seen = math.inf
        self.rev = 0                  # goes up each time they lose you, so every group starts a fresh search
        self.drills: dict[int, Structure] = {}
        self._revealed = False

    # ------------------------------------------------------------ places

    def near_copy(self, p: tuple[float, float], ref: tuple[float, float]) -> tuple[float, float]:
        """In wrapping space, the copy of point p nearest ref."""
        world = self.battle.stage.world
        if world is None:
            return p
        W, H = world
        return ref[0] + wrap_delta(p[0] - ref[0], W), ref[1] + wrap_delta(p[1] - ref[1], H)

    def home(self) -> tuple[float, float] | None:
        ms = self.mothership
        if ms is None or not ms.alive:
            return None
        return ms.x, ms.y

    def aim_point(self, m: Structure, x: float, y: float) -> tuple[float, float]:
        """Where a group at (x, y) raiding `m` aims: its centre, or for the collector ring the nearest
        point on its band (its middle is open space)."""
        mx, my = self.near_copy((m.x, m.y), (x, y))
        if m.hoop > 0:
            dx, dy = x - mx, y - my
            d = math.hypot(dx, dy)
            if d > 1e-6:
                return mx + dx / d * m.radius, my + dy / d * m.radius
            return mx, my + m.radius
        return mx, my

    def nearest_drill(self, x: float, y: float) -> Structure | None:
        best, bd = None, math.inf
        for m in self.drills.values():
            if not m.alive:
                continue
            mx, my = self.near_copy((m.x, m.y), (x, y))
            d = dist(x, y, mx, my)
            if d < bd:
                best, bd = m, d
        return best

    # ------------------------------------------------------------ the update

    def reveal(self) -> None:
        """You hit one of them: they know where you are."""
        self._revealed = True

    def step(self, dt: float) -> None:
        st = self.battle.stage
        ship = st.ship
        sight = self.spec["sight"]
        flying = [e for e in st.enemies if e.alive and e.dying < 0 and e.brain is not None]
        seen = self._revealed and st.ship_visible
        self._revealed = False
        if st.ship_visible and not st.ship_down and not seen:
            seen = any(dist(e.x, e.y, ship.x, ship.y) <= sight for e in flying)
        if seen:
            if not self.known:
                self.known = True
                st.events.append(("spotted",))
            self.last_seen = (ship.x, ship.y)
            self.since_seen = 0.0
        else:
            self.since_seen += dt
            if self.known and self.since_seen >= self.spec["lose_after"]:
                self.known = False
                self.rev += 1
                st.events.append(("lost",))
        # Drills, sentries and the collector ring they fly past, they remember.
        for t in st.structures:
            if t.kind not in ("drill", "sentry", "ring") or not t.alive or t.uid in self.drills:
                continue
            reach = sight + (t.radius if t.hoop else 0.0)      # the ring is seen from its band
            if any(dist(e.x, e.y, t.x, t.y) <= reach for e in flying):
                self.drills[t.uid] = t
                st.events.append(("drill_found", t.uid))
        for uid in [u for u, m in self.drills.items() if not m.alive]:
            del self.drills[uid]


class Task:
    """Where one group goes while the enemy doesn't know where you are: raid a drill it knows of,
    else fly to where you were last seen, search round it, and in the end go home."""

    def __init__(self, battle: "Battle"):
        self.battle = battle
        self.kind = "travel"          # travel, search, raid or home
        self.rev = -1
        self.point: tuple[float, float] | None = None
        self.search_t = 0.0
        self.drill: Structure | None = None

    def tick(self, dt: float, cx: float, cy: float) -> tuple[float, float, str]:
        hunt = self.battle.hunt
        spec = hunt.spec
        rng = self.battle.rng
        if self.rev != hunt.rev:
            self.rev = hunt.rev
            self.kind = "travel"
            self.search_t = 0.0
            self.point = None
            self.drill = None
        if self.kind != "home":
            m = self.drill if (self.drill is not None and self.drill.alive and self.drill.uid in hunt.drills) \
                else hunt.nearest_drill(cx, cy)
            if m is not None:
                self.kind = "raid"
                self.drill = m
                mx, my = hunt.aim_point(m, cx, cy)
                return mx, my, "raid"
            if self.kind == "raid":
                self.kind = "travel"
                self.drill = None
        if self.kind == "travel":
            tx, ty = hunt.near_copy(hunt.last_seen, (cx, cy))
            if dist(cx, cy, tx, ty) > spec["arrive"]:
                return tx, ty, "travel"
            self.kind = "search"
            self.point = None
        if self.kind == "search":
            self.search_t += dt
            if self.search_t < spec["search_time"] or hunt.home() is None:
                if self.point is not None:
                    px, py = hunt.near_copy(self.point, (cx, cy))
                    if dist(cx, cy, px, py) <= spec["arrive"]:
                        self.point = None
                if self.point is None:
                    a = rng.uniform(0.0, math.tau)
                    r = spec["search_radius"] * math.sqrt(rng.random())
                    lx, ly = hunt.near_copy(hunt.last_seen, (cx, cy))
                    self.point = (lx + math.cos(a) * r, ly + math.sin(a) * r)
                px, py = hunt.near_copy(self.point, (cx, cy))
                return px, py, "search"
            self.kind = "home"
        hx, hy = hunt.near_copy(hunt.home(), (cx, cy))
        return hx, hy, "home"


def share_out(total: int, parts: int) -> list[int]:
    """`total` things split between `parts` as evenly as it goes, the odd ones spread out along the
    list rather than bunched at its start."""
    if parts <= 0:
        return []
    base, odd = divmod(max(0, int(total)), parts)
    out = [base] * parts
    for j in range(odd):
        out[(j * parts + parts // 2) // odd] += 1
    return out


class Fleet:
    """Launches the mothership's waves on a timer that shrinks as the game goes on, each one built
    by spending that wave's threat budget the way its recipe says. Every `massive.every`th wave from
    `massive.first` is a massive one, released in parts. Numbers: the `fleet` block of `combat.json`;
    `tuning` (the WAVE GAP and WAVE SIZE sliders) scales the gaps and the sizes."""

    def __init__(self, battle: "Battle", mothership: Enemy, spec: dict | None = None, tuning=None):
        self.battle = battle
        self.mothership = mothership
        self.spec = spec or FLEET
        self.tuning = tuning
        self.launched = 0
        self.timer = float(self.spec["first"])
        self.name = ""
        self.last_size = 0
        self.held = False             # the next wave is due but `cap` enemies are still out
        self.parts: list[list] = []   # a wave still leaving: [seconds to go, wave, clusters, bearing]
        self._now = False

    @property
    def number(self) -> int:
        return self.launched

    def call_now(self) -> None:
        self._now = True

    # ------------------------------------------------------------ the plan

    def _scale(self, key: str) -> float:
        return float(getattr(self.tuning, key, 1.0)) if self.tuning is not None else 1.0

    def is_massive(self, n: int) -> bool:
        m = self.spec.get("massive")
        if not m:
            return False
        first, every = int(m["first"]), max(1, int(m["every"]))
        return n >= first and (n - first) % every == 0

    @property
    def massive_in(self) -> int | None:
        """How many launches away the next massive wave is (1: it is the next one)."""
        m = self.spec.get("massive")
        if not m:
            return None
        nxt = self.launched + 1
        first, every = int(m["first"]), max(1, int(m["every"]))
        at = first if nxt <= first else first + -(-(nxt - first) // every) * every
        return at - self.launched

    @property
    def warning(self) -> int | None:
        """`massive_in` once it is close enough to warn of (`massive.warn` waves), else None."""
        k = self.massive_in
        return k if k is not None and k <= int(self.spec["massive"].get("warn", 3)) else None

    def skip_to_massive(self) -> int:
        """A testing shortcut (the M key): move the wave count on so the massive wave is `warn`
        launches away. Returns the wave it will be."""
        k = self.massive_in
        if k is None:
            return 0
        at = self.launched + k
        self.launched = max(self.launched, at - int(self.spec["massive"].get("warn", 3)) - 1)
        return at

    def budget(self, n: int) -> float:
        """Wave n's threat points."""
        b = self.spec["budget"]
        late = int(b.get("late_from", 10 ** 9))
        if n > late:
            points = float(b["late_base"]) + float(b["late_step"]) * (n - late)
        else:
            points = float(b["base"]) + float(b["per_wave"]) * n + float(b["per_wave_sq"]) * n * n
        return points * self._scale("wave_size")

    def gap_after(self, n: int) -> float:
        """Seconds from wave n's launch to the next."""
        spec = self.spec
        if self.is_massive(n):
            gap = float(spec["cooloff"])
        else:
            gap = max(float(spec["gap_min"]), float(spec["gap_start"]) - float(spec["gap_step"]) * (n - 1))
        return gap * self._scale("wave_gap")

    def recipe(self, n: int) -> dict:
        recipes = self.spec["recipes"]
        for r in recipes:
            if "from" in r and n >= int(r["from"]) and (n - int(r["from"])) % max(1, int(r.get("every", 1))) == 0:
                return r
        plain = [r for r in recipes if "from" not in r] or recipes
        return plain[(n - 1) % len(plain)]

    def counts(self, n: int) -> dict[str, int]:
        """How many of each kind wave n has."""
        spec = self.spec
        if self.is_massive(n):
            scale = self._scale("wave_size")
            return {k: int(v * scale + 0.5) for k, v in spec["massive"]["ships"].items()}
        threat, unlock = spec["threat"], spec["unlock"]
        recipe = self.recipe(n)
        points = self.budget(n)
        tanks = 0
        if n >= int(unlock.get("tank", 0)):
            tanks = int(points // float(spec["tank_every"])) + int(recipe.get("tanks", 0))
        rest = max(0.0, points - tanks * float(threat["tank"]))
        mix = {k: float(v) for k, v in recipe["mix"].items()}
        for kind in ("guard", "rapid"):
            if n < int(unlock.get(kind, 0)):
                mix["infantry"] = mix.get("infantry", 0.0) + mix.pop(kind, 0.0)
        whole = sum(mix.values()) or 1.0
        guards = int(rest * mix.get("guard", 0.0) / whole / float(threat["guard"]) + 0.5)
        rapids = int(rest * mix.get("rapid", 0.0) / whole / float(threat["rapid"]) + 0.5)
        left = rest - guards * float(threat["guard"]) - rapids * float(threat["rapid"])
        infantry = max(0, int(left / float(threat["infantry"]) + 0.5))
        if tanks:                     # a tank never comes alone
            guards = max(guards, tanks * int(spec["escort"]["guard"]))
            infantry = max(infantry, tanks * int(spec["escort"]["infantry"]))
        if not (tanks or guards or rapids or infantry):
            infantry = 1
        return {"infantry": infantry, "rapid": rapids, "guard": guards, "tank": tanks}

    def clusters(self, counts: dict[str, int], formations: list[str]) -> list[list[tuple]]:
        """Those ships as the bunches that leave the hangar together: each tank with its escort,
        each infantry squad with its share of the guards, and the rapid ships in their own groups.
        A bunch is a list of (kind, count, formation)."""
        spec = self.spec
        lo, hi = (int(v) for v in spec["squad"])
        tanks, guards = counts.get("tank", 0), counts.get("guard", 0)
        infantry, rapids = counts.get("infantry", 0), counts.get("rapid", 0)
        forms = formations or ["line"]
        out: list[list[tuple]] = []
        k = 0
        for _ in range(tanks):
            g = min(guards, int(spec["escort"]["guard"]))
            i = min(infantry, max(lo, int(spec["escort"]["infantry"])))
            guards -= g
            infantry -= i
            bunch = [("tank", 1, "line")]
            if i:
                bunch.append(("infantry", i, forms[k % len(forms)]))
                k += 1
            if g:
                bunch.append(("guard", g, "line"))
            out.append(bunch)
        squads = share_out(infantry, -(-infantry // hi)) if infantry else []
        walls = share_out(guards, len(squads)) if squads else []
        for size, g in zip(squads, walls):
            bunch = [("infantry", size, forms[k % len(forms)])]
            k += 1
            if g:
                bunch.append(("guard", g, "line"))
            out.append(bunch)
        if guards and not squads:
            out.append([("guard", guards, "line")])
        per = max(1, int(spec.get("rapid_group", 4)))
        for size in (share_out(rapids, -(-rapids // per)) if rapids else []):
            out.append([("rapid", size, "line")])
        return out

    def compose(self, n: int) -> tuple[str, list[list[list[tuple]]]]:
        """Wave n: its name, and the parts it leaves in (a list of bunches each)."""
        spec = self.spec
        counts = self.counts(n)
        if not self.is_massive(n):
            recipe = self.recipe(n)
            return recipe["name"], [self.clusters(counts, recipe.get("formations", []))]
        m = spec["massive"]
        parts = max(1, int(m.get("groups", 1)))
        split = {kind: share_out(total, parts) for kind, total in counts.items()}
        forms = list(m.get("formations", ("wedge", "line", "arc")))
        return m.get("name", "MASSIVE WAVE"), [
            self.clusters({kind: split[kind][i] for kind in split}, forms[i % len(forms):] + forms[:i % len(forms)])
            for i in range(parts)]

    # ------------------------------------------------------------ the update

    def out(self) -> int:
        """Enemies still out."""
        return sum(1 for e in self.battle.stage.enemies if e.alive and e.dying < 0 and e.kind != "mothership")

    @property
    def next_in(self) -> float | None:
        """Seconds to the next launch, or None while it is held back by `cap`."""
        return None if self.held else max(0.0, self.timer)

    def step(self, dt: float) -> None:
        if not self.mothership.alive or self.mothership.dying >= 0:
            return
        for part in self.parts:
            part[0] -= dt
        while self.parts and self.parts[0][0] <= 0:
            _, n, bunches, bearing = self.parts.pop(0)
            self._release(n, bunches, bearing)
            left = len(self.parts)
            self.battle.stage.events.append(("wave_part", n, self._parts - left, self._parts))
        if self._now:
            self._now = False
            self.launch()
            return
        self.timer -= dt
        if self.timer > 0:
            return
        self.held = self.out() >= int(self.spec.get("cap", 10 ** 6))
        if not self.held:
            self.launch()

    _parts = 1

    def launch(self) -> None:
        spec = self.spec
        st = self.battle.stage
        n = self.launched + 1
        name, parts = self.compose(n)
        gap = float(spec.get("massive", {}).get("group_gap", 0.0))
        turn = 360.0 / len(parts)
        self._parts = len(parts)
        self.launched = n
        self.name = name
        self.held = False
        self.timer = self.gap_after(n)
        self.last_size = sum(count for part in parts for bunch in part for _, count, _ in bunch)
        st.events.append(("wave", n, name, self.last_size))
        self._release(n, parts[0], 0.0)
        for i, bunches in enumerate(parts[1:], 1):
            self.parts.append([gap * i, n, bunches, turn * i])

    def _release(self, n: int, bunches: list[list[tuple]], bearing: float) -> None:
        """Out of the hangar on the side facing where they're headed (`bearing` degrees round from it)."""
        battle = self.battle
        st = battle.stage
        ms = self.mothership
        rng = battle.rng
        hunt = battle.hunt
        aim = st.ship if hunt is None or hunt.known else None
        tx, ty = (aim.x, aim.y) if aim is not None else hunt.near_copy(hunt.last_seen, (ms.x, ms.y))
        toward = angle_to(tx - ms.x, ty - ms.y) + bearing
        fan = min(40.0, 200.0 / max(1, len(bunches)))
        for bi, bunch in enumerate(bunches):
            b = toward + (bi - (len(bunches) - 1) / 2) * fan + rng.uniform(-6.0, 6.0)
            fx, fy = forward_vector(b)
            R = 120.0 + 70.0 * (bi % 3)
            x, y = ms.x + fx * R, ms.y + fy * R
            tank, squad = None, None
            for kind, count, formation in bunch:
                # A tank sits behind its escort.
                back = 50.0 if kind == "tank" else 0.0
                members = battle.add_group(kind, count, x - fx * back, y - fy * back, formation)
                for e in members:
                    e.wave = n
                if kind == "tank" and members:
                    tank = members[0]
                elif kind == "infantry" and members:
                    squad = members[0].brain.squad
            if tank is not None and squad is not None:
                squad.escort = tank
