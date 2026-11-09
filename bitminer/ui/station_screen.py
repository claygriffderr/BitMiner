"""The space station screen in Secure the Base, drawn by the approved art code (`art/station.py`).

Press E at the station and it opens on the right, so your ship, the station and anything heading
your way stay in view: the game keeps running. 1, 2 and 3 pick the Ship, Weapons and Tools pages,
W and S (or the arrow keys) pick a row, A and D pick a sentry's tier, Enter buys it, and E or Esc
closes it. The mouse works too:
click a tab, a row or the buy button.

What's on each page and what it costs comes from the shop (`combat/shop.py`); this only turns
that into rows and the detail pane. The picture is rebuilt only when something on it changes.
"""

from __future__ import annotations

from functools import lru_cache

import arcade

from art import hud
from art import station as ST

from ..combat.shop import PAGE_ITEMS, PAGES, SENTRY_ITEMS, Shop
from ..combat.specs import SENTRIES, SHOP, WEAPONS
from ..graphics.textures import tex

LEFT = 640 - ST.PANEL_W - 6
TOP = 360 - 40              # 40 game pixels below the top of the screen, under the top bar
BOTTOM = TOP - ST.PANEL_H
BLINK_HZ = 3

NAMES = {"shield": "SHIELD", "armor": "ARMOR", "boost": "BOOST", "repair": "HEALTH", "auto": "AUTO CANNON",
         "sniper": "SNIPER", "missiles": "MISSILES", "laser": "LASER", "drill": "DRILL", "mine": "MINE",
         "sentry_auto": "AUTO SENTRY", "sentry_sniper": "SNIPER SENTRY", "sentry_missile": "MISSILE SENTRY"}
ABOUT = {
    "shield": "SOAKS UP HITS, THEN RECHARGES A FEW SECONDS AFTER THE LAST ONE. STRONGER SHIELDS TAKE LONGER TO "
              "RECHARGE.",
    "armor": "STOPS PART OF EVERY HIT TO YOUR HULL. HEAVIER ARMOR MAKES YOUR SHIP A LITTLE HEAVIER.",
    "boost": "HOLD SHIFT WHILE YOU FLY FOR MORE THRUST AND TOP SPEED. THE METER REFILLS AFTER A SHORT PAUSE.",
    "repair": "PATCHES UP HALF YOUR HULL.",
    "auto": "YOUR STARTING GUN: FAST, LIGHT SHOTS. EACH LEVEL HITS 20% HARDER.",
    "sniper": "SLOW, HARD-HITTING SHOTS THAT GO THROUGH {pierce} ENEMIES.",
    "sniper_up": "EACH LEVEL HITS 20% HARDER. LEVELS 2 AND 3 PIERCE MORE ENEMIES.",
    "missiles": "HOMING MISSILES THAT BLAST WHAT'S AROUND THEM. CLICK FOR ONE, OR HOLD TO KEEP FIRING.",
    "laser": "HOLD FIRE {charge:g} SECONDS TO CHARGE IT, THEN SWEEP THE BEAM. YOU CAN TURN BUT NOT MOVE WHILE "
             "IT CHARGES. {charges} CHARGES THAT COME BACK SLOWLY.",
    "drill": "PRESS F NEXT TO AN ASTEROID WITH ORE. IT DIGS UNTIL ITS HOLD IS FULL, THEN WAITS FOR YOU. "
             "THE ASTEROID CRUMBLES ONCE IT'S EMPTY AND TAKES ITS DRILLS WITH IT.",
    "mine": "HOLD G TO LAY THEM BEHIND YOU: HOLD STILL FOR A PILE, KEEP FLYING FOR A LINE. ONE GOES OFF WHEN AN "
            "ENEMY FLIES RIGHT OVER IT. IT NEVER HURTS YOU OR YOUR THINGS.",
    "sentry_auto": "PLACE IT WITH R. FIRES QUICK PELLETS. ENEMIES CAN DESTROY IT.",
    "sentry_sniper": "PLACE IT WITH R. LONG-RANGE ROUNDS THAT GO THROUGH {pierce} ENEMIES.",
    "sentry_missile": "PLACE IT WITH R. FIRES SALVOS OF {salvo} HOMING MISSILES.",
}
BLOCKED = {"OWNED": "OWNED", "SOON": "COMING NEXT SPRINT", "MAX": "YOU HAVE THE MOST"}
LEVEL_WORDS = {"shield": ("WEAK", "STRONG", "TOUGHEST")}


