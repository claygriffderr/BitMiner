"""Secure the Base: the big map, home base and its space station, your drills and the mothership's waves.

Everything the combat sandbox has (WASD, mouse, 1 to 4, P, Tab), plus F to set a drill on the
asteroid next to you, E at the station to open its shop (E or Esc closes it), Shift to boost, G
(held) to lay mines, R to place a sentry (inside your collector ring, to mount it there), Q to grab
or let go of an asteroid with the lasso, T (hold, then let go) to place the collector ring, and N
to call the next wave now. = adds test credits
(`test_credits` in shop.json) so every item can be tried, and M skips the wave count ahead to just
before the next massive wave (both are testing shortcuts, marked in the play log). Backspace starts a new game, on a map as
big as the MAP SIZE slider says.
"""

from __future__ import annotations

import arcade

from ..combat.campaign import Campaign, autopilot
from ..flight import Controls
from ..graphics.renderer import VIEW
from ..ui.campaign_hud import CampaignHud
from ..ui import station_screen
from ..combat.shop import SENTRY_ITEMS
from ..ui.station_screen import StationScreen
from .sandbox import SandboxView

PAGE_KEYS = {arcade.key.KEY_1: 0, arcade.key.KEY_2: 1, arcade.key.KEY_3: 2}
PICK_KEYS = {arcade.key.W: -1, arcade.key.UP: -1, arcade.key.S: 1, arcade.key.DOWN: 1}
BUY_KEYS = (arcade.key.ENTER, arcade.key.RETURN, arcade.key.NUM_ENTER, arcade.key.SPACE)
TIER_KEYS = {arcade.key.A: -1, arcade.key.LEFT: -1, arcade.key.D: 1, arcade.key.RIGHT: 1}
BOOST_KEYS = (arcade.key.LSHIFT, arcade.key.RSHIFT)
TEST_CREDIT_KEYS = (arcade.key.EQUAL, arcade.key.PLUS, arcade.key.NUM_ADD)


class CampaignView(SandboxView):
    HUD = CampaignHud
    MODE = "campaign"

    def __init__(self, window):
        self._set_drill = False
        self._place_sentry = False
        self._lasso = False
        self.held: set[int] = set()       # Shift, G and T, while held
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
        self._place_sentry = False
        self._lasso = False
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
        if key == arcade.key.R and not self.paused:
            self._place_sentry = True
            return True
        if key == arcade.key.Q and not self.paused:
            self._lasso = True
            return True
        if key in BOOST_KEYS or key in (arcade.key.G, arcade.key.T):
            self.held.add(key)
            return True
        if key in TEST_CREDIT_KEYS:
            self._test_credits()
            return True
        if key == arcade.key.M and not self.paused:
            at = game.fleet.skip_to_massive()
            if at:
                game.note(("wave_skip", at))
                self.hud.notice(f"SKIPPED AHEAD: WAVE {at} IS THE MASSIVE ONE. N SENDS THE NEXT WAVE")
            return True
        return super().on_key_press(key, modifiers)

    def _test_credits(self) -> None:
        amount = self.sb.test_credits()
        if amount:
            self.hud.notice(f"TEST CREDITS +{amount:,}")

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
        elif key in TIER_KEYS and st.item in SENTRY_ITEMS:
            game.shop.pick_tier(st.item, game.shop.tier[st.item] + TIER_KEYS[key])
        elif key == arcade.key.P:
            self.paused = not self.paused
            self.hud.show_paused(self.paused)
        elif key in TEST_CREDIT_KEYS:
            self._test_credits()
        return True

    def on_key_release(self, key, modifiers):
        self.down.discard(key)
        self.held.discard(key)

    def on_hide_view(self):
        super().on_hide_view()
        self.held.clear()

    def on_deactivate(self):
        super().on_deactivate()
        self.held.clear()

    def on_mouse_press(self, x, y, button, modifiers):
        game = self.sb
        if game.station_open:
            w = self.window
            if button == arcade.MOUSE_BUTTON_LEFT and not w.panel.contains(*w.mouse):
                hit = self.station.click(*w.mouse)
                item = self.station.item
                if hit == "buy":
                    game.shop.buy(item)
                elif hit and hit.startswith("tier") and item in SENTRY_ITEMS:
                    game.shop.pick_tier(item, int(hit[4:]))
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
            keys = self.sb._autopilot.keys
            self._place_sentry = self._place_sentry or keys["sentry"]
            self._lasso = self._lasso or keys.get("lasso", False)
            self._auto_keys = keys
            return controls, trigger, cursor
        if self.sb.station_open:
            return Controls(), False, self.cursor_world()
        return super().pilot()

    def step_game(self, dt: float, controls: Controls, trigger: bool, cursor) -> list:
        keys = getattr(self, "_auto_keys", {})
        if self.args.smoke:
            boost, mines = keys.get("boost", False), keys.get("mines", False)
        else:
            boost = any(k in self.held for k in BOOST_KEYS)
            mines = arcade.key.G in self.held
        ring_key = keys.get("ring", False) if self.args.smoke else arcade.key.T in self.held
        events = self.sb.step(dt, controls, trigger, cursor, set_drill=self._set_drill, boost=boost,
                              lay_mines=mines, place_sentry=self._place_sentry, lasso=self._lasso,
                              ring_key=ring_key)
        self._set_drill = self._place_sentry = self._lasso = False
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
        self.hud.place_pops(dt, self.view_centre())
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

