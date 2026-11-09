"""The space station's shop in Secure the Base: what each page sells, what it costs, whether you can
buy it right now, and buying it. No graphics: the station screen in `ui/station_screen.py` shows
these offers, and tests buy things directly.

Prices and limits come from `data/shop.json`. Upgrades, mines and sentries are listed as coming
soon: they show on their pages but can't be bought until the next sprint.
"""

from __future__ import annotations

from dataclasses import dataclass

from .specs import SHOP

PAGES = ("ship", "weapons", "tools")
PAGE_ITEMS = {
    "ship": ("shield", "armor", "boost", "repair"),
    "weapons": ("auto", "sniper", "missiles", "laser"),
    "tools": ("drill", "mine", "sentry_auto", "sentry_sniper", "sentry_missile"),
}
SOON = {"shield", "armor", "boost", "auto", "mine", "sentry_auto", "sentry_sniper", "sentry_missile"}
WEAPON_OF = {"sniper": "sniper", "laser": "laser", "missiles": "missile", "auto": "auto"}


@dataclass
class Offer:
    key: str
    price: int | None          # what it costs now; None when there's nothing to buy
    blocked: str = ""          # why you can't buy it: OWNED, FULL, MAX, SOON (empty if you can, money aside)

    @property
    def soon(self) -> bool:
        return self.blocked == "SOON"


class Shop:
    def __init__(self, game) -> None:
        self.game = game

    @staticmethod
    def item(key: str) -> dict:
        return SHOP["items"].get(key, {})

    # ------------------------------------------------------------ what's on offer

    def offer(self, key: str) -> Offer:
        g = self.game
        st = g.stage
        if key == "auto":
            return Offer(key, None, "SOON")           # owned from the start; its upgrades come next sprint
        if key in SOON:
            return Offer(key, None, "SOON")
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
            if self.drills_owned() == 0 and g.credits < price and self.item(key).get("free_when_broke", True):
                return Offer(key, 0)                  # never stuck: no drills and no money gets you one free
            return Offer(key, price)
        if key == "repair":
            if st.hull >= st.hull_max - 1e-6:
                return Offer(key, None, "FULL")
            return Offer(key, price)
        return Offer(key, None, "SOON")

    def offers(self, page: str) -> list[Offer]:
        return [self.offer(k) for k in PAGE_ITEMS[page]]

    def can_buy(self, key: str) -> bool:
        o = self.offer(key)
        return o.price is not None and not o.blocked and o.price <= self.game.credits

    # ------------------------------------------------------------ counts the shop shows

    def missiles_carried(self) -> int:
        total = self.game.stage.missiles_total
        return 0 if total is None else total

    def drills_owned(self) -> int:
        return self.game.drills_carried + len(self.game.drills)

    # ------------------------------------------------------------ buying

    def buy(self, key: str) -> bool:
        """Buy one of `key` if you can. Returns whether it went through."""
        g = self.game
        if not self.can_buy(key):
            g.note(("no_sale", key))
            return False
        price = self.offer(key).price
        st = g.stage
        g.credits -= price
        if key in ("sniper", "laser"):
            g.arsenal.own(WEAPON_OF[key])
        elif key == "missiles":
            if "missile" not in g.arsenal.owned:
                g.arsenal.own("missile")
            st.add_missiles(int(self.item(key)["pack"]))
        elif key == "drill":
            g.drills_carried += 1
        elif key == "repair":
            st.hull = min(st.hull_max, st.hull + st.hull_max * float(self.item(key)["restores"]))
        g.note(("bought", key, price))
        return True
