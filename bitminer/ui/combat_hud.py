"""The combat sandbox's HUD, laid out like the approved mock fight screen.

- Lower right: the ship console. Weapons on top (the one in hand large, filled to show its ammo or
  reload, the rest small and grey), then shield, hull and armor, then the ship plate.
- Top: kills on the left, the wave and the time to the next one in the middle, wave alerts below.
- Screen edges: faint arrows toward enemies that are off screen but close.
- Centre: SHIP DOWN while you wait to come back.

Layout is in game pixels with y up.
"""

from __future__ import annotations

import math

import arcade
from PIL import Image

from art import hud
from art import sprites as S
from art.palette import rgba

from ..combat.arsenal import ORDER
from ..combat.specs import DEFENSE, WEAPONS
from ..graphics.textures import GameTextures, tex
from .panel import set_rect, solid
from .text import TextLayer, text_width

VIEW_W, VIEW_H = 640, 360

CON_W, CON_H = 118, 92
CON_X, CON_Y = VIEW_W - 6 - CON_W, 6
CON_TOP = CON_Y + CON_H
ICON = {"auto": "auto", "sniper": "sniper", "missile": "explosive", "laser": "laser"}
ARROW_COLOR = {"infantry": "alien_green_hi", "guard": "steel_hi", "rapid": "danger_pink"}
ARROW_STEPS = 32           # arrow pictures are made for this many directions
ARROW_MARGIN = 10
ALERT_SHOW = 3.5           # seconds a wave alert stays up

HELP = [("WASD", " FLY  "), ("CLICK", " FIRE  "), ("1-4", "/"), ("WHEEL", " WEAPON  "),
        ("N", " NEXT WAVE  "), ("P", " PAUSE  "), ("TAB", " TUNING  "), ("ESC", " MENU")]


def clock_text(seconds: float) -> str:
    s = max(0, int(math.ceil(seconds)))
    return f"{s // 60}:{s % 60:02d}"


def ammo_line(sb) -> str:
    """What is left in the weapon in hand, in a few characters."""
    st = sb.stage
    arsenal = sb.arsenal
    w = arsenal.weapon
    if w == "missile":
        if st.missile_reload > 0:
            return "RELOAD"
        return f"{st.missiles_loaded}/{int(WEAPONS['missile']['salvo'])}"
    if w == "laser":
        if arsenal.unlimited_laser:
            return ""
        text = f"{arsenal.charges}/{arsenal.laser_max}"
        if arsenal.charges < arsenal.laser_max:
            text += f" +{clock_text(WEAPONS['laser']['recharge'] - arsenal.recharge)}"
        return text
    return ""


