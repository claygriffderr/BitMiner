"""Your weapons in a fight: which one is in hand, when each can fire again, and the laser's charges.

The stage does the firing; this decides when. Holding the trigger keeps firing whatever is in hand:
the auto cannon at its fire rate, the sniper whenever it has cycled, missiles one at a time until
the rack is empty, and the laser once per press while it has a charge.
"""

from __future__ import annotations

from .specs import WEAPONS
from .stage import Enemy, Stage, dist

ORDER = ["auto", "sniper", "missile", "laser"]


class Arsenal:
    def __init__(self, stage: Stage, unlimited_laser: bool = False):
        self.stage = stage
        self.unlimited_laser = unlimited_laser
        self.weapon = "auto"
        self.reset()

    def reset(self) -> None:
        self.cooldown = 0.0
        self.beam = None
        self.charges = int(WEAPONS["laser"]["charges"])
        self.recharge = 0.0          # seconds toward the next laser charge
        self._held = False

    # ------------------------------------------------------------ choosing

    def select(self, weapon: str) -> None:
        if weapon in ORDER:
            self.weapon = weapon

    def cycle(self, step: int) -> None:
        self.weapon = ORDER[(ORDER.index(self.weapon) + step) % len(ORDER)]

    @property
    def laser_max(self) -> int:
        return int(WEAPONS["laser"]["charges"])

    def ready(self, weapon: str | None = None) -> float:
        """How ready a weapon is, 0 to 1, for the HUD's ammo fill."""
        w = weapon or self.weapon
        st = self.stage
        if w == "auto":
            return 1.0
        if w == "sniper":
            period = 1.0 / WEAPONS["sniper"]["fire_rate"]
            return 1.0 - min(1.0, self.cooldown / period) if self.weapon == "sniper" else 1.0
        if w == "missile":
            salvo = int(WEAPONS["missile"]["salvo"])
            if st.missile_reload > 0:
                return 1.0 - st.missile_reload / float(WEAPONS["missile"]["reload"])
            return st.missiles_loaded / salvo
        if self.unlimited_laser:
            return 1.0
        part = self.recharge / float(WEAPONS["laser"]["recharge"]) if self.charges < self.laser_max else 0.0
        return min(1.0, (self.charges + part) / self.laser_max)

    # ------------------------------------------------------------ firing

    def step(self, dt: float, trigger: bool, cursor: tuple[float, float] | None = None) -> None:
        st = self.stage
        self.cooldown = max(0.0, self.cooldown - dt)
        if self.charges < self.laser_max:
            self.recharge += dt
            if self.recharge >= WEAPONS["laser"]["recharge"]:
                self.charges += 1
                self.recharge = 0.0
        pressed = trigger and not self._held
        self._held = trigger
        if st.ship_down or not trigger:
            return
        ship = st.ship
        if self.weapon == "missile":
            if st.missile_ready:
                st.fire_missile(self._target(cursor or (ship.x, ship.y)))
            return
        if self.weapon == "laser":
            if self.beam is not None and not self.beam.done and self.beam in st.beams:
                return
            if not (pressed or self.unlimited_laser) or self.cooldown > 0:
                return
            if not self.unlimited_laser:
                if self.charges <= 0:
                    st.events.append(("empty", "laser"))
                    return
                self.charges -= 1
            self.beam = st.start_laser()
            w = WEAPONS["laser"]
            self.cooldown = w["warmup"] + w["duration"] + 0.35
            return
        if self.cooldown > 0:
            return
        if self.weapon == "auto":
            st.fire_auto()
        else:
            st.fire_sniper()
        self.cooldown = 1.0 / WEAPONS[self.weapon]["fire_rate"]

    def _target(self, point: tuple[float, float]) -> Enemy | None:
        live = self.stage.live_enemies
        if not live:
            return None
        return min(live, key=lambda e: dist(e.x, e.y, point[0], point[1]))
