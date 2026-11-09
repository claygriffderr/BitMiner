"""The follow camera: it sits on the ship, looks ahead along the drift (and in a fight toward the
mouse), and shakes on hard hits.

Pure Python, so it can be tested without a window.
"""

from __future__ import annotations

import math

from .flight import Ship
from .settings import Tuning

LEAD_TIME = 0.6         # At full camera lead, look this many seconds ahead along the drift.
MAX_LEAD = (190.0, 105.0)  # But never further than this from the ship, in game pixels.
LEAD_EASE = 3.0         # How quickly the look-ahead catches up, per second.
MAX_SHAKE = 7.0         # Offset in game pixels at full trauma and shake 1.
TRAUMA_DECAY = 1.6      # Trauma drains this much per second.


def _shake_noise(t: float, phase: float) -> float:
    """Smooth wobble in -1..1 from three detuned sine waves."""
    return (math.sin(t * 31.0 + phase) * 0.5
            + math.sin(t * 47.3 + phase * 2.1) * 0.3
            + math.sin(t * 83.9 + phase * 3.7) * 0.2)


class FollowCamera:
    def __init__(self) -> None:
        self.lead_x = 0.0
        self.lead_y = 0.0
        self.trauma = 0.0
        self.shake_x = 0.0
        self.shake_y = 0.0
        self._t = 0.0

    def reset(self) -> None:
        self.__init__()

    def kick(self, amount: float) -> None:
        """Add screen shake. Shake grows with the square of trauma, so small bumps stay small."""
        self.trauma = min(1.0, self.trauma + max(0.0, amount))

    def update(self, ship: Ship, tuning: Tuning, dt: float, aim: tuple[float, float] | None = None,
               hold: tuple[float, float] | None = None) -> None:
        """`aim` is the mouse's offset from the middle of the screen, in game pixels: in a fight the
        view leans that way (by the CAMERA AIM setting) so you can see what you are shooting at.
        `hold`, when given, is where the view centre should sit relative to the ship instead (the
        view eases there), for example to keep the ship beside the station screen."""
        if hold is not None:
            want_x, want_y = hold
        else:
            t = LEAD_TIME * tuning.camera_lead
            want_x, want_y = ship.vx * t, ship.vy * t
            if aim is not None:
                want_x += aim[0] * tuning.camera_aim
                want_y += aim[1] * tuning.camera_aim
            want_x = max(-MAX_LEAD[0], min(MAX_LEAD[0], want_x))
            want_y = max(-MAX_LEAD[1], min(MAX_LEAD[1], want_y))
        ease = 1 - math.exp(-LEAD_EASE * dt)
        self.lead_x += (want_x - self.lead_x) * ease
        self.lead_y += (want_y - self.lead_y) * ease

        self._t += dt
        self.trauma = max(0.0, self.trauma - TRAUMA_DECAY * dt)
        amp = MAX_SHAKE * tuning.shake * self.trauma ** 2
        self.shake_x = amp * _shake_noise(self._t, 0.0)
        self.shake_y = amp * _shake_noise(self._t, 1.7)

    def offset(self) -> tuple[float, float]:
        """Where the view centre sits relative to the ship."""
        return self.lead_x + self.shake_x, self.lead_y + self.shake_y
