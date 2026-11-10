"""The wrap-around asteroid field: where the rocks are, how they drift, and what happens when
the ship hits one. Pure numpy, no graphics.

Every position wraps at the field's edges, so the field has no border: fly off the right and you
come back on the left. Distances are always measured the short way around.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import numpy as np

from .flight import Ship

SIZES = (10, 14, 18, 24, 32, 48, 64, 96)   # Asteroid sprite diameters, in game pixels.
VARIANTS = 3                               # Different rock shapes per size.
ROCK_DENSITY = 0.0035                      # Mass per square pixel of radius. A 24 px rock weighs 0.42 ships.
ROCK_DAMPER = 0.12                         # Pushed rocks slowly come to rest.
SLEEP_SPEED = 0.8                          # Below this speed a rock stops moving.
CELL = 128.0                               # Side of a lookup cell. Rocks are filed by the cell their centre is in.


def wrap_delta(d, size):
    """Shortest signed distance along a wrapping axis. Works on floats and numpy arrays."""
    return (d + size / 2) % size - size / 2


def collision_radius(diameter: float) -> float:
    return diameter * 0.46


@dataclass
class Impact:
    x: float          # Contact point, world coordinates.
    y: float
    nx: float         # Unit normal from the ship toward the rock.
    ny: float
    impulse: float    # How hard the hit was (mass times speed change).
    rock: int


class AsteroidField:
    def __init__(self, width: float, height: float, seed: int = 1):
        self.width = float(width)
        self.height = float(height)
        self.seed = seed
        self.x = np.zeros(0)
        self.y = np.zeros(0)
        self.vx = np.zeros(0)
        self.vy = np.zeros(0)
        self.r = np.zeros(0)
        self.m = np.zeros(0)
        self.size = np.zeros(0, dtype=int)
        self.variant = np.zeros(0, dtype=int)
        self.ore = np.zeros(0, dtype=bool)
        self.wear = np.zeros(0, dtype=np.int8)     # crack stage 0 to 3 as drills empty a rock
        self.gone = np.zeros(0, dtype=bool)        # crumbled away: no longer in the field
        self.sites: dict[int, list[float]] = {}    # where drills sit on a rock (headings), for its cracks
        self.held: set[int] = set()                # rocks something is pulling (the lasso): never put to sleep
        self._reach_cache = None
        self._reach_max = 0.0
        self._r_max = 0.0
        # The lookup grid: which rocks have their centre in each cell, so a question about one
        # spot only looks at the rocks near it, however big the field is.
        self._gw = max(1, int(math.ceil(self.width / CELL)))
        self._gh = max(1, int(math.ceil(self.height / CELL)))
        self._cw = self.width / self._gw
        self._ch = self.height / self._gh
        self._grid: dict[int, list[int]] = {}
        self._cell = np.zeros(0, dtype=np.int64)

    def __len__(self) -> int:
        return len(self.x)

    # ------------------------------------------------------------ building

    def add(self, x: float, y: float, size: int, variant: int, ore: bool) -> None:
        r = collision_radius(size)
        self.x = np.append(self.x, x % self.width)
        self.y = np.append(self.y, y % self.height)
        self.vx = np.append(self.vx, 0.0)
        self.vy = np.append(self.vy, 0.0)
        self.r = np.append(self.r, r)
        self.m = np.append(self.m, ROCK_DENSITY * r * r)
        self.size = np.append(self.size, size)
        self.variant = np.append(self.variant, variant)
        self.ore = np.append(self.ore, ore)
        self.wear = np.append(self.wear, np.int8(0))
        self.gone = np.append(self.gone, False)
        self._r_max = max(self._r_max, r)
        i = len(self.x) - 1
        key = self._key(self.x[i], self.y[i])
        self._cell = np.append(self._cell, key)
        self._grid.setdefault(key, []).append(i)

    def add_many(self, xs, ys, sizes, variants, ores) -> None:
        """Add a batch of rocks in one go (building a big field one rock at a time is slow)."""
        n0 = len(self.x)
        xs = np.asarray(xs, dtype=float) % self.width
        ys = np.asarray(ys, dtype=float) % self.height
        sizes = np.asarray(sizes, dtype=int)
        r = collision_radius(sizes.astype(float))
        k = len(xs)
        self.x = np.concatenate([self.x, xs])
        self.y = np.concatenate([self.y, ys])
        self.vx = np.concatenate([self.vx, np.zeros(k)])
        self.vy = np.concatenate([self.vy, np.zeros(k)])
        self.r = np.concatenate([self.r, r])
        self.m = np.concatenate([self.m, ROCK_DENSITY * r * r])
        self.size = np.concatenate([self.size, sizes])
        self.variant = np.concatenate([self.variant, np.asarray(variants, dtype=int)])
        self.ore = np.concatenate([self.ore, np.asarray(ores, dtype=bool)])
        self.wear = np.concatenate([self.wear, np.zeros(k, dtype=np.int8)])
        self.gone = np.concatenate([self.gone, np.zeros(k, dtype=bool)])
        if k:
            self._r_max = max(self._r_max, float(r.max()))
        keys = self._keys(xs, ys)
        self._cell = np.concatenate([self._cell, keys])
        for j, key in enumerate(keys.tolist()):
            self._grid.setdefault(key, []).append(n0 + j)

    # ------------------------------------------------------------ the lookup grid

    def _key(self, x: float, y: float) -> int:
        cx = int(x // self._cw) % self._gw
        cy = int(y // self._ch) % self._gh
        return cy * self._gw + cx

    def _keys(self, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        cx = (np.floor_divide(xs, self._cw).astype(np.int64)) % self._gw
        cy = (np.floor_divide(ys, self._ch).astype(np.int64)) % self._gh
        return cy * self._gw + cx

    def remove(self, i: int) -> None:
        """Take rock `i` out of the field for good (it crumbled). It keeps its number, so other
        rocks keep theirs, but nothing finds it any more: no collisions, no lookups."""
        if self.gone[i]:
            return
        self.gone[i] = True
        self.held.discard(i)
        self.ore[i] = False
        self.vx[i] = self.vy[i] = 0.0
        cell = self._grid.get(int(self._cell[i]))
        if cell is not None and i in cell:
            cell.remove(i)
            if not cell:
                del self._grid[int(self._cell[i])]
        self.sites.pop(i, None)

    def _refile(self, idx) -> None:
        """Rocks in `idx` may have moved: file them under the cell they are in now."""
        for i in np.atleast_1d(idx).tolist():
            if self.gone[i]:
                continue
            key = self._key(self.x[i], self.y[i])
            old = int(self._cell[i])
            if key != old:
                cell = self._grid.get(old)
                if cell is not None:
                    cell.remove(i)
                    if not cell:
                        del self._grid[old]
                self._grid.setdefault(key, []).append(i)
                self._cell[i] = key

    def _candidates(self, x: float, y: float, hx: float, hy: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Every rock whose centre is within the box (x +- hx, y +- hy), plus some just outside it,
        with offsets from (x, y) the short way round. Sorted by rock number."""
        gw, gh = self._gw, self._gh
        c0 = int(math.floor((x - hx) / self._cw))
        c1 = int(math.floor((x + hx) / self._cw))
        r0 = int(math.floor((y - hy) / self._ch))
        r1 = int(math.floor((y + hy) / self._ch))
        cols = range(gw) if c1 - c0 + 1 >= gw else [c % gw for c in range(c0, c1 + 1)]
        rows = range(gh) if r1 - r0 + 1 >= gh else [r % gh for r in range(r0, r1 + 1)]
        grid = self._grid
        found: list[int] = []
        for row in rows:
            base = row * gw
            for col in cols:
                cell = grid.get(base + col)
                if cell:
                    found.extend(cell)
        if not found:
            empty = np.zeros(0, dtype=np.int64)
            return empty, np.zeros(0), np.zeros(0)
        idx = np.array(sorted(found), dtype=np.int64)
        dx = wrap_delta(self.x[idx] - x, self.width)
        dy = wrap_delta(self.y[idx] - y, self.height)
        return idx, dx, dy

    def fits(self, x: float, y: float, r: float, gap: float = 4.0) -> bool:
        if not len(self):
            return True
        reach = r + gap + self._r_max
        idx, dx, dy = self._candidates(x, y, reach, reach)
        return bool(np.all(np.hypot(dx, dy) >= self.r[idx] + r + gap))

    @classmethod
    def flight_test(cls, width: float = 3200, height: float = 2000, seed: int = 7,
                    spawn: tuple[float, float] | None = None) -> "AsteroidField":
        """Two wavy belts that cross, a few big landmark rocks, and loose rocks everywhere else.

        The area around the spawn point is kept clear.
        """
        f = cls(width, height, seed)
        rng = random.Random(seed)
        spawn = spawn or (width / 2, height / 2)

        def clear_of_spawn(x, y, r):
            dx = wrap_delta(x - spawn[0], width)
            dy = wrap_delta(y - spawn[1], height)
            return math.hypot(dx, dy) > 150 + r

        def place(x, y, size, ore_chance):
            r = collision_radius(size)
            if clear_of_spawn(x, y, r) and f.fits(x, y, r):
                f.add(x, y, size, rng.randrange(VARIANTS), rng.random() < ore_chance)
                return True
            return False

        # Landmarks: big rocks spread around the field.
        for i in range(7):
            for _ in range(50):
                if place(rng.uniform(0, width), rng.uniform(0, height), rng.choice((64, 96, 96)), 0.6):
                    break

        # Belt one runs left to right, belt two top to bottom. Both wave, and both wrap cleanly.
        def belt_one(t):
            return width * t, height * 0.74 + 170 * math.sin(2 * math.pi * t) + 50 * math.sin(6 * math.pi * t)

        def belt_two(t):
            return width * 0.2 + 150 * math.sin(4 * math.pi * t), height * t

        belt_sizes = (10, 10, 14, 14, 14, 18, 18, 18, 24, 24, 24, 32, 32, 48, 48, 64)
        for belt, count, half_width in ((belt_one, 260, 120), (belt_two, 170, 105)):
            for _ in range(count * 4):
                if count <= 0:
                    break
                cx, cy = belt(rng.random())
                # Denser in the middle of the belt.
                off = rng.gauss(0, half_width / 2)
                ang = rng.uniform(0, 2 * math.pi)
                x, y = cx + math.cos(ang) * off, cy + math.sin(ang) * off
                if place(x, y, rng.choice(belt_sizes), 0.3):
                    count -= 1

        # Loose rocks everywhere so open space is never empty.
        loose = (10, 10, 14, 14, 18, 24, 32)
        placed, tries = 0, 0
        while placed < 70 and tries < 2000:
            tries += 1
            if place(rng.uniform(0, width), rng.uniform(0, height), rng.choice(loose), 0.2):
                placed += 1
        return f

    # ------------------------------------------------------------ queries

    def near(self, x: float, y: float, half_w: float, half_h: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Rocks overlapping the box around (x, y), with their offsets from (x, y) the short way round."""
        reach = self._reach()
        idx, dx, dy = self._candidates(x, y, half_w + self._reach_max, half_h + self._reach_max)
        if not len(idx):
            return idx, dx, dy
        rr = reach[idx]
        keep = (np.abs(dx) <= half_w + rr) & (np.abs(dy) <= half_h + rr)
        return idx[keep], dx[keep], dy[keep]

    def _reach(self) -> np.ndarray:
        """How far each rock's picture reaches from its centre (cached: rocks never change size)."""
        if self._reach_cache is None or len(self._reach_cache) != len(self):
            self._reach_cache = self.size / 2 + 4
            self._reach_max = float(self._reach_cache.max()) if len(self) else 0.0
        return self._reach_cache

    @property
    def awake(self) -> np.ndarray:
        return np.nonzero((self.vx != 0) | (self.vy != 0))[0]

    # ------------------------------------------------------------ simulation

    def step(self, dt: float) -> None:
        """Move pushed rocks, let them bump each other, and let them settle."""
        moving = self.awake
        if not len(moving):
            return
        self.x[moving] = (self.x[moving] + self.vx[moving] * dt) % self.width
        self.y[moving] = (self.y[moving] + self.vy[moving] * dt) % self.height
        keep = math.exp(-ROCK_DAMPER * dt)
        self.vx[moving] *= keep
        self.vy[moving] *= keep
        touched = set(moving.tolist())
        for i in moving:
            touched.update(self._collide_rock(int(i)))
        self._refile(np.array(sorted(touched), dtype=np.int64))
        slow = np.hypot(self.vx, self.vy) < SLEEP_SPEED
        if self.held:
            # A rock on the lasso gains only a little speed each step (less the shorter the step),
            # so putting it to sleep would stop it ever moving, differently at each frame rate.
            slow[[i for i in self.held if i < len(slow)]] = False
        self.vx[slow] = 0.0
        self.vy[slow] = 0.0

    def _collide_rock(self, i: int, bounce: float = 0.5) -> list[int]:
        """Push rock i and any rock it overlaps apart. Returns the rocks it moved."""
        reach = self.r[i] + self._r_max
        close, cdx, cdy = self._candidates(self.x[i], self.y[i], reach, reach)
        moved = []
        for j, ddx, ddy in zip(close.tolist(), cdx, cdy):
            if j == i:
                continue
            d = math.hypot(ddx, ddy)
            over = self.r[j] + self.r[i] - d
            if over <= 0:
                continue
            d = max(d, 1e-6)
            nx, ny = ddx / d, ddy / d
            inv_i, inv_j = 1 / self.m[i], 1 / self.m[j]
            rel = (self.vx[j] - self.vx[i]) * nx + (self.vy[j] - self.vy[i]) * ny
            if rel < 0:
                jimp = -(1 + bounce) * rel / (inv_i + inv_j)
                self.vx[i] -= jimp * inv_i * nx
                self.vy[i] -= jimp * inv_i * ny
                self.vx[j] += jimp * inv_j * nx
                self.vy[j] += jimp * inv_j * ny
            push = over / (inv_i + inv_j)
            self.x[i] = (self.x[i] - push * inv_i * nx) % self.width
            self.y[i] = (self.y[i] - push * inv_i * ny) % self.height
            self.x[j] = (self.x[j] + push * inv_j * nx) % self.width
            self.y[j] = (self.y[j] + push * inv_j * ny) % self.height
            moved.append(j)
        return moved

    def collide_ship(self, ship: Ship, ship_mass: float, bounce: float) -> list[Impact]:
        """Bounce the ship off any rocks it overlaps, trading momentum by mass. Returns the hits."""
        impacts: list[Impact] = []
        if not len(self):
            return impacts
        reach = ship.radius + self._r_max
        cand, cdx, cdy = self._candidates(ship.x, ship.y, reach, reach)
        if not len(cand):
            return impacts
        cdist = np.hypot(cdx, cdy)
        coverlap = self.r[cand] + ship.radius - cdist
        hits = np.nonzero(coverlap > 0)[0]
        inv_s = 1 / max(0.05, ship_mass)
        for h in hits[np.argsort(-coverlap[hits])]:
            i = int(cand[h])
            d = max(cdist[h], 1e-6)
            nx, ny = cdx[h] / d, cdy[h] / d
            inv_a = 1 / self.m[i]
            rel = (self.vx[i] - ship.vx) * nx + (self.vy[i] - ship.vy) * ny
            jimp = 0.0
            if rel < 0:
                jimp = -(1 + bounce) * rel / (inv_s + inv_a)
                ship.vx -= jimp * inv_s * nx
                ship.vy -= jimp * inv_s * ny
                self.vx[i] += jimp * inv_a * nx
                self.vy[i] += jimp * inv_a * ny
            # Push the two apart so they don't stay stuck together.
            push = coverlap[h] / (inv_s + inv_a)
            ship.x = (ship.x - push * inv_s * nx) % self.width
            ship.y = (ship.y - push * inv_s * ny) % self.height
            ship.ux -= push * inv_s * nx
            ship.uy -= push * inv_s * ny
            self.x[i] = (self.x[i] + push * inv_a * nx) % self.width
            self.y[i] = (self.y[i] + push * inv_a * ny) % self.height
            self._refile(i)
            if jimp > 0:
                impacts.append(Impact(ship.x + nx * ship.radius, ship.y + ny * ship.radius, nx, ny, jimp, i))
        return impacts
