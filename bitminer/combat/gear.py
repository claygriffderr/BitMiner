"""Your ship's upgrades in Secure the Base: shield, armor, boost, and auto cannon and sniper power.

Each has 3 levels, bought in order at the station (`shop.py`). This module holds the levels you
own, puts them into effect on the stage, and runs the boost meter. Every number comes from the
`upgrades` block of `data/shop.json`. No graphics.
"""

from __future__ import annotations

from dataclasses import replace

from ..settings import Tuning
from .specs import SHOP

UPGRADES = ("shield", "armor", "boost", "auto", "sniper")
MAX_LEVEL = 3


def spec(key: str) -> dict:
    return SHOP["upgrades"][key]


class Gear:
    def __init__(self, stage) -> None:
        self.stage = stage
        self.levels = {k: 0 for k in UPGRADES}
        self.boost = 1.0              # the boost meter, 0 to 1
        self.boosting = False         # boosting this step
        self.since_boost = 99.0       # seconds since you last boosted
        self.apply()

    def level(self, key: str) -> int:
        return self.levels[key]

    def next_price(self, key: str) -> int | None:
        """What the next level costs, or None at level 3."""
        lv = self.levels[key]
        return None if lv >= MAX_LEVEL else int(spec(key)["prices"][lv])

    def raise_level(self, key: str) -> None:
        self.levels[key] = min(MAX_LEVEL, self.levels[key] + 1)
        self.apply()
        if key == "shield":
            self.stage.shield = self.stage.shield_max      # a new shield comes fully charged
        if key == "boost":
            self.boost = 1.0

    def apply(self) -> None:
        """Put the levels you own into effect on the stage."""
        st = self.stage
        lv = self.levels
        if lv["shield"]:
            s = spec("shield")
            i = lv["shield"] - 1
            st.shield_max = float(s["strength"][i])
            st.shield_delay = float(s["delay"][i])
            st.shield_regen = float(s["regen"][i])
            st.shield_level = lv["shield"]
            st.shield = min(st.shield, st.shield_max)
        else:
            st.shield_max = 0.0
            st.shield = 0.0
        st.armor_block = float(spec("armor")["block"][lv["armor"]])
        for weapon in ("auto", "sniper"):
            st.damage_mult[weapon] = 1.0 if not lv[weapon] else float(spec(weapon)["damage"][lv[weapon] - 1])
        pierce = spec("sniper").get("pierce")
        if lv["sniper"] and pierce:
            st.sniper_pierce = int(pierce[lv["sniper"] - 1])

    @property
    def mass_factor(self) -> float:
        return float(spec("armor")["mass"][self.levels["armor"]])

    @property
    def boost_gain(self) -> float:
        lv = self.levels["boost"]
        return 0.0 if not lv else float(spec("boost")["gain"][lv - 1])

    # ------------------------------------------------------------ each step

    def step_boost(self, dt: float, want: bool) -> bool:
        """Drain the meter while you hold boost, refill it after a pause. Returns whether the
        ship is boosting this step."""
        s = spec("boost")
        on = want and self.levels["boost"] > 0 and self.boost > 0
        if on:
            self.boost = max(0.0, self.boost - dt / float(s["seconds"]))
            self.since_boost = 0.0
        else:
            self.since_boost += dt
            if self.since_boost >= float(s["delay"]):
                self.boost = min(1.0, self.boost + dt / float(s["refill"]))
        self.boosting = on
        return on

    def flight(self, tuning: Tuning) -> Tuning:
        """The flight settings for this step: more thrust and top speed while boosting, more mass
        with heavier armor."""
        mass = tuning.mass * self.mass_factor
        if not self.boosting:
            return tuning if mass == tuning.mass else replace(tuning, mass=mass)
        k = 1.0 + self.boost_gain
        return replace(tuning, mass=mass, thrust_main=tuning.thrust_main * k, thrust_side=tuning.thrust_side * k,
                       thrust_retro=tuning.thrust_retro * k, top_speed=tuning.top_speed * k)
