"""The start menu: Secure the Base, Flight Test, Combat Sandbox, Weapon Gallery or Quit, over a slow drift through the asteroid field."""

from __future__ import annotations

import math

import arcade

from art import hud, pix, pixfont

from ..graphics.renderer import VIEW, FrameView
from ..graphics.textures import tex
from ..ui.panel import solid
from ..ui.text import TextLayer
from ..world import FlightWorld

ITEMS = [
    ("campaign", "SECURE THE BASE", "DRILL THE ASTEROIDS, SHOP AT THE STATION AND HOLD OUT AGAINST THE WAVES."),
    ("flight", "FLIGHT TEST", "FLY THE SHIP THROUGH THE ASTEROIDS AND TUNE HOW IT HANDLES."),
    ("sandbox", "COMBAT SANDBOX", "FIGHT WAVE AFTER WAVE OF ENEMIES IN THE ASTEROID FIELD."),
    ("gallery", "WEAPON GALLERY", "EVERY WEAPON, ENEMY ATTACK AND EXPLOSION, PLAYING ON A LOOP."),
    ("quit", "QUIT", "CLOSE THE GAME."),
]
BUTTON_W, BUTTON_H = 132, 15
BUTTON_GAP = 6
DRIFT = (14.0, 5.0)        # how fast the view drifts over the field, game pixels per second


def title_image():
    """BITMINER in the HUD font at four times size, cyan with a dark outline and a drop shadow."""
    face = pix.scale(pixfont.render("BITMINER", "ion_hi", spacing=1), 4)
    shade = pix.scale(pixfont.render("BITMINER", "ion_dark", spacing=1), 4)
    w, h = face.width + 4, face.height + 4
    from PIL import Image
    img = Image.new("RGBA", (w + 2, h + 2), (0, 0, 0, 0))
    img.alpha_composite(shade, (2, 6))
    img.alpha_composite(face, (2, 2))
    # A white top edge on every letter, like light catching it.
    a = img.load()
    top = pix.scale(pixfont.render("BITMINER", "ion_white", spacing=1), 4)
    t = top.load()
    for y in range(0, top.height, 4):
        for x in range(top.width):
            if t[x, y][3] and (y == 0 or not t[x, y - 1][3]):
                a[x + 2, y + 2] = t[x, y]
    return pix.outline(img, "console_black")


