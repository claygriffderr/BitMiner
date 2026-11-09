"""The space station screen in Secure the Base, drawn by the approved art code (`art/station.py`).

Press E at the station and it opens on the right, so your ship, the station and anything heading
your way stay in view: the game keeps running. 1, 2 and 3 pick the Ship, Weapons and Tools pages,
W and S (or the arrow keys) pick a row, Enter buys it, and E or Esc closes it. The mouse works too:
click a tab, a row or the buy button.

What's on each page and what it costs comes from the shop (`combat/shop.py`); this only turns
that into rows and the detail pane. The picture is rebuilt only when something on it changes.
"""

from __future__ import annotations

import arcade

from art import station as ST

from ..combat.shop import PAGE_ITEMS, PAGES, Shop
from ..combat.specs import WEAPONS
from ..graphics.textures import tex

LEFT = 640 - ST.PANEL_W - 6
TOP = 360 - 40              # 40 game pixels below the top of the screen, under the top bar
BOTTOM = TOP - ST.PANEL_H
BLINK_HZ = 3

NAMES = {"shield": "SHIELD", "armor": "ARMOR", "boost": "BOOST", "repair": "HEALTH", "auto": "AUTO CANNON",
         "sniper": "SNIPER", "missiles": "MISSILES", "laser": "LASER", "drill": "DRILL", "mine": "MINE",
         "sentry_auto": "AUTO SENTRY", "sentry_sniper": "SNIPER SENTRY", "sentry_missile": "MISSILE SENTRY"}
ABOUT = {
    "shield": "SOAKS UP HITS, THEN RECHARGES A FEW SECONDS AFTER THE LAST ONE. 3 LEVELS.",
    "armor": "STOPS PART OF EVERY HIT TO YOUR HULL. 3 LEVELS.",
    "boost": "HOLD SHIFT FOR A BURST OF SPEED. RECHARGES AFTER A SHORT PAUSE. 3 LEVELS.",
    "repair": "PATCHES UP HALF YOUR HULL.",
    "auto": "YOUR STARTING GUN: FAST, LIGHT SHOTS. ITS 3 UPGRADE LEVELS COME NEXT SPRINT.",
    "sniper": "SLOW, HARD-HITTING SHOTS THAT GO THROUGH {pierce} ENEMIES.",
    "missiles": "HOMING MISSILES THAT BLAST WHAT'S AROUND THEM. CLICK FOR ONE, OR HOLD TO KEEP FIRING.",
    "laser": "HOLD FIRE {charge:g} SECONDS TO CHARGE IT, THEN SWEEP THE BEAM. YOU CAN TURN BUT NOT MOVE WHILE "
             "IT CHARGES. {charges} CHARGES THAT COME BACK SLOWLY.",
    "drill": "PRESS F NEXT TO AN ASTEROID WITH ORE. IT DIGS UNTIL ITS HOLD IS FULL, THEN WAITS FOR YOU. "
             "THE ASTEROID CRUMBLES ONCE IT'S EMPTY AND TAKES ITS DRILLS WITH IT.",
    "mine": "HOLD G TO LAY EXPLOSIVE MINES. THEY GO OFF WHEN AN ENEMY FLIES OVER ONE.",
    "sentry_auto": "A TURRET YOU PLACE WITH R. IT NEVER MOVES, BUT ENEMIES CAN DESTROY IT. 3 TIERS.",
    "sentry_sniper": "A LONG-RANGE TURRET YOU PLACE WITH R. 3 TIERS.",
    "sentry_missile": "A MISSILE TURRET YOU PLACE WITH R. 3 TIERS.",
}
BLOCKED = {"OWNED": "OWNED", "SOON": "COMING NEXT SPRINT", "MAX": "YOU HAVE THE MOST"}


def page_content(game, page: str, selected: int) -> tuple[list[ST.Row], ST.Detail]:
    """The rows of a page and the detail pane for the selected one, from what the shop offers now."""
    shop: Shop = game.shop
    rows = []
    offers = shop.offers(page)
    for o in offers:
        rows.append(_row(game, o))
    o = offers[max(0, min(selected, len(offers) - 1))]
    return rows, _detail(game, o)


def _counts(game) -> dict:
    shop = game.shop
    st = game.stage
    return {"hull": int(round(100 * st.hull / st.hull_max)), "missiles": shop.missiles_carried(),
            "carried": game.drills_carried, "out": len(game.drills)}


def _row(game, o) -> ST.Row:
    c = _counts(game)
    key = o.key
    name = NAMES[key]
    if key == "auto":
        return ST.Row(key, name, None, sub="OWNED, UPGRADES SOON", tag="SOON")
    if o.soon:
        return ST.Row(key, name, None, sub="NEXT SPRINT", owned=False, tag="SOON")
    if key == "repair":
        return ST.Row(key, name, o.price, sub=f"HULL {c['hull']}%", tag="FULL" if o.blocked else None)
    if key in ("sniper", "laser"):
        owned = o.blocked == "OWNED"
        sub = "OWNED" if owned else ("3 CHARGES" if key == "laser" else "NOT OWNED")
        return ST.Row(key, name, o.price, sub=sub, owned=owned)
    if key == "missiles":
        pack = int(Shop.item("missiles")["pack"])
        return ST.Row(key, name, o.price, sub=f"{c['missiles']} CARRIED  BUY {pack}",
                      tag="FULL" if o.blocked else None)
    if key == "drill":
        tag = "MAX" if o.blocked else ("FREE" if o.price == 0 else None)
        return ST.Row(key, name, o.price, sub=f"{c['carried']} CARRIED  {c['out']} OUT", tag=tag)
    return ST.Row(key, name, o.price)


