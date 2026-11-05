"""The flight test's HUD: a speed and hit readout, the controls line, frame rate, and the cursor."""

from __future__ import annotations

import arcade

from art import hud

from ..graphics.textures import GameTextures, tex
from .panel import set_rect, solid
from .text import TextLayer, text_width

VIEW_W, VIEW_H = 640, 360

HELP = [("WASD", " BOOSTERS   "), ("MOUSE", " AIM   "), ("TAB", " TUNING   "), ("C", " CRT   "),
        ("R", " RESET SHIP   "), ("F11", " FULL SCREEN   "), ("ESC", " QUIT")]

CONSOLE_W, CONSOLE_H = 112, 33
HIT_SHOW = 2.5   # seconds a hit stays on the readout


class FlightHud:
    def __init__(self, textures: GameTextures):
        self.sprites = arcade.SpriteList()
        self.text = TextLayer(textures)
        self.cursor = arcade.SpriteList()

        # Controls along the bottom left: keys bright, what they do dim.
        x = 8
        for key, what in HELP:
            self.text.label(key, x, 5, "hud_text", shadow="console_black")
            x += text_width(key) + 1
            self.text.label(what.rstrip(), x, 5, "hud_dim", shadow="console_black")
            x += text_width(what) + 1

        # Speed and hit console, bottom right.
        left = VIEW_W - 6 - CONSOLE_W
        bottom = 16
        back = arcade.Sprite(tex(hud.panel(CONSOLE_W, CONSOLE_H), "speed_console"))
        back.center_x, back.center_y = left + CONSOLE_W / 2, bottom + CONSOLE_H / 2
        self.sprites.append(back)
        self.bar_left, self.bar_w, self.bar_y = left + 7, CONSOLE_W - 14, bottom + 15
        self.sprites.append(solid(self.bar_left, self.bar_y, self.bar_w, 5, "console_black"))
        self.sprites.append(solid(self.bar_left + 1, self.bar_y + 1, self.bar_w - 2, 3, "console_mid"))
        self.bar = solid(self.bar_left + 1, self.bar_y + 1, 1, 3, "ion")
        self.bar_shine = solid(self.bar_left + 1, self.bar_y + 3, 1, 1, "ion_white")
        self.sprites.append(self.bar)
        self.sprites.append(self.bar_shine)
        self.text.label("SPEED", self.bar_left, bottom + 23, "hud_dim")
        self.speed = self.text.label("0", self.bar_left + self.bar_w, bottom + 23, "hud_text", "right")
        self.text.label("LAST HIT", self.bar_left, bottom + 5, "hud_dim")
        self.hit = self.text.label("-", self.bar_left + self.bar_w, bottom + 5, "hud_dim", "right")
        self._hit_age = HIT_SHOW

        self.fps = self.text.label("", VIEW_W - 6, VIEW_H - 12, "hud_dim", "right", shadow="console_black")

        self.cross = arcade.Sprite(textures.crosshair)
        self.arrow = arcade.Sprite(textures.pointer)
        self.cursor.append(self.cross)
        self.cursor.append(self.arrow)
        self.arrow.visible = False

    def show_hit(self, force: float) -> None:
        self.hit.set(f"{force:.0f}", color="ion_white")
        self._hit_age = 0.0

    def update(self, dt: float, speed: float, top_speed: float, fps: float | None) -> None:
        self.speed.set(f"{speed:.0f}")
        frac = min(1.0, speed / max(1.0, top_speed))
        w = round(frac * (self.bar_w - 2))
        set_rect(self.bar, self.bar_left + 1, self.bar_y + 1, w, 3)
        set_rect(self.bar_shine, self.bar_left + 1, self.bar_y + 3, w, 1)
        self._hit_age += dt
        if self._hit_age > 0.4:
            self.hit.set(color="hud_text" if self._hit_age < HIT_SHOW else "hud_dim")
        if fps is not None:
            self.fps.set(f"{fps:.0f} FPS")

    def set_cursor(self, x: float, y: float, over_ui: bool) -> None:
        self.cross.visible = not over_ui
        self.arrow.visible = over_ui
        # Whole game pixels, so the cursor stays crisp.
        self.cross.center_x, self.cross.center_y = int(x) + 0.5, int(y) + 0.5
        self.arrow.center_x = int(x) + self.arrow.width / 2
        self.arrow.center_y = int(y) + 1 - self.arrow.height / 2

    def draw(self) -> None:
        self.sprites.draw(pixelated=True)
        self.text.draw()

    def draw_cursor(self) -> None:
        self.cursor.draw(pixelated=True)
