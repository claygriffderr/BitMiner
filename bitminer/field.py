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
        self._reach_cache = None
        self._reach_max = 0.0

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

    def fits(self, x: float, y: float, r: float, gap: float = 4.0) -> bool:
        if not len(self):
            return True
        dx = wrap_delta(self.x - x, self.width)
        dy = wrap_delta(self.y - y, self.height)
        return bool(np.all(np.hypot(dx, dy) >= self.r + r + gap))

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
        dx = self._offsets(self.x, x, half_w, self.width)
        dy = self._offsets(self.y, y, half_h, self.height)
        reach = self._reach()
        idx = np.nonzero((np.abs(dx) <= half_w + reach) & (np.abs(dy) <= half_h + reach))[0]
        return idx, dx[idx], dy[idx]

    def _reach(self) -> np.ndarray:
        """How far each rock's picture reaches from its centre (cached: rocks never change size)."""
        if self._reach_cache is None or len(self._reach_cache) != len(self):
            self._reach_cache = self.size / 2 + 4
            self._reach_max = float(self._reach_cache.max()) if len(self) else 0.0
        return self._reach_cache

    def _offsets(self, xs: np.ndarray, x: float, half: float, size: float) -> np.ndarray:
        """Offsets from x along one wrapping axis. Wrapping costs time, so it is only done when the
        box around x comes near the seam; anywhere else the plain difference is the short way."""
        self._reach()
        x0 = x % size
        d = xs - x0
        if x0 - half - self._reach_max < 0 or x0 + half + self._reach_max > size:
            d = wrap_delta(d, size)
        return d

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
        for i in moving:
            self._collide_rock(int(i))
        slow = np.hypot(self.vx, self.vy) < SLEEP_SPEED
        self.vx[slow] = 0.0
        self.vy[slow] = 0.0

    def _collide_rock(self, i: int, bounce: float = 0.5) -> None:
        reach = self.r[i] + float(self.r.max())
        dx = self._offsets(self.x, self.x[i], reach, self.width)
        dy = self._offsets(self.y, self.y[i], reach, self.height)
        close = np.nonzero((np.abs(dx) < reach) & (np.abs(dy) < reach))[0]
        for j in close:
            if j == i:
                continue
            d = math.hypot(dx[j], dy[j])
            over = self.r[j] + self.r[i] - d
            if over <= 0:
                continue
            d = max(d, 1e-6)
            nx, ny = dx[j] / d, dy[j] / d
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

    def collide_ship(self, ship: Ship, ship_mass: float, bounce: float) -> list[Impact]:
        """Bounce the ship off any rocks it overlaps, trading momentum by mass. Returns the hits."""
        impacts: list[Impact] = []
        if not len(self):
            return impacts
        reach = ship.radius + float(self.r.max())
        dx = self._offsets(self.x, ship.x, reach, self.width)
        dy = self._offsets(self.y, ship.y, reach, self.height)
        dist = np.hypot(dx, dy)
        overlap = self.r + ship.radius - dist
        hits = np.nonzero(overlap > 0)[0]
        inv_s = 1 / max(0.05, ship_mass)
        for i in hits[np.argsort(-overlap[hits])]:
            d = max(dist[i], 1e-6)
            nx, ny = dx[i] / d, dy[i] / d
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
            push = overlap[i] / (inv_s + inv_a)
            ship.x = (ship.x - push * inv_s * nx) % self.width
            ship.y = (ship.y - push * inv_s * ny) % self.height
            ship.ux -= push * inv_s * nx
            ship.uy -= push * inv_s * ny
            self.x[i] = (self.x[i] + push * inv_a * nx) % self.width
            self.y[i] = (self.y[i] + push * inv_a * ny) % self.height
            if jimp > 0:
                impacts.append(Impact(ship.x + nx * ship.radius, ship.y + ny * ship.radius, nx, ny, jimp, int(i)))
        return impacts
