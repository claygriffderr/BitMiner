"""Single-pixel particles: booster exhaust, hull sparks and rock dust.

State lives in numpy arrays; each live particle is one 1x1 sprite, tinted along a colour ramp as it
ages. Exhaust is drawn into the light layer too, so it glows like the flames.
"""

from __future__ import annotations

import math
import random

import arcade
import numpy as np

from art.palette import GLOW, rgba

from ..field import wrap_delta

# kind -> colour ramp from birth to death
RAMPS = {
    "exhaust": ["ion_white", "ion_hi", "ion", "ion_dark"],
    "spark": ["hull_outline", "hull_hi", "hull_light", "hull_mid"],
    "dust": ["rock_rim", "rock_light", "rock_mid", "rock_dark"],
}
KINDS = list(RAMPS)
DRAG = {"exhaust": 2.5, "spark": 1.5, "dust": 1.2}


def _ramp_colors(kind: str) -> list[tuple[int, int, int, int]]:
    return [rgba(c) for c in RAMPS[kind]]


def _ramp_light(kind: str) -> list[tuple[int, int, int, int]]:
    out = []
    for name in RAMPS[kind]:
        r, g, b, _ = rgba(name)
        s = GLOW.get(name, 0.0)
        out.append((int(r * s), int(g * s), int(b * s), 255 if s > 0 else 0))
    return out


class Particles:
    def __init__(self, texture: arcade.Texture, world: tuple[float, float], capacity: int = 700):
        self.world = world
        self.n = capacity
        self.x = np.zeros(capacity)
        self.y = np.zeros(capacity)
        self.vx = np.zeros(capacity)
        self.vy = np.zeros(capacity)
        self.age = np.zeros(capacity)
        self.life = np.ones(capacity)
        self.kind = np.zeros(capacity, dtype=int)
        self.alive = np.zeros(capacity, dtype=bool)
        self._next = 0
        self.rng = random.Random(5)
        self.colors = [_ramp_colors(k) for k in KINDS]
        self.lights = [_ramp_light(k) for k in KINDS]
        self.drag = np.array([DRAG[k] for k in KINDS])
        self.sprites = arcade.SpriteList(capacity=capacity)
        self.light_sprites = arcade.SpriteList(capacity=capacity)
        self._sprites = []
        self._light = []
        for _ in range(capacity):
            s = arcade.Sprite(texture)
            s.visible = False
            self.sprites.append(s)
            self._sprites.append(s)
            ls = arcade.Sprite(texture)
            ls.visible = False
            self.light_sprites.append(ls)
            self._light.append(ls)
        self._shown = np.zeros(capacity, dtype=bool)

    def emit(self, kind: str, x: float, y: float, vx: float, vy: float, life: float) -> None:
        i = self._next
        self._next = (i + 1) % self.n
        self.x[i], self.y[i] = x % self.world[0], y % self.world[1]
        self.vx[i], self.vy[i] = vx, vy
        self.age[i] = 0.0
        self.life[i] = max(0.02, life)
        self.kind[i] = KINDS.index(kind)
        self.alive[i] = True

    def burst(self, kind: str, x: float, y: float, base_angle: float, spread: float, count: int,
              speed: tuple[float, float], life: tuple[float, float], carry: tuple[float, float] = (0, 0)) -> None:
        r = self.rng
        for _ in range(count):
            a = base_angle + r.gauss(0, spread)
            s = r.uniform(*speed)
            self.emit(kind, x, y, carry[0] + math.cos(a) * s, carry[1] + math.sin(a) * s, r.uniform(*life))

    def step(self, dt: float) -> None:
        a = self.alive
        if not a.any():
            return
        keep = np.exp(-self.drag[self.kind[a]] * dt)
        self.vx[a] *= keep
        self.vy[a] *= keep
        self.x[a] = (self.x[a] + self.vx[a] * dt) % self.world[0]
        self.y[a] = (self.y[a] + self.vy[a] * dt) % self.world[1]
        self.age[a] += dt
        self.alive &= self.age < self.life

    def sync(self, cam_x: float, cam_y: float, k: int) -> None:
        """Place live particles next to the camera (the short way round) and hide dead ones."""
        W, H = self.world
        live = np.nonzero(self.alive)[0]
        gone = np.nonzero(self._shown & ~self.alive)[0]
        for i in gone:
            self._sprites[i].visible = False
            self._light[i].visible = False
        self._shown = self.alive.copy()
        if not len(live):
            return
        px = cam_x + wrap_delta(self.x[live] - cam_x, W)
        py = cam_y + wrap_delta(self.y[live] - cam_y, H)
        # Snap so each particle covers whole screen pixels.
        px = np.floor(px * k) / k + 0.5
        py = np.floor(py * k) / k + 0.5
        stage = np.minimum(3, (self.age[live] / self.life[live] * 4).astype(int))
        kinds = self.kind[live]
        for j, i in enumerate(live):
            s = self._sprites[i]
            pos = (float(px[j]), float(py[j]))
            s.position = pos
            s.color = self.colors[kinds[j]][stage[j]]
            s.visible = True
            light = self.lights[kinds[j]][stage[j]]
            ls = self._light[i]
            if light[3]:
                ls.position = pos
                ls.color = light
                ls.visible = True
            elif ls.visible:
                ls.visible = False