class MenuView(arcade.View):
    def __init__(self, window):
        super().__init__(window)
        self.world = FlightWorld(seed=window.args.seed)
        self.sprites = arcade.SpriteList()
        self.text = TextLayer(window.textures)
        self.cursor = arcade.SpriteList()
        self.time = 0.0
        self.selected = 0          # the newest screen: Secure the Base

        logo = arcade.Sprite(tex(title_image(), "menu_title"))
        logo.center_x = VIEW[0] / 2
        logo.center_y = 262
        self.sprites.append(logo)
        self.text.label("SPRINT 8 BUILD: UPGRADES, SENTRIES AND MINES", VIEW[0] // 2, 222, "hud_dim", "center",
                        shadow="console_black")

        n = len(ITEMS)
        plate_h = n * BUTTON_H + (n - 1) * BUTTON_GAP + 16
        plate = arcade.Sprite(tex(hud.panel(BUTTON_W + 16, plate_h, alpha=215), "menu_plate"))
        self.top = 196
        plate.center_x, plate.center_y = VIEW[0] / 2, self.top - plate_h / 2
        self.sprites.append(plate)
        self.buttons = []
        for i, (_, label, _) in enumerate(ITEMS):
            left = VIEW[0] // 2 - BUTTON_W // 2
            bottom = self.top - 8 - BUTTON_H - i * (BUTTON_H + BUTTON_GAP)
            frame = solid(left, bottom, BUTTON_W, BUTTON_H, "console_edge")
            face = solid(left + 1, bottom + 1, BUTTON_W - 2, BUTTON_H - 2, "console_mid")
            shine = solid(left + 1, bottom + BUTTON_H - 2, BUTTON_W - 2, 1, "console_hi")
            for s in (frame, face, shine):
                self.sprites.append(s)
            text = self.text.label(label, VIEW[0] // 2, bottom + 4, "hud_text", "center")
            self.buttons.append((left, bottom, face, text))
        self.about = self.text.label("", VIEW[0] // 2, self.top - plate_h - 14, "hud_text", "center",
                                     shadow="console_black")
        self.text.label("UP/DOWN PICK   ENTER START   C CRT   F11 FULL SCREEN   ESC QUIT", VIEW[0] // 2, 6,
                        "hud_dim", "center", shadow="console_black")

        self.arrow = arcade.Sprite(window.textures.pointer)
        self.cursor.append(self.arrow)
        self._show()

    def _show(self) -> None:
        for i, (left, bottom, face, text) in enumerate(self.buttons):
            on = i == self.selected
            face.color = (74, 82, 98, 255) if on else (43, 49, 60, 255)
            text.set(color="ion_white" if on else "hud_text")
        self.about.set(ITEMS[self.selected][2])

    def _button_at(self, x: float, y: float) -> int | None:
        for i, (left, bottom, _, _) in enumerate(self.buttons):
            if left <= x < left + BUTTON_W and bottom <= y < bottom + BUTTON_H:
                return i
        return None

    # ------------------------------------------------------------ input

    def on_show_view(self):
        w = self.window
        w.renderer.set_field(self.world.field)
        w.renderer.under = w.no_particles
        w.renderer.over = w.no_particles
        w.panel.open = False

    def on_key_press(self, key, modifiers):
        if key in (arcade.key.UP, arcade.key.W):
            self.selected = (self.selected - 1) % len(ITEMS)
            self._show()
        elif key in (arcade.key.DOWN, arcade.key.S):
            self.selected = (self.selected + 1) % len(ITEMS)
            self._show()
        elif key in (arcade.key.ENTER, arcade.key.RETURN, arcade.key.SPACE) and not modifiers & arcade.key.MOD_ALT:
            self.window.go(ITEMS[self.selected][0])
            return True
        elif key == arcade.key.ESCAPE:
            self.window.close()
            return True
        elif key == arcade.key.TAB:
            return True          # no tuning panel on the menu

    def on_mouse_motion(self, x, y, dx, dy):
        i = self._button_at(*self.window.mouse)
        if i is not None and i != self.selected:
            self.selected = i
            self._show()

    def on_mouse_press(self, x, y, button, modifiers):
        i = self._button_at(*self.window.mouse)
        if i is not None:
            self.window.go(ITEMS[i][0])
            return True

    # ------------------------------------------------------------ loop

    def on_update(self, delta_time):
        w = self.window
        dt = w.frame_dt(delta_time)
        self.time += dt
        self.world.field.step(dt)
        mx, my = w.mouse
        self.arrow.center_x = int(mx) + self.arrow.width / 2
        self.arrow.center_y = int(my) + 1 - self.arrow.height / 2
        w.tick(dt, delta_time)

    def on_draw(self):
        w = self.window
        sx, sy = self.world.spawn
        x = sx + DRIFT[0] * self.time
        y = sy + 120 + DRIFT[1] * self.time + 18 * math.sin(self.time * 0.15)
        view = FrameView(cam_x=x % self.world.width, cam_y=y % self.world.height, cam_ux=x, cam_uy=y,
                         ship_x=0.0, ship_y=0.0, ship_angle=0.0, boosters=(), flame_frame=0, flash=0.0,
                         crt=w.settings.display.crt, ship_visible=False)
        w.renderer.draw(view, self.draw_ui)
        w.after_draw()
        return True

    def draw_ui(self) -> None:
        self.sprites.draw(pixelated=True)
        self.text.draw()
        if self.window.mouse_inside:
            self.cursor.draw(pixelated=True)
