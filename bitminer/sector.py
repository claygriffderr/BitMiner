"""The big map for Secure the Base: how big it is, where home base and the mothership sit, and the
asteroid field that fills it (belts, clusters, loose rocks and landmarks). Every number is in
`data/map.json`.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

from .field import VARIANTS, AsteroidField, collision_radius, wrap_delta
from .world import WORLD_H, WORLD_W

MAP_FILE = Path(__file__).resolve().parent / "data" / "map.json"
MAP: dict = json.loads(MAP_FILE.read_text(encoding="utf-8"))

BELT_SIZES = (10, 10, 14, 14, 14, 18, 18, 18, 24, 24, 24, 32, 32, 48, 48, 64)
CLUSTER_SIZES = (10, 14, 14, 18, 18, 24, 24, 32, 32, 48, 48, 64, 96)
LOOSE_SIZES = (10, 10, 14, 14, 18, 24, 32)
LANDMARK_SIZES = (64, 96, 96)


@dataclass
class Layout:
    width: float
    height: float
    base: tuple[float, float]
    mothership: tuple[float, float]
    spawn: tuple[float, float]


def layout(spec: dict | None = None, scale: float | None = None) -> Layout:
    """Where everything big sits on a map of the given scale (times the combat sandbox)."""
    spec = spec or MAP
    k = float(spec["scale"] if scale is None else scale)
    W, H = WORLD_W * k, WORLD_H * k
    base = (W * 0.25, H * 0.25)
    d = float(spec["mothership"]["distance"])
    mothership = ((base[0] + W * d) % W, (base[1] + H * d) % H)
    spawn = (base[0], base[1] - 90.0)
    return Layout(W, H, base, mothership, spawn)


class _Placer:
    """Collects rocks for a new field, refusing any that would overlap one already placed or sit
    in a kept-clear circle. Uses its own grid so building tens of thousands of rocks stays quick."""

    CELL = 128.0

    def __init__(self, W: float, H: float, clear: list[tuple[float, float, float]], rng: random.Random):
        self.W, self.H = W, H
        self.clear = clear
        self.rng = rng
        self.cells: dict[tuple[int, int], list[tuple[float, float, float]]] = {}
        self.gw = max(1, int(W // self.CELL))
        self.gh = max(1, int(H // self.CELL))
        self.cw, self.ch = W / self.gw, H / self.gh
        self.xs: list[float] = []
        self.ys: list[float] = []
        self.sizes: list[int] = []
        self.variants: list[int] = []
        self.ores: list[bool] = []

    def place(self, x: float, y: float, size: int, ore_chance: float, gap: float = 4.0) -> bool:
        W, H = self.W, self.H
        x, y = x % W, y % H
        r = collision_radius(size)
        for cx, cy, cr in self.clear:
            if math.hypot(wrap_delta(x - cx, W), wrap_delta(y - cy, H)) < cr + r:
                return False
        col, row = int(x // self.cw), int(y // self.ch)
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                for ox, oy, orr in self.cells.get(((col + dc) % self.gw, (row + dr) % self.gh), ()):
                    if math.hypot(wrap_delta(x - ox, W), wrap_delta(y - oy, H)) < r + orr + gap:
                        return False
        self.cells.setdefault((col % self.gw, row % self.gh), []).append((x, y, r))
        self.xs.append(x)
        self.ys.append(y)
        self.sizes.append(size)
        self.variants.append(self.rng.randrange(VARIANTS))
        self.ores.append(self.rng.random() < ore_chance)
        return True


def build_field(lay: Layout, spec: dict | None = None, seed: int | None = None) -> AsteroidField:
    """Fill the map with rocks: wavy belts across and down, round clusters, big landmark rocks,
    and loose rocks everywhere so open space is never empty."""
    spec = spec or MAP
    seed = int(spec.get("seed", 11) if seed is None else seed)
    W, H = lay.width, lay.height
    rng = random.Random(seed)
    clear = [(*lay.base, float(spec["home_base"]["clear"])),
             (*lay.mothership, float(spec["mothership"]["clear"])),
             (*lay.spawn, float(spec.get("spawn_clear", 150)))]
    p = _Placer(W, H, clear, rng)
    ore = spec["ore"]
    area = W * H / 1e6

    # Landmarks first, so the belts and clusters settle round them.
    for _ in range(int(round(spec["landmarks_per_million"] * area))):
        for _ in range(50):
            if p.place(rng.uniform(0, W), rng.uniform(0, H), rng.choice(LANDMARK_SIZES), ore["landmark"]):
                break

    # Belts: periodic wavy lines, so each one joins up cleanly across the wrap.
    spacing = float(spec["belt_spacing"])
    belts = []
    across = max(1, round(H / spacing))
    down = max(1, round(W / spacing))
    for i in range(across):
        y0 = H * (i + rng.uniform(0.3, 0.7)) / across
        belts.append(("across", y0, W))
    for i in range(down):
        x0 = W * (i + rng.uniform(0.3, 0.7)) / down
        belts.append(("down", x0, H))
    for way, at, length in belts:
        swing = rng.uniform(*spec["wave"])
        k1, k2 = rng.randint(1, 3), rng.randint(3, 7)
        ph1, ph2 = rng.uniform(0, math.tau), rng.uniform(0, math.tau)
        half = rng.uniform(*spec["half_width"])
        count = int(spec["per_1000px"] * length / 1000)

        def curve(t, at=at, swing=swing, k1=k1, k2=k2, ph1=ph1, ph2=ph2, length=length, way=way):
            off = swing * math.sin(k1 * math.tau * t + ph1) + swing * 0.3 * math.sin(k2 * math.tau * t + ph2)
            return (length * t, at + off) if way == "across" else (at + off, length * t)

        tries = 0
        while count > 0 and tries < count * 4 + 100:
            tries += 1
            cx, cy = curve(rng.random())
            off = rng.gauss(0, half / 2)
            a = rng.uniform(0, math.tau)
            if p.place(cx + math.cos(a) * off, cy + math.sin(a) * off, rng.choice(BELT_SIZES), ore["belt"]):
                count -= 1

    # Clusters: round fields of rocks, densest in the middle.
    for _ in range(int(round(spec["clusters_per_million"] * area))):
        cx, cy = rng.uniform(0, W), rng.uniform(0, H)
        R = rng.uniform(*spec["cluster_radius"])
        n = rng.randint(*spec["cluster_rocks"])
        tries = 0
        while n > 0 and tries < n * 4:
            tries += 1
            d = R * math.sqrt(rng.random()) * rng.uniform(0.6, 1.0)
            a = rng.uniform(0, math.tau)
            if p.place(cx + math.cos(a) * d, cy + math.sin(a) * d, rng.choice(CLUSTER_SIZES), ore["cluster"]):
                n -= 1

    # Loose rocks everywhere.
    want = int(round(spec["loose_per_million"] * area))
    placed = tries = 0
    while placed < want and tries < want * 4 + 100:
        tries += 1
        if p.place(rng.uniform(0, W), rng.uniform(0, H), rng.choice(LOOSE_SIZES), ore["loose"]):
            placed += 1

    f = AsteroidField(W, H, seed)
    f.add_many(p.xs, p.ys, p.sizes, p.variants, p.ores)
    return f
