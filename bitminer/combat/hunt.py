"""What the enemy knows in Secure the Base, and the mothership's waves.

Enemies only know where you are while one of them can see you (or you hit one of them); then every
one of them knows. When none has seen you for a few seconds they lose you: each group flies to
where you were last seen, searches round it, and eventually gives up and flies home to the
mothership. They also remember any of your mines they come across, and raid those.

The mothership launches each wave from its hangar once only a few enemies are still out.

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
        self.mines: dict[int, Structure] = {}
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

    def nearest_mine(self, x: float, y: float) -> Structure | None:
        best, bd = None, math.inf
        for m in self.mines.values():
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
        # Mines they fly past, they remember.
        for t in st.structures:
            if t.kind != "mine" or not t.alive or t.uid in self.mines:
                continue
            if any(dist(e.x, e.y, t.x, t.y) <= sight for e in flying):
                self.mines[t.uid] = t
                st.events.append(("mine_found", t.uid))
        for uid in [u for u, m in self.mines.items() if not m.alive]:
            del self.mines[uid]


class Task:
    """Where one group goes while the enemy doesn't know where you are: raid a mine it knows of,
    else fly to where you were last seen, search round it, and in the end go home."""

    def __init__(self, battle: "Battle"):
        self.battle = battle
        self.kind = "travel"          # travel, search, raid or home
        self.rev = -1
        self.point: tuple[float, float] | None = None
        self.search_t = 0.0
        self.mine: Structure | None = None

    def tick(self, dt: float, cx: float, cy: float) -> tuple[float, float, str]:
        hunt = self.battle.hunt
        spec = hunt.spec
        rng = self.battle.rng
        if self.rev != hunt.rev:
            self.rev = hunt.rev
            self.kind = "travel"
            self.search_t = 0.0
            self.point = None
            self.mine = None
        if self.kind != "home":
            m = self.mine if (self.mine is not None and self.mine.alive and self.mine.uid in hunt.mines) \
                else hunt.nearest_mine(cx, cy)
            if m is not None:
                self.kind = "raid"
                self.mine = m
                mx, my = hunt.near_copy((m.x, m.y), (cx, cy))
                return mx, my, "raid"
            if self.kind == "raid":
                self.kind = "travel"
                self.mine = None
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


class Fleet:
    """Launches the waves listed in `combat.json` (`fleet`) from the mothership: the first after
    `first` seconds, then each next one `gap` seconds after only `few_left` enemies are still out."""

    def __init__(self, battle: "Battle", mothership: Enemy, spec: dict | None = None):
        self.battle = battle
        self.mothership = mothership
        self.spec = spec or FLEET
        self.launched = 0
        self.timer = float(self.spec["first"])
        self.wait = 0.0
        self.name = ""
        self.last_size = 0
        self._now = False

    @property
    def number(self) -> int:
        return self.launched

    def call_now(self) -> None:
        self._now = True

    def out(self) -> int:
        """Enemies still out, not counting ships on their way home."""
        battle = self.battle
        return sum(1 for e in battle.stage.enemies
                   if e.alive and e.dying < 0 and e.brain is not None and not battle.heading_home(e))

    @property
    def few_left(self) -> int:
        """How few must be left before the next wave: `few_left`, but never more than
        `few_left_share` of the last wave, so a small wave has to be mostly beaten first."""
        spec = self.spec
        return min(int(spec["few_left"]), int(self.last_size * float(spec.get("few_left_share", 0.5))))

    def step(self, dt: float) -> None:
        if not self.mothership.alive or self.mothership.dying >= 0:
            return
        if self._now:
            self._now = False
            self.launch()
            return
        if self.launched == 0:
            self.timer -= dt
            if self.timer <= 0:
                self.launch()
            return
        if self.out() <= self.few_left:
            self.wait += dt
            if self.wait >= self.spec["gap"]:
                self.launch()
        else:
            self.wait = 0.0

    def launch(self) -> None:
        spec = self.spec
        battle = self.battle
        st = battle.stage
        ms = self.mothership
        rng = battle.rng
        waves = spec["list"]
        wave = waves[self.launched % len(waves)]
        lap = self.launched // len(waves)
        groups = wave["groups"]
        # Out of the hangar on the side facing where they're headed.
        hunt = battle.hunt
        aim = st.ship if hunt is None or hunt.known else None
        tx, ty = (aim.x, aim.y) if aim is not None else hunt.near_copy(hunt.last_seen, (ms.x, ms.y))
        toward = angle_to(tx - ms.x, ty - ms.y)
        R = 120.0
        size = 0
        for gi, g in enumerate(groups):
            kind = g["kind"]
            count = int(g["count"]) + lap * int(spec.get("grow", 0))
            b = toward + (gi - (len(groups) - 1) / 2) * 40.0 + rng.uniform(-8.0, 8.0)
            fx, fy = forward_vector(b)
            battle.add_group(kind, count, ms.x + fx * R, ms.y + fy * R, g.get("formation", "line"))
            size += count
        self.last_size = size
        self.launched += 1
        self.wait = 0.0
        self.name = wave["name"]
        st.events.append(("wave", self.launched, self.name))