class CombatHud:
    def __init__(self, textures: GameTextures):
        self.textures = textures
        self.sprites = arcade.SpriteList()
        self.text = TextLayer(textures)
        self.arrows = arcade.SpriteList()
        self.cursor = arcade.SpriteList()
        self._arrow_tex: dict = {}
        self._alert_t = ALERT_SHOW
        self._icons = {}
        for w in ORDER:
            big = hud.weapon_icon(ICON[w])
            small = hud.weapon_icon(ICON[w], greyed=True).resize((9, 9), Image.NEAREST)
            self._icons[w] = (tex(big, f"wpn_big_{w}"), tex(small, f"wpn_small_{w}"))
        self._build_console()
        self._build_top()
        self._build_help()
        self.centre = self.text.label("", VIEW_W // 2, 206, "danger_pink_hi", "center", shadow="console_black")
        self.centre_sub = self.text.label("", VIEW_W // 2, 194, "hud_text", "center", shadow="console_black")
        self.paused = self.text.label("", VIEW_W // 2, 176, "ion_white", "center", shadow="console_black")
        self.fps = self.text.label("", VIEW_W - 6, VIEW_H - 12, "hud_dim", "right", shadow="console_black")
        self.cross = arcade.Sprite(textures.crosshair)
        self.pointer = arcade.Sprite(textures.pointer)
        self.cursor.append(self.cross)
        self.cursor.append(self.pointer)

    # ------------------------------------------------------------ building

    def _sprite(self, img: Image.Image, name: str, left: float, bottom: float) -> arcade.Sprite:
        s = arcade.Sprite(tex(img, name))
        s.center_x = left + img.width / 2
        s.center_y = bottom + img.height / 2
        self.sprites.append(s)
        return s

    def _build_console(self) -> None:
        # Weapon row: the one in hand large on the right, the others small and grey to its left.
        self._sprite(hud.panel(26, 26), "con_weapon", CON_X + CON_W - 26, CON_TOP - 26)
        self.ammo_box = (CON_X + CON_W - 24, CON_TOP - 24, 22, 22)
        self.ammo_fill = solid(*self.ammo_box, "ion_dark")
        self.ammo_fill.alpha = 150
        self.ammo_line = solid(self.ammo_box[0], self.ammo_box[1], 22, 1, "ion")
        self.sprites.append(self.ammo_fill)
        self.sprites.append(self.ammo_line)
        self.big_icon = arcade.Sprite(self._icons["auto"][0])
        self.big_icon.center_x = CON_X + CON_W - 26 + 6 + 6.5
        self.big_icon.center_y = CON_TOP - 6 - 6.5
        self.sprites.append(self.big_icon)
        self.small_icons = []
        for i in range(3):
            left = CON_X + 71 - 19 * i
            self._sprite(hud.panel(17, 17, "console_black"), "con_small", left, CON_TOP - 9 - 17)
            s = arcade.Sprite(self._icons["sniper"][1])
            s.center_x = left + 4 + 4.5
            s.center_y = CON_TOP - 9 - 4 - 4.5
            self.sprites.append(s)
            self.small_icons.append(s)
        self.text.label("WPN", CON_X + 15, CON_TOP - 14 - 7, "hud_dim")
        # What is in hand and how much is left, just above the console.
        self.weapon_name = self.text.label("", CON_X + CON_W, CON_TOP + 3, "hud_text", "right", shadow="console_black")
        self.weapon_ammo = self.text.label("", CON_X + CON_W, CON_TOP + 3, "ion_hi", "right", shadow="console_black")

        # Shield, hull and armor.
        prot_top = CON_TOP - 30
        self._sprite(hud.panel(CON_W, 36), "con_protection", CON_X, prot_top - 36)
        self.bars = {}
        armor_max = int(DEFENSE.get("armor_max", 5))
        rows = (("shield", "SHLD", "ion", "ion_dark"), ("hull", "HULL", "hud_text", "console_mid"),
                ("armor", "ARMR", "hull_hi", "console_mid"))
        for i, (key, label, color, dim) in enumerate(rows):
            y = prot_top - 4 - i * 10 - 7
            self.text.label(label, CON_X + 5, y, "hud_dim")
            left, w = CON_X + CON_W - 76, 70
            self.sprites.append(solid(left, y + 2, w, 4, "console_black"))
            back = solid(left + 1, y + 3, w - 2, 2, dim)
            fill = solid(left + 1, y + 3, w - 2, 2, color)
            shine = solid(left + 1, y + 4, w - 2, 1, "ion_white" if key == "shield" else color)
            for s in (back, fill, shine):
                self.sprites.append(s)
            if key == "armor":
                step = (w - 2) / armor_max
                for k in range(1, armor_max):
                    self.sprites.append(solid(left + 1 + round(k * step), y + 3, 1, 2, "console_black"))
            self.bars[key] = (left, w, y, back, fill, shine)

        # The ship plate, and how many times you have gone down.
        self._sprite(hud.panel(26, 24), "con_plate", CON_X + CON_W - 26, CON_Y)
        icon = S.tight(S.player_ship())
        self.ship_icon = self._sprite(icon, "con_ship", CON_X + CON_W - 26 + (26 - icon.width) // 2,
                                      CON_Y + (24 - icon.height) // 2)
        self.downs = self.text.label("DOWNS 0", CON_X + CON_W - 32, CON_Y + 9, "hud_dim", "right")

    def _build_top(self) -> None:
        self._sprite(hud.panel(116, 15), "top_left", 6, VIEW_H - 6 - 15)
        y = VIEW_H - 6 - 11
        self.text.label("KILLS", 11, y, "hud_dim")
        self.kills = self.text.label("0", 11 + text_width("KILLS") + 5, y, "ore")
        self.text.label("LEFT", 62, y, "hud_dim")
        self.alive = self.text.label("0", 62 + text_width("LEFT") + 5, y, "alien_green_hi")
        self.mid_w = 0
        self.mid = None
        self.wave = self.text.label("", 0, VIEW_H - 6 - 11, "hud_text")
        self.next_wave = self.text.label("", 0, VIEW_H - 6 - 11, "danger_pink_hi")
        self._mid_key = None
        self.alert_back = None
        self.alert = self.text.label("", VIEW_W // 2, VIEW_H - 25 - 11, "danger_pink_hi", "center")

    def _build_help(self) -> None:
        x = 8
        for key, what in HELP:
            self.text.label(key, x, 5, "hud_text", shadow="console_black")
            x += text_width(key) + 1
            if what.strip():
                self.text.label(what.rstrip(), x, 5, "hud_dim", shadow="console_black")
            x += text_width(what) + 1

    def _plate(self, attr: str, w: int, name: str, bottom: float, fill: str = "console_dark") -> None:
        """A centred top-bar plate `w` wide, rebuilt only when its width changes."""
        old = getattr(self, attr)
        if old is not None and old.width == w:
            return
        if old is not None:
            old.remove_from_sprite_lists()
        s = self._sprite(hud.panel(w, 15, fill), f"{name}_{w}", (VIEW_W - w) // 2, bottom)
        setattr(self, attr, s)

    # ------------------------------------------------------------ each frame

    def update(self, dt: float, sb) -> None:
        """Show the state of `sb`, a Sandbox."""
        st = sb.stage
        arsenal = sb.arsenal
        weapon = arsenal.weapon
        ready = {w: arsenal.ready(w) for w in ORDER}
        ammo_text = ammo_line(sb)
        # Weapons.
        x, y, w, h = self.ammo_box
        level = int(round(h * max(0.0, min(1.0, ready[weapon]))))
        set_rect(self.ammo_fill, x, y, w if level else 0, level)
        set_rect(self.ammo_line, x, y + level - 1, w if level else 0, 1)
        self.big_icon.texture = self._icons[weapon][0]
        others = [o for o in ORDER if o != weapon]
        for s, o in zip(self.small_icons, others):
            s.texture = self._icons[o][1]
            s.color = (255, 255, 255, 255) if ready[o] >= 1.0 else (150, 150, 150, 255)
        self.weapon_ammo.set(ammo_text)
        gap = text_width(ammo_text) + 6 if ammo_text else 0
        self.weapon_name.set(WEAPONS[weapon]["label"], x=CON_X + CON_W - gap)

        # Protection.
        armor_max = int(DEFENSE.get("armor_max", 5))
        low = st.hull < st.hull_max * 0.3
        values = {"shield": st.shield / st.shield_max, "hull": st.hull / st.hull_max,
                  "armor": st.armor / max(1, armor_max)}
        for key, (left, bw, by, back, fill, shine) in self.bars.items():
            n = round(max(0.0, min(1.0, values[key])) * (bw - 2))
            set_rect(fill, left + 1, by + 3, n, 2)
            set_rect(shine, left + 1, by + 4, n, 1)
            if key == "hull":
                blink = low and int(st.time * 4) % 2 == 0
                fill.color = rgba("danger_red" if low else "hud_text")
                shine.color = rgba("danger_pink" if low else "hud_text")
                back.color = rgba("danger_dark" if blink else "console_mid")
        self.ship_icon.alpha = 90 if st.ship_down else (120 if st.invulnerable > 0 and int(st.time * 10) % 2 else 255)
        self.downs.set(f"DOWNS {sb.downs}")

        # Top bar.
        self.kills.set(str(sb.kills))
        alive = sum(1 for e in st.enemies if e.alive and e.dying < 0)
        self.alive.set(str(alive))
        waves = sb.waves
        wave_txt = f"WAVE {waves.number}" if waves.number else "GET READY"
        next_txt = f"NEXT {clock_text(waves.timer)}"
        mid_w = text_width(wave_txt) + text_width(next_txt) + 22
        self._plate("mid", mid_w, "top_mid", VIEW_H - 6 - 15)
        left = (VIEW_W - mid_w) // 2
        self.wave.set(wave_txt, x=left + 6)
        self.next_wave.set(next_txt, x=left + 16 + text_width(wave_txt))
        for ev in st.events:
            if ev[0] == "wave":
                self._alert_t = 0.0
                self.alert.set(f"{ev[2]} INCOMING")
        self._alert_t += dt
        show = self._alert_t < ALERT_SHOW
        self.alert.visible = show and int(self._alert_t * 4) % 4 != 3
        if show:
            self._plate("alert_back", text_width(self.alert.text) + 12, "alert", VIEW_H - 25 - 15, "console_black")
        if self.alert_back is not None:
            self.alert_back.visible = show

        # Centre.
        if st.ship_down:
            self.centre.set("SHIP DOWN")
            self.centre_sub.set(f"BACK IN {max(0.0, sb.respawn_in):.1f}")
        else:
            self.centre.set("")
            self.centre_sub.set("")

    def show_paused(self, paused: bool) -> None:
        self.paused.set("PAUSED   P TO GO ON" if paused else "")

    def set_fps(self, fps: float | None) -> None:
        self.fps.set(f"FPS {fps:.0f}" if fps else "")

    def place_arrows(self, targets: list) -> None:
        """`targets` is [(dx, dy, kind, distance)] from the view centre, in game pixels."""
        while len(self.arrows) < len(targets):
            s = arcade.Sprite(self._arrow(0, "alien_green_hi"))
            self.arrows.append(s)
        for i, s in enumerate(self.arrows):
            if i >= len(targets):
                s.visible = False
                continue
            dx, dy, kind, d = targets[i]
            a = math.atan2(dy, dx)
            step = int(round(a / math.tau * ARROW_STEPS)) % ARROW_STEPS
            s.texture = self._arrow(step, ARROW_COLOR.get(kind, "alien_green_hi"))
            # Pinned to the edge of the screen, inside the top bar and the help line.
            left, right, bottom, top = ARROW_MARGIN, VIEW_W - ARROW_MARGIN, 22, VIEW_H - 28
            cx, cy = (left + right) / 2, (bottom + top) / 2
            k = min((right - cx) / abs(dx) if dx else 1e9, (top - cy) / abs(dy) if dy else 1e9)
            s.center_x = int(cx + dx * k) + 0.5
            s.center_y = int(cy + dy * k) + 0.5
            s.alpha = int(255 * max(0.3, min(0.85, 1.15 - d / 1100)))
            s.visible = True

    def _arrow(self, step: int, color: str) -> arcade.Texture:
        key = (step, color)
        t = self._arrow_tex.get(key)
        if t is None:
            angle = -360.0 * step / ARROW_STEPS      # the picture's angles run clockwise, y down
            t = tex(hud.edge_arrow(angle, color), f"arrow_{step}_{color}")
            self._arrow_tex[key] = t
        return t

    def set_cursor(self, x: float, y: float, over_ui: bool, visible: bool) -> None:
        self.cross.visible = visible and not over_ui
        self.pointer.visible = visible and over_ui
        self.cross.center_x, self.cross.center_y = int(x) + 0.5, int(y) + 0.5
        self.pointer.center_x = int(x) + self.pointer.width / 2
        self.pointer.center_y = int(y) + 1 - self.pointer.height / 2

    # ------------------------------------------------------------ drawing

    def draw(self) -> None:
        self.arrows.draw(pixelated=True)
        self.sprites.draw(pixelated=True)
        self.text.draw()

    def draw_cursor(self) -> None:
        self.cursor.draw(pixelated=True)
