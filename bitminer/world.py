"""The flight test world: the ship, the asteroid field, and the clock that steps them together."""

from __future__ import annotations

import math

from .field import AsteroidField, Impact, wrap_delta
from .flight import Controls, Ship
from .settings import Tuning

WORLD_W = 3200.0
WORLD_H = 2000.0
PHYSICS_STEP = 1 / 120   # Longest physics step. Longer frames are split into equal smaller steps.
MAX_FRAME = 1 / 20       # A frame longer than this (a hitch, a dragged window) is slowed down.


class FlightWorld:
    def __init__(self, seed: int = 7):
        self.width = WORLD_W
        self.height = WORLD_H
        # Start just below the long belt, so there is something to fly at straight away.
        self.spawn = (WORLD_W / 2, WORLD_H * 0.74 - 250)
        self.field = AsteroidField.flight_test(WORLD_W, WORLD_H, seed=seed, spawn=self.spawn)
        self.ship = Ship(*self.spawn)
        self.time = 0.0

    def step(self, controls: Controls, tuning: Tuning, dt: float) -> list[Impact]:
        """Advance by dt seconds and return every hit between the ship and a rock."""
        dt = min(max(dt, 0.0), MAX_FRAME)
        if dt == 0:
            return []
        n = max(1, math.ceil(dt / PHYSICS_STEP - 1e-9))
        h = dt / n
        impacts: list[Impact] = []
        for _ in range(n):
            self.ship.step(controls, tuning, h, self.width, self.height)
            impacts += self.field.collide_ship(self.ship, tuning.mass, tuning.bounce)
            self.field.step(h)
            self.time += h
        return impacts

    def respawn(self) -> None:
        """Put the ship back at the start, stopped and facing up."""
        old = self.ship
        self.ship = Ship(*self.spawn)
        # Keep the backdrop's running distance continuous so the stars jump with the ship.
        self.ship.ux = old.ux + wrap_delta(self.spawn[0] - old.x, self.width)
        self.ship.uy = old.uy + wrap_delta(self.spawn[1] - old.y, self.height)
