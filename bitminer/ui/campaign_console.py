"""The ship console for Secure the Base, lower right, drawn by the approved art code
(`art.hud.campaign_console`): only the weapons you own, the one in hand large; shield (NONE until
you buy one), hull, armor and boost; the drills, mines and sentries you carry; and your downs.

The picture is rebuilt only when what it shows changes shape (a weapon bought or picked, a level
gained). Everything that moves every moment, the ammo fill, the bars and the counts, is drawn live
on top of it at the spots the art code reports.
"""

from __future__ import annotations

import arcade

from art import hud
from art.palette import rgba

from ..combat.specs import SHOP, WEAPONS
from ..graphics.textures import tex
from .panel import set_rect, solid
from .text import TextLayer

ART_NAME = {"auto": "auto", "sniper": "sniper", "missile": "missiles", "laser": "laser"}
BAR_COLOR = {"shield": ("ion", "ion_white"), "hull": ("hud_text", "hud_text"), "boost": ("ion_hi", "ion_white")}
MINES_MAX = int(SHOP["items"]["mine"]["max"])     # the mine slot reads n/5


class CampaignConsole:
    def __init__(self, textures, right: float, bottom: float) -> None:
        self.textures = textures
        self.right = right
        self.bottom = bottom
        self.sprites = arcade.SpriteList()
        self.live = arcade.SpriteList()
        self.text = TextLayer(textures)
        self.frame: arcade.Sprite | None = None
        self.key = None
        self.spots: dict = {}
        self.size = (0, 0)
        self._textures: dict = {}
        self.visible = True
        self._n = 0
        # Live parts, placed whenever the frame is rebuilt.
        self.ammo_fill = solid(0, 0, 22, 22, "ion_dark")
        self.ammo_fill.alpha = 150
        self.ammo_line = solid(0, 0, 22, 1, "ion")
        self.bars = {k: (solid(0, 0, 1, 1, c), solid(0, 0, 1, 1, shine)) for k, (c, shine) in BAR_COLOR.items()}
        self.pips = [solid(0, 0, 2, 2, "ion_hi") for _ in range(int(WEAPONS["laser"]["charges"]))]
        for s in (self.ammo_fill, self.ammo_line, *[p for pair in self.bars.values() for p in pair], *self.pips):
            self.live.append(s)
        self.labels = {name: self.text.label("", 0, 0, "hud_text", align)
                       for name, align in (("missiles_big", "right"), ("missiles_small", "right"),
                                           ("tool_drill", "left"), ("tool_mine", "left"), ("tool_sentry", "left"),
                                           ("downs", "right"))}

    # ------------------------------------------------------------ where things go

    @property
    def top(self) -> float:
        return self.bottom + self.size[1]

    @property
    def left(self) -> float:
        return self.right - self.size[0]

    def _rect(self, x: float, y: float, w: float, h: float) -> tuple[float, float, float, float]:
        """A box from the top left of the picture (y down) to game pixels (left, bottom, w, h)."""
        return self.left + x, self.bottom + self.size[1] - y - h, w, h

    def _text_at(self, x: float, y: float) -> tuple[float, float]:
        return self.left + x, self.bottom + self.size[1] - y - 7

    # ------------------------------------------------------------ each frame

    def update(self, game) -> None:
        st = game.stage
        arsenal = game.arsenal
        owned = tuple(ART_NAME[w] for w in arsenal.owned)
        current = ART_NAME.get(arsenal.weapon, "auto")
        gear = game.gear
        d = game.defenses
        low = st.hull < st.hull_max * 0.3
        shape = dict(shield_level=gear.level("shield"), armor_level=gear.level("armor"),
                     boost_level=gear.level("boost"), drills=game.drills_carried, mines=d.mines_carried,
                     sentries=d.sentries_carried)
        # The picture only changes with what's owned, which icons are lit and how wide the counts are.
        key = (owned, current, shape["shield_level"], shape["armor_level"], shape["boost_level"], low,
               *[(shape[k] > 0, len(str(shape[k]))) for k in ("drills", "mines", "sentries")], game.downs >= 10)
        if key != self.key:
            self._rebuild(key, owned, current, low, shape)
        self._update_live(game)

    def _rebuild(self, key, owned, current, low, shape) -> None:
        self.key = key
        cached = self._textures.get(key)
        if cached is None:
            spots: dict = {}
            img = hud.campaign_console(weapons=owned, current=current, mines_max=MINES_MAX, low_hull=low,
                                       blank=True, spots=spots, **shape)
            self._n += 1
            cached = self._textures[key] = (tex(img, f"campaign_console_{self._n}"), spots, img.size)
        texture, self.spots, self.size = cached
        if self.frame is None:
            self.frame = arcade.Sprite(texture)
            self.sprites.append(self.frame)
        else:
            self.frame.texture = texture
        self.frame.center_x = self.left + self.size[0] / 2
        self.frame.center_y = self.bottom + self.size[1] / 2
        for name, label in self.labels.items():
            spot = self.spots.get(name)
            label.visible = spot is not None and self.visible
            if spot is not None:
                x, y = self._text_at(*spot)
                label.set(x=x, y=y)

    def _update_live(self, game) -> None:
        st = game.stage
        arsenal = game.arsenal
        sp = self.spots
        # The weapon in hand fills up as it's ready to fire.
        x, y, w, h = self._rect(*sp["ammo"])
        level = int(round(h * max(0.0, min(1.0, arsenal.ready()))))
        set_rect(self.ammo_fill, x, y, w if level else 0, level)
        set_rect(self.ammo_line, x, y + level - 1, w if level else 0, 1)
        # Bars.
        values = {"shield": st.shield / st.shield_max if st.shield_max > 0 else 0.0,
                  "hull": st.hull / st.hull_max, "boost": game.gear.boost}
        low = st.hull < st.hull_max * 0.3
        for k, (fill, shine) in self.bars.items():
            spot = sp.get(k)
            if spot is None:
                fill.visible = shine.visible = False
                continue
            bx, by, bw, bh = self._rect(*spot)
            n = round(max(0.0, min(1.0, values[k])) * (bw - 2))
            set_rect(fill, bx + 1, by + 1, n, bh - 2)
            set_rect(shine, bx + 1, by + bh - 2, n, 1)
            if k == "hull":
                fill.color = shine.color = rgba("danger_red" if low else "hud_text")
        # Laser charges.
        spot = sp.get("laser_pips")
        for i, p in enumerate(self.pips):
            p.visible = spot is not None
            if spot is not None:
                px, py, _, _ = self._rect(spot[0] + i * 3, spot[1], 2, 2)
                set_rect(p, px, py, 2, 2)
                p.color = rgba("ion_hi" if i < arsenal.charges else "console_edge")
        # Counts.
        total = st.missiles_total
        missiles = "" if total is None else str(total)
        lb = self.labels
        lb["missiles_big"].set(missiles, color="hud_text" if total else "danger_pink_hi")
        lb["missiles_small"].set(missiles, color="hud_dim")
        lb["tool_drill"].set(str(game.drills_carried), color="hud_text" if game.drills_carried else "console_edge")
        mines, sentries = game.defenses.mines_carried, game.defenses.sentries_carried
        lb["tool_mine"].set(f"{mines}/{MINES_MAX}", color="hud_text" if mines else "console_edge")
        lb["tool_sentry"].set(str(sentries), color="hud_text" if sentries else "console_edge")
        lb["downs"].set(f"DOWNS {game.downs}", color="hud_dim")

    def show(self, visible: bool) -> None:
        if visible == self.visible:
            return
        self.visible = visible
        for name, label in self.labels.items():
            label.visible = visible and name in self.spots

    def draw(self) -> None:
        if not self.visible:
            return
        self.sprites.draw(pixelated=True)
        self.live.draw(pixelated=True)
        self.text.draw()

