"""The weapon gallery's HUD: the scene list, the scene's name and notes, your shield and hull, your
missile rack, the mothership's health bar, and the controls line. Layout is in game pixels with y up.
"""

from __future__ import annotations

import arcade

from art import hud

from ..combat.specs import WEAPONS
from ..graphics.textures import GameTextures, tex
from ..gallery import scenes as SC
from .panel import set_rect, solid
from .text import TextLayer, text_width

VIEW_W, VIEW_H = 640, 360

LIST_W = 158
LIST_X = VIEW_W - 6 - LIST_W
LIST_TOP = 354
ROW_H = 11
MAX_ROWS = 5
LIST_H = 34 + ROW_H * MAX_ROWS + 30

CONSOLE_W, CONSOLE_H = 112, 33
CONSOLE_X, CONSOLE_Y = VIEW_W - 6 - CONSOLE_W, 16
AMMO_H = 15
AMMO_Y = CONSOLE_Y + CONSOLE_H + 3   # the missile rack sits just above the shield console
BOSS_W = 236
BOSS_Y = 52
ABOUT_W = CONSOLE_X - 16          # notes wrap before they reach the shield console

HELP = [("ARROWS", " PICK   "), ("SPACE", " REPLAY   "), ("F", " FREE FLY   "), ("TAB", " TUNING   "),
        ("ESC", " MENU")]
HELP_FREE = [("WASD", " FLY   "), ("CLICK", " FIRE   "), ("1-4", " WEAPON   "), ("F", " AUTO PILOT   "),
             ("ESC", " MENU")]