def _detail(game, o) -> ST.Detail:
    c = _counts(game)
    key = o.key
    laser = WEAPONS["laser"]
    about = ABOUT[key].format(pierce=WEAPONS["sniper"].get("pierce", 3), charge=laser.get("charge_time", 2.0),
                              charges=laser["charges"])
    price = o.price if not o.blocked else None
    buy = BLOCKED.get(o.blocked, "BUY")
    stats, bars = [], []
    if key == "auto":
        sub = "OWNED"
        buy = "UPGRADES NEXT SPRINT"
    elif o.soon:
        sub = "COMING NEXT SPRINT"
    elif key == "repair":
        sub = f"HULL {c['hull']}%"
        restores = float(Shop.item("repair")["restores"])
        now = c["hull"] / 100
        bars = [("HULL", now, min(1.0, now + restores))]
        if o.blocked:
            buy = "HULL IS FULL"
    elif key in ("sniper", "laser"):
        sub = "OWNED" if o.blocked == "OWNED" else "NOT OWNED YET"
    elif key == "missiles":
        pack = int(Shop.item("missiles")["pack"])
        sub = f"{c['missiles']} CARRIED, UP TO {int(Shop.item('missiles')['max'])}"
        stats = [("CARRIED", str(c["missiles"]), str(c["missiles"] + pack))]
        buy = "CARRYING THE MOST" if o.blocked else f"BUY {pack}"
    elif key == "drill":
        sub = f"{c['carried']} CARRIED  {c['out']} OUT"
        stats = [("CARRIED", str(c["carried"]), str(c["carried"] + 1))]
        if o.price == 0 and not o.blocked:
            buy = "TAKE A FREE ONE"
    else:
        sub = ""
    return ST.Detail(NAMES[key], sub, [about], [], stats=stats, bars=bars, buy=buy, price=price)


class StationScreen:
    def __init__(self, textures) -> None:
        self.textures = textures
        self.sprites = arcade.SpriteList()
        self.sprite: arcade.Sprite | None = None
        self.page = PAGES[0]
        self.selected = {p: 0 for p in PAGES}
        self.spots: dict = {}
        self._key = None
        self._n = 0
        self.visible = False

    # ------------------------------------------------------------ input

    def pick_page(self, i: int) -> None:
        if 0 <= i < len(PAGES):
            self.page = PAGES[i]

    def move(self, step: int) -> None:
        n = len(PAGE_ITEMS[self.page])
        self.selected[self.page] = (self.selected[self.page] + step) % n

    @property
    def item(self) -> str:
        return PAGE_ITEMS[self.page][self.selected[self.page]]

    def click_test(self, x: float, y: float) -> bool:
        """Whether game pixel (x, y) is over the screen (for the mouse pointer)."""
        return self.visible and 0 <= x - LEFT < ST.PANEL_W and 0 <= TOP - y < ST.PANEL_H

    def click(self, x: float, y: float) -> str | None:
        """A click at game pixel (x, y). Returns "buy" when it lands on the buy button, "inside" when
        it lands elsewhere on the screen, or None when it misses the screen."""
        px, py = x - LEFT, TOP - y
        if not (0 <= px < ST.PANEL_W and 0 <= py < ST.PANEL_H):
            return None
        sp = self.spots

        def inside(box) -> bool:
            bx, by, bw, bh = box
            return bx <= px < bx + bw and by <= py < by + bh

        for i, box in enumerate(sp.get("tabs", [])):
            if inside(box):
                self.pick_page(i)
                return "inside"
        for i, box in enumerate(sp.get("rows", [])):
            if inside(box):
                self.selected[self.page] = i
                return "inside"
        if "buy" in sp and inside(sp["buy"]):
            return "buy"
        return "inside"

    # ------------------------------------------------------------ each frame

    def update(self, game, time: float) -> None:
        self.visible = game.station_open
        if not self.visible:
            return
        rows, det = page_content(game, self.page, self.selected[self.page])
        warn = game.enemy_near()
        blink = (int(time * BLINK_HZ) % 2 == 0) if warn else True
        key = repr((self.page, self.selected[self.page], rows, det, game.credits, warn, blink))
        if key == self._key:
            return
        self._key = key
        spots: dict = {}
        img = ST.station_panel(self.page, rows, self.selected[self.page], det, game.credits, warn, blink, spots=spots)
        self.spots = spots
        self._n += 1
        texture = tex(img, f"station_screen_{self._n}")     # the old picture is let go once replaced
        if self.sprite is None:
            self.sprite = arcade.Sprite(texture)
            self.sprite.center_x = LEFT + ST.PANEL_W / 2
            self.sprite.center_y = BOTTOM + ST.PANEL_H / 2
            self.sprites.append(self.sprite)
        else:
            self.sprite.texture = texture

    def draw(self) -> None:
        if self.visible and self.sprite is not None:
            self.sprites.draw(pixelated=True)