def page_content(game, page: str, selected: int) -> tuple[list[ST.Row], ST.Detail]:
    """The rows of a page and the detail pane for the selected one, from what the shop offers now."""
    shop: Shop = game.shop
    rows = []
    offers = shop.offers(page)
    for o in offers:
        rows.append(_row(game, o))
    o = offers[max(0, min(selected, len(offers) - 1))]
    return rows, _detail(game, o)


def hints(page: str, selected: int) -> list[tuple[str, str]]:
    """The key hints along the bottom of the screen."""
    keys = [("1-3", "PAGE"), ("W/S", "PICK")]
    if PAGE_ITEMS[page][selected] in SENTRY_ITEMS:
        keys.append(("A/D", "TIER"))
    return keys + [("ENTER", "BUY"), ("E", "LEAVE")]


def _counts(game) -> dict:
    shop = game.shop
    st = game.stage
    d = game.defenses
    out = {k: 0 for k in SENTRY_ITEMS}
    held = {k: 0 for k in SENTRY_ITEMS}
    for s in d.sentries:
        out["sentry_" + s.gun] += 1
    for gun, _ in d.carried:
        held["sentry_" + gun] += 1
    return {"hull": int(round(100 * st.hull / st.hull_max)), "missiles": shop.missiles_carried(),
            "carried": game.drills_carried, "out": len(game.drills), "mines": d.mines_carried,
            "mines_out": len(st.mines), "sentries_held": held, "sentries_out": out}


def _pct(v: float) -> str:
    return f"{int(round(v * 100))}%"


def _row(game, o) -> ST.Row:
    c = _counts(game)
    key = o.key
    name = NAMES[key]
    if o.upgrade:
        return ST.Row(key, name, o.price, level=o.level)
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
        tag = "MAX" if o.blocked else None
        return ST.Row(key, name, o.price, sub=f"{c['carried']} CARRIED  {c['out']} OUT", tag=tag)
    if key == "mine":
        most = int(Shop.item("mine")["max"])
        return ST.Row(key, name, o.price, sub=f"{c['mines']}/{most} CARRIED  {c['mines_out']} OUT",
                      tag="FULL" if o.blocked else None)
    if key in SENTRY_ITEMS:
        held, out = c["sentries_held"][key], c["sentries_out"][key]
        sub = f"{held} CARRIED  {out} OUT" if held or out else f"FROM {Shop.sentry_price(key, 1):,}"
        return ST.Row(key, name, o.price, sub=sub, tag="MAX" if o.blocked else None)
    return ST.Row(key, name, o.price)


def _steps(o, values: list[str], prices: list[int], art=None) -> list[ST.Step]:
    out = []
    for i in range(3):
        state = "owned" if i < o.level else ("next" if i == o.level else "locked")
        out.append(ST.Step(f"LV{i + 1}", values[i], int(prices[i]), state, art=None if art is None else art[i]))
    return out


@lru_cache(maxsize=None)
def _strength_art(v: float):
    return hud.bar(40, v, "ion", "console_mid")


@lru_cache(maxsize=None)
def _tier_art(gun: str, tier: int):
    return ST._tier_art(gun, tier)


