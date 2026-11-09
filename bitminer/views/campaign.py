"""Secure the Base: the big map, home base and its space station, your drills and the mothership's waves.

Everything the combat sandbox has (WASD, mouse, 1 to 4, P, Tab), plus F to set a drill on the
asteroid next to you, E at the station to open its shop (E or Esc closes it), and N to call the
next wave now. Backspace starts a new game, on a map as big as the MAP SIZE slider says.
"""

from __future__ import annotations

import arcade

from ..combat.campaign import Campaign, autopilot
from ..flight import Controls
from ..graphics.renderer import VIEW
from ..ui.campaign_hud import CampaignHud
from ..ui import station_screen
from ..ui.station_screen import StationScreen
from .sandbox import SandboxView

PAGE_KEYS = {arcade.key.KEY_1: 0, arcade.key.KEY_2: 1, arcade.key.KEY_3: 2}
PICK_KEYS = {arcade.key.W: -1, arcade.key.UP: -1, arcade.key.S: 1, arcade.key.DOWN: 1}
BUY_KEYS = (arcade.key.ENTER, arcade.key.RETURN, arcade.key.NUM_ENTER, arcade.key.SPACE)


class CampaignView(SandboxView):
    HUD = CampaignHud
    MODE = "campaign"

    def __init__(self, window):
        self._set_drill = False
        self._size = None
        self.station = StationScreen(window.textures)
        super().__init__(window)

    def make_game(self) -> Campaign:
        tuning = self.window.settings.tuning
        self._size = tuning.map_size
        game = Campaign(self.sparks, self.smoke, tuning, scale=tuning.map_size)
        world = (game.world.width, game.world.height)
        self.sparks.world = world
        self.smoke.world = world
        self._set_drill = False
        return game

    # ------------------------------------------------------------ input

    def on_key_press(self, key, modifiers):
        game = self.sb
        if game.station_open:
            return self._station_key(key)
        if key == arcade.key.E:
            if not self.paused and not game.open_station():
                self.hud.notice("FLY UP TO THE STATION, THEN PRESS E")
            if game.station_open:
                self.down.clear()
                self.trigger = False
            return True
        if key == arcade.key.F and not self.paused:
            self._set_drill = True
            return True
        return super().on_key_press(key, modifiers)

    def _station_key(self, key) -> bool:
        game = self.sb
        st = self.station
        if key in (arcade.key.E, arcade.key.ESCAPE):
            game.close_station()
        elif key in PAGE_KEYS:
            st.pick_page(PAGE_KEYS[key])
        elif key in PICK_KEYS:
            st.move(PICK_KEYS[key])
        elif key in BUY_KEYS:
            game.shop.buy(st.item)
        elif key == arcade.key.P:
            self.paused = not self.paused
            self.hud.show_paused(self.paused)
        return True

    def on_key_release(self, key, modifiers):
        self.down.discard(key)

    def on_mouse_press(self, x, y, button, modifiers):
        game = self.sb
        if game.station_open:
            w = self.window
            if button == arcade.MOUSE_BUTTON_LEFT and not w.panel.contains(*w.mouse):
                if self.station.click(*w.mouse) == "buy":
                    game.shop.buy(self.station.item)
            return
        super().on_mouse_press(x, y, button, modifiers)

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        if self.sb.station_open:
            if scroll_y:
                self.station.move(-1 if scroll_y > 0 else 1)
            return True
        return super().on_mouse_scroll(x, y, scroll_x, scroll_y)

    # ------------------------------------------------------------ the game loop

    def pilot(self):
        if self.args.smoke:
            controls, trigger, cursor, set_drill = autopilot(self.sb, self.clock)
            self._set_drill = self._set_drill or set_drill
            return controls, trigger, cursor
        if self.sb.station_open:
            return Controls(), False, self.cursor_world()
        return super().pilot()

    def step_game(self, dt: float, controls: Controls, trigger: bool, cursor) -> list:
        events = self.sb.step(dt, controls, trigger, cursor, set_drill=self._set_drill)
        self._set_drill = False
        if self.window.settings.tuning.map_size != self._size:
            self._size = self.window.settings.tuning.map_size
            self.hud.notice(f"MAP SIZE {self._size:.0f}X ON THE NEXT NEW GAME (BACKSPACE)")
        return events

    def camera_hold(self):
        """While docked the view slides over so the station and your ship sit in the open space
        left of the station screen."""
        if not self.sb.station_open:
            return None
        ship, base = self.sb.stage.ship, self.sb.base
        return base.x + VIEW[0] / 2 - station_screen.LEFT / 2 - ship.x, base.y - ship.y

    def advance(self, dt: float) -> None:
        super().advance(dt)
        self.station.update(self.sb, self.clock)
        if self.sb.station_open:
            w = self.window
            over = self.station.click_test(*w.mouse) or w.panel.contains(*w.mouse)
            self.hud.set_cursor(*w.mouse, over, w.mouse_inside or bool(self.args.smoke))

    def place_arrows(self) -> None:
        super().place_arrows()
        cx, cy = self.view_centre()
        half = (VIEW[0] / 2 + 4, VIEW[1] / 2 + 4)
        self.hud.place_marks(self.sb.marks((cx, cy), half))

    def draw_ui(self) -> None:
        w = self.window
        self.hud.draw()
        self.station.draw()
        w.panel.draw()
        if w.mouse_inside or self.args.smoke:
            self.hud.draw_cursor()