def wrap(text: str, width: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and text_width(trial) > width:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


class Group:
    """Sprites and text that can be drawn together, and shifted as one for recordings."""

    def __init__(self, textures: GameTextures):
        self.sprites = arcade.SpriteList()
        self.text = TextLayer(textures)

    def draw(self) -> None:
        self.sprites.draw(pixelated=True)
        self.text.draw()


class GalleryHud:
    def __init__(self, textures: GameTextures):
        self.textures = textures
        self.main = Group(textures)
        self.console = Group(textures)
        self.ammo = Group(textures)
        self.boss = Group(textures)
        self.missiles = None
        self.cursor = arcade.SpriteList()
        self._boss_tex: dict = {}
        self.boss_health = None
        self._shown_health = 1.0

        # ---- the scene list, top right
        m = self.main
        back = arcade.Sprite(tex(hud.panel(LIST_W, LIST_H, alpha=225), "gallery_list"))
        back.center_x, back.center_y = LIST_X + LIST_W / 2, LIST_TOP - LIST_H / 2
        m.sprites.append(back)
        self.left_arrow = m.text.label("<", LIST_X + 7, LIST_TOP - 12, "hud_dim")
        self.right_arrow = m.text.label(">", LIST_X + LIST_W - 7, LIST_TOP - 12, "hud_dim", "right")
        self.column = m.text.label("", LIST_X + LIST_W // 2, LIST_TOP - 12, "ion_white", "center")
        self.group = m.text.label("", LIST_X + LIST_W // 2, LIST_TOP - 22, "hud_dim", "center")
        m.sprites.append(solid(LIST_X + 5, LIST_TOP - 27, LIST_W - 10, 1, "console_edge"))
        self.row_bars = []
        self.row_labels = []
        for i in range(MAX_ROWS):
            y = LIST_TOP - 34 - (i + 1) * ROW_H
            bar = solid(LIST_X + 4, y, LIST_W - 8, ROW_H - 1, "console_edge")
            m.sprites.append(bar)
            self.row_bars.append(bar)
            self.row_labels.append(m.text.label("", LIST_X + 12, y + 2, "hud_text"))
        foot = LIST_TOP - LIST_H
        m.sprites.append(solid(LIST_X + 5, foot + 27, LIST_W - 10, 1, "console_edge"))
        self.mode = m.text.label("", LIST_X + 8, foot + 16, "hud_text")
        self.mode_hint = m.text.label("", LIST_X + LIST_W - 8, foot + 16, "hud_dim", "right")
        self.weapon = m.text.label("", LIST_X + 8, foot + 6, "hud_dim")

        # ---- the scene's name and notes, bottom left
        self.title = m.text.label("", 8, 38, "hud_text", shadow="console_black")
        self.about = [m.text.label("", 8, 28 - i * 9, "hud_dim", shadow="console_black") for i in range(2)]
        self.help_labels = []
        self._help = None

        # ---- shield and hull, bottom right
        c = self.console
        plate = arcade.Sprite(tex(hud.panel(CONSOLE_W, CONSOLE_H), "defense_console"))
        plate.center_x, plate.center_y = CONSOLE_X + CONSOLE_W / 2, CONSOLE_Y + CONSOLE_H / 2
        c.sprites.append(plate)
        self.bars = {}
        for i, (key, label, color, dim) in enumerate((("shield", "SHLD", "ion", "ion_dark"),
                                                      ("hull", "HULL", "hud_text", "console_mid"))):
            y = CONSOLE_Y + CONSOLE_H - 13 - i * 11
            c.text.label(label, CONSOLE_X + 6, y, "hud_dim")
            left, w = CONSOLE_X + 30, 56
            c.sprites.append(solid(left, y + 1, w, 5, "console_black"))
            c.sprites.append(solid(left + 1, y + 2, w - 2, 3, dim))
            fill = solid(left + 1, y + 2, w - 2, 3, color)
            shine = solid(left + 1, y + 4, w - 2, 1, "ion_white" if key == "shield" else "hull_outline")
            c.sprites.append(fill)
            c.sprites.append(shine)
            value = c.text.label("100", CONSOLE_X + CONSOLE_W - 6, y, "hud_text", "right")
            self.bars[key] = (left, w, y, fill, shine, value)

        # ---- the missile rack, above the console: a pip per missile, then a bar while it reloads
        a = self.ammo
        plate = arcade.Sprite(tex(hud.panel(CONSOLE_W, AMMO_H), "missile_rack"))
        plate.center_x, plate.center_y = CONSOLE_X + CONSOLE_W / 2, AMMO_Y + AMMO_H / 2
        a.sprites.append(plate)
        y = AMMO_Y + 4
        a.text.label("MSL", CONSOLE_X + 6, y, "hud_dim")
        salvo = int(WEAPONS["missile"]["salvo"])
        left, w = CONSOLE_X + 30, 56
        step = (w + 2) // salvo
        self.pips = []
        for i in range(salvo):
            x = left + i * step
            a.sprites.append(solid(x, y + 1, step - 2, 5, "console_black"))
            self.pips.append(solid(x + 1, y + 2, step - 4, 3, "ion"))
            a.sprites.append(self.pips[-1])
        self.rack_span = (left, step * salvo - 2, y)
        self.reload_bar = solid(left, y + 1, 1, 5, "ion_dark")
        self.reload_bar.visible = False
        a.sprites.append(self.reload_bar)
        self.ammo_value = a.text.label(str(salvo), CONSOLE_X + CONSOLE_W - 6, y, "hud_text", "right")

        # ---- the mothership's health, bottom centre
        self.boss_sprite = arcade.Sprite(self._boss_texture(1.0, 0.0))
        self.boss_sprite.center_x = VIEW_W / 2
        self.boss_sprite.center_y = BOSS_Y + 7.5
        self.boss.sprites.append(self.boss_sprite)

        self.cross = arcade.Sprite(textures.crosshair)
        self.arrow = arcade.Sprite(textures.pointer)
        self.cursor.append(self.cross)
        self.cursor.append(self.arrow)

    # ------------------------------------------------------------ state

    def _boss_texture(self, health: float, recent: float) -> arcade.Texture:
        inner = 150
        key = (int(round(health * inner)), int(round(recent * inner)))
        t = self._boss_tex.get(key)
        if t is None:
            t = tex(hud.boss_bar("MOTHERSHIP", key[0] / inner, key[1] / inner, BOSS_W), f"boss_{key[0]}_{key[1]}")
            self._boss_tex[key] = t
        return t

    def show_scene(self, scene: SC.Scene, auto: bool, weapon: str, hover_row: int | None = None) -> None:
        col = scene.column
        cols = SC.COLUMNS
        self.column.set(SC.column_label(col))
        weapons = [c for c in cols if c in WEAPONS]
        if col in WEAPONS:
            self.group.set(f"YOUR WEAPONS  {weapons.index(col) + 1}/{len(weapons)}")
        else:
            attacks = [c for c in cols if c not in WEAPONS]
            self.group.set(f"ENEMY ATTACKS  {attacks.index(col) + 1}/{len(attacks)}")
        rows = SC.rows_of(col)
        for i in range(MAX_ROWS):
            bar, label = self.row_bars[i], self.row_labels[i]
            if i < len(rows):
                on = rows[i] == scene.row
                label.set(("> " if on else "") + SC.row_label(rows[i]),
                          color="ion_white" if on else ("hud_text" if i == hover_row else "hud_dim"))
                label.visible = True
                bar.visible = on or i == hover_row
                bar.color = (74, 82, 98, 255) if on else (43, 49, 60, 255)
            else:
                label.visible = False
                bar.visible = False
        self.mode.set("AUTO PILOT" if auto else "FREE FLY", color="ion_white" if not auto else "hud_text")
        self.mode_hint.set("F: FREE FLY" if auto else "F: AUTO")
        self.weapon.set(f"WEAPON {WEAPONS[weapon]['label']}" if not auto else "SPACE REPLAYS")
        self.title.set(scene.title)
        lines = wrap(scene.about, ABOUT_W)[:2]
        for i, lab in enumerate(self.about):
            lab.set(lines[i] if i < len(lines) else "")
        self._set_help(HELP if auto else HELP_FREE)

    def _set_help(self, items) -> None:
        if items is self._help:
            return
        self._help = items
        for lab in self.help_labels:
            lab.set("")
        self.help_labels = []
        x = 8
        for key, what in items:
            self.help_labels.append(self.main.text.label(key, x, 5, "hud_text", shadow="console_black"))
            x += text_width(key) + 1
            self.help_labels.append(self.main.text.label(what.rstrip(), x, 5, "hud_dim", shadow="console_black"))
            x += text_width(what) + 1

    def update(self, dt: float, shield: float, shield_max: float, hull: float, hull_max: float,
               boss: float | None, missiles: tuple[int, float] | None = None) -> None:
        """`missiles` is (missiles loaded, reload done from 0 to 1, or 1 when not reloading), or None
        to hide the missile rack."""
        self.missiles = missiles
        if missiles is not None:
            loaded, reload = missiles
            left, span, y = self.rack_span
            reloading = loaded == 0
            for i, pip in enumerate(self.pips):
                pip.visible = i < loaded
            set_rect(self.reload_bar, left, y + 1, round(span * reload) if reloading else 0, 5)
            self.ammo_value.set("RLD" if reloading else str(loaded), color="hud_dim" if reloading else "hud_text")
        for key, value, top in (("shield", shield, shield_max), ("hull", hull, hull_max)):
            left, w, y, fill, shine, label = self.bars[key]
            frac = max(0.0, min(1.0, value / max(1.0, top)))
            n = round(frac * (w - 2))
            set_rect(fill, left + 1, y + 2, n, 3)
            set_rect(shine, left + 1, y + 4, n, 1)
            label.set(f"{value:.0f}", color="hud_text" if value > 0 else "danger_pink")
        self.boss_health = boss
        if boss is None:
            self._shown_health = 1.0
        else:
            # Health just lost lingers in pale cyan, then drains down to the real value.
            self._shown_health = max(boss, self._shown_health - dt * 0.35)
            self.boss_sprite.texture = self._boss_texture(boss, self._shown_health - boss)

    def set_cursor(self, x: float, y: float, over_ui: bool, visible: bool) -> None:
        self.cross.visible = visible and not over_ui
        self.arrow.visible = visible and over_ui
        self.cross.center_x, self.cross.center_y = int(x) + 0.5, int(y) + 0.5
        self.arrow.center_x = int(x) + self.arrow.width / 2
        self.arrow.center_y = int(y) + 1 - self.arrow.height / 2

    # ------------------------------------------------------------ input

    def contains(self, x: float, y: float) -> bool:
        return LIST_X <= x < LIST_X + LIST_W and LIST_TOP - LIST_H <= y < LIST_TOP

    def hit(self, x: float, y: float):
        """What is under the mouse: ("column", -1 or 1), ("row", index), ("mode",) or None."""
        if not self.contains(x, y):
            return None
        if y >= LIST_TOP - 27:
            if x < LIST_X + 40:
                return ("column", -1)
            if x >= LIST_X + LIST_W - 40:
                return ("column", 1)
            return None
        for i in range(MAX_ROWS):
            bottom = LIST_TOP - 34 - (i + 1) * ROW_H
            if bottom <= y < bottom + ROW_H:
                return ("row", i)
        if y < LIST_TOP - LIST_H + 27:
            return ("mode",)
        return None

    # ------------------------------------------------------------ drawing

    def draw(self) -> None:
        self.main.draw()
        self.console.draw()
        if self.missiles is not None:
            self.ammo.draw()
        if self.boss_health is not None:
            self.boss.draw()

    def draw_cursor(self) -> None:
        self.cursor.draw(pixelated=True)
