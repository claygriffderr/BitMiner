"""The space station's shop in Secure the Base: what each page sells, what it costs, whether you can
buy it right now, and buying it. No graphics: the station screen in `ui/station_screen.py` shows
these offers, and tests buy things directly.

- Items: drills, the sniper and laser (once each), missiles six at a time, health, mines one at a
  time, and sentries (each kind in tiers 1 to 3, the tier picked on the station screen).
- Upgrades: shield, armor and boost on the Ship page, and the auto cannon and the sniper (once
  you own it) on the Weapons page, each 3 levels bought in order (see `gear.py`).

Prices and limits come from `data/shop.json`.
"""

from __future__ import annotations

from dataclasses import dataclass

from .specs import SENTRIES, SHOP

PAGES = ("ship", "weapons", "tools")
PAGE_ITEMS = {
    "ship": ("shield", "armor", "boost", "repair"),
    "weapons": ("auto", "sniper", "missiles", "laser"),
    "tools": ("drill", "mine", "sentry_auto", "sentry_sniper", "sentry_missile"),
}
SOON: set[str] = set()
WEAPON_OF = {"sniper": "sniper", "laser": "laser", "missiles": "missile", "auto": "auto"}
SENTRY_ITEMS = ("sentry_auto", "sentry_sniper", "sentry_missile")
TIERS = 3


@dataclass
class Offer:
    key: str
    price: int | None          # what it costs now; None when there's nothing to buy
    blocked: str = ""          # why you can't buy it: OWNED, FULL, MAX, SOON (empty if you can, money aside)
    level: int | None = None   # upgrades: the level you own now (0 to 3)
    tier: int | None = None    # sentries: the tier this price is for

    @property
    def soon(self) -> bool:
        return self.blocked == "SOON"

    @property
    def upgrade(self) -> bool:
        return self.level is not None


class Shop:
    def __init__(self, game) -> None:
        self.game = game
        self.tier = {k: 1 for k in SENTRY_ITEMS}      # the tier picked for each sentry

    @staticmethod
    def item(key: str) -> dict:
        return SHOP["items"].get(key, {})

    @staticmethod
    def sentry_price(key: str, tier: int) -> int:
        return int(Shop.item(key)["prices"][tier - 1])

    def is_upgrade(self, key: str) -> bool:
        """Is this row an upgrade right now? (The sniper row sells the gun until you own it.)"""
        if key in ("shield", "armor", "boost", "auto"):
            return True
        return key == "sniper" and "sniper" in self.game.arsenal.owned

    def pick_tier(self, key: str, tier: int) -> None:
        if key in self.tier:
            self.tier[key] = max(1, min(TIERS, tier))

    # ------------------------------------------------------------ what's on offer

    def offer(self, key: str, tier: int | None = None) -> Offer:
        g = self.game
        st = g.stage
        if self.is_upgrade(key):
            lv = g.gear.level(key)
            price = g.gear.next_price(key)
            return Offer(key, price, "MAX" if price is None else "", level=lv)
        if key in SOON:
            return Offer(key, None, "SOON")
        if key in SENTRY_ITEMS:
            t = tier or self.tier[key]
            if len(g.defenses.sentries) + g.defenses.sentries_carried >= int(SENTRIES["max_out"]):
                return Offer(key, None, "MAX", tier=t)
            return Offer(key, self.sentry_price(key, t), tier=t)
        price = int(self.item(key).get("price", 0))
        if key in ("sniper", "laser"):
            if WEAPON_OF[key] in g.arsenal.owned:
                return Offer(key, None, "OWNED")
            return Offer(key, price)
        if key == "missiles":
            if self.missiles_carried() + int(self.item(key)["pack"]) > int(self.item(key)["max"]):
                return Offer(key, None, "FULL")
            return Offer(key, price)
        if key == "drill":
            if self.drills_owned() >= int(self.item(key)["max"]):
                return Offer(key, None, "MAX")
            return Offer(key, price)
        if key == "mine":
            if g.defenses.mines_carried >= int(self.item(key)["max"]):
                return Offer(key, None, "FULL")
            return Offer(key, price)
        if key == "repair":
            if st.hull >= st.hull_max - 1e-6:
                return Offer(key, None, "FULL")
            return Offer(key, price)
        return Offer(key, None, "SOON")

    def offers(self, page: str) -> list[Offer]:
        return [self.offer(k) for k in PAGE_ITEMS[page]]

    def can_buy(self, key: str, tier: int | None = None) -> bool:
        o = self.offer(key, tier)
        return o.price is not None and not o.blocked and o.price <= self.game.credits

    def missiles_carried(self) -> int:
        total = self.game.stage.missiles_total
        return 0 if total is None else total

    def drills_owned(self) -> int:
        return self.game.drills_carried + len(self.game.drills)

    # ------------------------------------------------------------ buying

    def buy(self, key: str, tier: int | None = None) -> bool:
        """Buy one of `key` (a sentry at `tier`, or the tier picked for it) if you can. Returns
        whether it went through."""
        g = self.game
        if not self.can_buy(key, tier):
            g.note(("no_sale", key))
            return False
        o = self.offer(key, tier)
        price = o.price
        st = g.stage
        g.credits -= price
        if o.upgrade:
            g.gear.raise_level(key)
            g.note(("bought", key, price, g.gear.level(key)))
            return True
        if key in ("sniper", "laser"):
            g.arsenal.own(WEAPON_OF[key])
        elif key == "missiles":
            if "missile" not in g.arsenal.owned:
                g.arsenal.own("missile")
            st.add_missiles(int(self.item(key)["pack"]))
        elif key == "drill":
            g.drills_carried += 1
        elif key == "mine":
            g.defenses.mines_carried += 1
        elif key in SENTRY_ITEMS:
            g.defenses.carried.append((key.split("_", 1)[1], o.tier))
            g.note(("bought", key, price, o.tier))
            return True
        elif key == "repair":
            st.hull = min(st.hull_max, st.hull + st.hull_max * float(self.item(key)["restores"]))
        g.note(("bought", key, price))
        return True