def _upgrade_detail(game, o) -> ST.Detail:
    key = o.key
    lv = o.level
    up = SHOP["upgrades"][key]
    prices = up["prices"]
    nxt = min(lv, 2)                       # the level the next purchase gives, as an index
    sub = f"LEVEL {lv} OF 3" if lv else "NOT UPGRADED YET"
    stats, bars, art = [], [], None
    if key == "shield":
        strength = up["strength"]
        top = float(strength[-1])
        values = list(LEVEL_WORDS["shield"])
        art = [_strength_art(round(float(v) / top, 2)) for v in strength]
        now = float(strength[lv - 1]) / top if lv else 0.0
        bars = [("STRENGTH", now, float(strength[nxt]) / top)]
        stats = [("RECHARGE", f"{up['delay'][lv - 1]:g}S" if lv else "-", f"{up['delay'][nxt]:g}S")]
        if not lv:
            sub = "NO SHIELD YET"
    elif key == "armor":
        block = up["block"]
        values = [_pct(float(b)) for b in block[1:]]
        stats = [("BLOCKS", _pct(float(block[lv])), _pct(float(block[min(lv + 1, 3)])))]
        if not lv:
            sub = "STARTING ARMOR"
    elif key == "boost":
        gain = up["gain"]
        values = [f"+{_pct(float(g))}" for g in gain]
        now = f"+{_pct(float(gain[lv - 1]))}" if lv else "NONE"
        stats = [("TOP SPEED", now, f"+{_pct(float(gain[nxt]))}"), ("THRUST", now, f"+{_pct(float(gain[nxt]))}")]
        if not lv:
            sub = "NO BOOST YET"
    else:
        dmg = up["damage"]
        values = [f"X{float(d):g}" for d in dmg]
        stats = [("DAMAGE", f"X{float(dmg[lv - 1]):g}" if lv else "X1", f"X{float(dmg[nxt]):g}")]
        if key == "sniper":
            pierce = up["pierce"]
            values = [f"X{float(d):g}\nPIERCE {p}" for d, p in zip(dmg, pierce)]
            base = int(WEAPONS["sniper"]["pierce"])
            stats.append(("PIERCE", str(pierce[lv - 1] if lv else base), str(pierce[nxt])))
    about = ABOUT["sniper_up" if key == "sniper" else key]
    if o.blocked == "MAX":
        return ST.Detail(NAMES[key], "LEVEL 3 OF 3", [about], _steps(o, values, prices, art), buy="FULLY UPGRADED",
                         price=None)
    return ST.Detail(NAMES[key], sub, [about], _steps(o, values, prices, art), stats=stats, bars=bars,
                     buy=f"BUY LV{lv + 1}", price=o.price)


def _sentry_detail(game, o) -> ST.Detail:
    key = o.key
    gun = key.split("_", 1)[1]
    spec = SENTRIES[gun]
    c = _counts(game)
    steps = [ST.Step(f"T{t}", "", Shop.sentry_price(key, t), "next" if t == o.tier else "locked",
                     art=_tier_art(gun, t)) for t in (1, 2, 3)]
    about = ABOUT[key].format(pierce=spec.get("pierce", 1), salvo=spec.get("salvo", 4))
    stats = [("HEALTH", f"{int(spec['health'][o.tier - 1])}   RANGE {int(spec['range'])}", "")]
    held, out = c["sentries_held"][key], c["sentries_out"][key]
    sub = f"{held} CARRIED  {out} OUT"
    if o.blocked:
        return ST.Detail(NAMES[key], sub, [about], steps, stats=stats, buy=BLOCKED["MAX"], price=None)
    return ST.Detail(NAMES[key], sub, [about], steps, stats=stats, buy=f"BUY T{o.tier}", price=o.price)


def _detail(game, o) -> ST.Detail:
    c = _counts(game)
    key = o.key
    if o.upgrade:
        return _upgrade_detail(game, o)
    if key in SENTRY_ITEMS:
        return _sentry_detail(game, o)
    laser = WEAPONS["laser"]
    about = ABOUT[key].format(pierce=WEAPONS["sniper"].get("pierce", 3), charge=laser.get("charge_time", 2.0),
                              charges=laser["charges"])
    price = o.price if not o.blocked else None
    buy = BLOCKED.get(o.blocked, "BUY")
    stats, bars = [], []
    if o.soon:
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
    elif key == "mine":
        most = int(Shop.item("mine")["max"])
        sub = f"{c['mines']}/{most} CARRIED  {c['mines_out']} OUT"
        stats = [("CARRIED", str(c["mines"]), str(c["mines"] + 1))]
        buy = "CARRYING THE MOST" if o.blocked else "BUY 1"
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
        """A click at game pixel (x, y). Returns "buy" when it lands on the buy button, "tier1" to
        "tier3" on a sentry's tier cards, "inside" when it lands elsewhere on the screen, or None when
        it misses the screen."""
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
        for i, box in enumerate(sp.get("steps", [])):
            if inside(box):
                return f"tier{i + 1}"
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
        img = ST.station_panel(self.page, rows, self.selected[self.page], det, game.credits, warn, blink, spots=spots,
                               hints=hints(self.page, self.selected[self.page]))
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

