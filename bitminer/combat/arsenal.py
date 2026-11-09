"""Your weapons in a fight: which one is in hand, when each can fire again, and the laser's charges.

The stage does the firing; this decides when. Holding the trigger keeps firing whatever is in hand:
the auto cannon at its fire rate, the sniper whenever it has cycled, missiles one at a time until
the pods are empty (a quick click fires just one), and the laser once per press while it has a
charge. In a fight the laser first charges for `charge_time` seconds while you hold fire: let go
early and it cancels without using a charge.

Only weapons you own can be picked: all of them in the sandbox, what you've bought in Secure the Base.
"""

from __future__ import annotations

import math

from ..flight import Controls
from .specs import WEAPONS
from .stage import Enemy, Stage, dist

ORDER = ["auto", "sniper", "missile", "laser"]
CANCEL_TIME = 0.4        # seconds the energy takes to scatter after you let go of a charge


class Arsenal:
    def __init__(self, stage: Stage, unlimited_laser: bool = False, owned=None, charge_up: bool | None = None):
        self.stage = stage
        self.unlimited_laser = unlimited_laser
        # The gallery's free-fly laser fires on the click; a real fight charges it first.
        self.charge_up = (not unlimited_laser) if charge_up is None else charge_up
        self.owned: list[str] = [w for w in ORDER if owned is None or w in owned]
        self.weapon = self.owned[0] if self.owned else "auto"
        self.reset()

    def reset(self) -> None:
        self.cooldown = 0.0
        self.beam = None
        self.charges = int(WEAPONS["laser"]["charges"])
        self.recharge = 0.0          # seconds toward the next laser charge
        self.charge = -1.0           # seconds into a laser charge-up, or -1
        self._held = False
        self.stage.charging = -1.0

    # ------------------------------------------------------------ choosing

    def own(self, weapon: str) -> None:
        """A weapon bought at the station: it goes in its slot, ready to pick."""
        if weapon in ORDER and weapon not in self.owned:
            self.owned = [w for w in ORDER if w in self.owned or w == weapon]
            if weapon == "laser":
                self.charges = self.laser_max
                self.recharge = 0.0

    def select(self, weapon: str) -> None:
        if weapon in self.owned and weapon != self.weapon:
            self.weapon = weapon
            self._cancel_charge()

    def cycle(self, step: int) -> None:
        if not self.owned:
            return
        i = self.owned.index(self.weapon) if self.weapon in self.owned else 0
        self.select(self.owned[(i + step) % len(self.owned)])

    @property
    def laser_max(self) -> int:
        return int(WEAPONS["laser"]["charges"])

    @property
    def charging(self) -> bool:
        """Charging the laser: your ship holds still and can only turn."""
        return self.charge >= 0

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
        if self.charging:
            return min(1.0, self.charge / float(WEAPONS["laser"]["charge_time"]))
        part = self.recharge / float(WEAPONS["laser"]["recharge"]) if self.charges < self.laser_max else 0.0
        return min(1.0, (self.charges + part) / self.laser_max)

    # ------------------------------------------------------------ firing

    def step(self, dt: float, trigger: bool, cursor: tuple[float, float] | None = None) -> None:
        st = self.stage
        self.cooldown = max(0.0, self.cooldown - dt)
        st.charge_cancel = max(0.0, st.charge_cancel - dt / CANCEL_TIME)
        if self.charges < self.laser_max and "laser" in self.owned:
            self.recharge += dt
            if self.recharge >= WEAPONS["laser"]["recharge"]:
                self.charges += 1
                self.recharge = 0.0
        pressed = trigger and not self._held
        self._held = trigger
        if self.charging:
            self._step_charge(dt, trigger)
            return
        if st.ship_down or not trigger or self.weapon not in self.owned:
            return
        ship = st.ship
        if self.weapon == "missile":
            if st.missile_ready:
                st.fire_missile(self._target(cursor or (ship.x, ship.y)))
            elif pressed and st.missiles_total == 0:
                st.events.append(("empty", "missile"))
            return
        if self.weapon == "laser":
            if self.beam is not None and not self.beam.done and self.beam in st.beams:
                return
            if not (pressed or self.unlimited_laser) or self.cooldown > 0:
                return
            if not self.unlimited_laser and self.charges <= 0:
                st.events.append(("empty", "laser"))
                return
            if self.charge_up:
                self.charge = 0.0
                st.charging = 0.0
                st.events.append(("charge", "laser"))
                return
            if not self.unlimited_laser:
                self.charges -= 1
            self._fire_laser(burst=False)
            return
        if self.cooldown > 0:
            return
        if self.weapon == "auto":
            st.fire_auto()
        else:
            st.fire_sniper()
        self.cooldown = 1.0 / WEAPONS[self.weapon]["fire_rate"]

    def _step_charge(self, dt: float, trigger: bool) -> None:
        st = self.stage
        if st.ship_down or not trigger:
            self._cancel_charge()
            return
        self.charge += dt
        need = float(WEAPONS["laser"]["charge_time"])
        st.charging = min(1.0, self.charge / need)
        if self.charge >= need:
            self.charge = -1.0
            st.charging = -1.0
            if not self.unlimited_laser:
                self.charges -= 1
            self._fire_laser(burst=True)

    def _cancel_charge(self) -> None:
        if not self.charging:
            return
        st = self.stage
        self.charge = -1.0
        st.charging = -1.0
        st.charge_cancel = 1.0
        st.events.append(("cancel", "laser"))

    def _fire_laser(self, burst: bool) -> None:
        self.beam = self.stage.start_laser(burst=burst)
        w = WEAPONS["laser"]
        self.cooldown = self.beam.warmup + w["duration"] + 0.35

    def _target(self, point: tuple[float, float]) -> Enemy | None:
        live = self.stage.live_enemies
        if not live:
            return None
        return min(live, key=lambda e: dist(e.x, e.y, point[0], point[1]))


def hold_still(arsenal: Arsenal, controls: Controls, dt: float) -> Controls:
    """While the laser charges your ship brakes to a stop and can only turn to aim."""
    if not arsenal.charging:
        return controls
    ship = arsenal.stage.ship
    keep = math.exp(-float(WEAPONS["laser"].get("charge_brake", 6.0)) * dt)
    ship.vx *= keep
    ship.vy *= keep
    return Controls(aim=controls.aim)
