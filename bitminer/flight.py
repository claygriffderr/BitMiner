"""The player ship's flight model. Pure Python, no graphics, so it can be tested on its own.

World units are game pixels (the game screen is 640x360 of them) and seconds. Y points up.
Angles are degrees clockwise from straight up, the same as Arcade's sprite angles.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .settings import Tuning

SHIP_RADIUS = 7.0        # Collision circle for the 17x17 ship sprite.
SOFT_CAP_PULL = 6.0      # Above top speed, the excess shrinks by this fraction per second.


@dataclass
class Controls:
    forward: bool = False   # W
    back: bool = False      # S
    left: bool = False      # A
    right: bool = False     # D
    aim: float | None = None  # Angle toward the mouse. None keeps the current heading.

    def boosters(self) -> tuple[str, ...]:
        """Which booster flames are lit, by key."""
        keys = []
        if self.forward:
            keys.append("W")
        if self.back:
            keys.append("S")
        if self.left:
            keys.append("A")
        if self.right:
            keys.append("D")
        return tuple(keys)


def wrap_angle(a: float) -> float:
    """Wrap to (-180, 180]."""
    a = (a + 180.0) % 360.0 - 180.0
    return 180.0 if a == -180.0 else a


def forward_vector(angle: float) -> tuple[float, float]:
    r = math.radians(angle)
    return math.sin(r), math.cos(r)


def right_vector(angle: float) -> tuple[float, float]:
    r = math.radians(angle)
    return math.cos(r), -math.sin(r)


def angle_to(dx: float, dy: float) -> float:
    """Angle of the vector (dx, dy), clockwise from up."""
    return math.degrees(math.atan2(dx, dy))


@dataclass
class Ship:
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    angle: float = 0.0
    radius: float = SHIP_RADIUS
    # Distance flown without wrapping, for the parallax backdrop.
    ux: float = field(default=0.0)
    uy: float = field(default=0.0)

    def __post_init__(self) -> None:
        self.ux, self.uy = self.x, self.y

    @property
    def speed(self) -> float:
        return math.hypot(self.vx, self.vy)

    def thrust(self, controls: Controls, tuning: Tuning) -> tuple[float, float]:
        """Acceleration from the boosters, in world axes."""
        fx, fy = forward_vector(self.angle)
        rx, ry = right_vector(self.angle)
        ax = ay = 0.0
        if controls.forward:
            ax += fx * tuning.thrust_main
            ay += fy * tuning.thrust_main
        if controls.back:
            ax -= fx * tuning.thrust_retro
            ay -= fy * tuning.thrust_retro
        if controls.right:
            ax += rx * tuning.thrust_side
            ay += ry * tuning.thrust_side
        if controls.left:
            ax -= rx * tuning.thrust_side
            ay -= ry * tuning.thrust_side
        m = max(0.05, tuning.mass)
        return ax / m, ay / m

    def turn(self, controls: Controls, tuning: Tuning, dt: float) -> None:
        """Turn toward the aim at a limited rate. Turning never changes the drift."""
        if controls.aim is None:
            return
        diff = wrap_angle(controls.aim - self.angle)
        step = tuning.turn_rate * dt
        self.angle = wrap_angle(self.angle + max(-step, min(step, diff)))

    def step(self, controls: Controls, tuning: Tuning, dt: float, world_w: float, world_h: float) -> None:
        self.turn(controls, tuning, dt)
        ax, ay = self.thrust(controls, tuning)
        self.vx += ax * dt
        self.vy += ay * dt
        # The drift damper bleeds off a little speed all the time.
        if tuning.damper > 0:
            keep = math.exp(-tuning.damper * dt)
            self.vx *= keep
            self.vy *= keep
        # Soft cap: above top speed, the excess is pulled back quickly but not instantly.
        speed = self.speed
        if speed > tuning.top_speed > 0:
            excess = speed - tuning.top_speed
            new_speed = tuning.top_speed + excess * math.exp(-SOFT_CAP_PULL * dt)
            self.vx *= new_speed / speed
            self.vy *= new_speed / speed
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.ux += self.vx * dt
        self.uy += self.vy * dt
        self.x %= world_w
        self.y %= world_h
