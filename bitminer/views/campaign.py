"""Secure the Base: the big map, home base, your mines and the mothership's waves.

Everything the combat sandbox has (WASD, mouse, 1 to 4, P, Tab), plus F to set a mine on the
asteroid next to you and N to call the next wave now. Backspace starts a new game, on a map as big
as the MAP SIZE slider says.
"""

from __future__ import annotations

import arcade

from ..combat.campaign import Campaign, autopilot
from ..flight import Controls
from ..graphics.renderer import VIEW
from ..ui.campaign_hud import CampaignHud
from .sandbox import SandboxView


class CampaignView(SandboxView):
    HUD = CampaignHud
    MODE = "campaign"

    def __init__(self, window):
        self._set_mine = False
        self._size = None
        super().__init__(window)

    def make_game(self) -> Campaign:
        tuning = self.window.settings.tuning
        self._size = tuning.map_size
        game = Campaign(self.sparks, self.smoke, tuning, scale=tuning.map_size)
        world = (game.world.width, game.world.height)
        self.sparks.world = world
        self.smoke.world = world
        self._set_mine = False
        return game

    def on_key_press(self, key, modifiers):
        if key == arcade.key.F and not self.paused:
            self._set_mine = True
            return True
        return super().on_key_press(key, modifiers)

    def pilot(self):
        if self.args.smoke:
            controls, trigger, cursor, set_mine = autopilot(self.sb, self.clock)
            self._set_mine = self._set_mine or set_mine
            return controls, trigger, cursor
        return super().pilot()

    def step_game(self, dt: float, controls: Controls, trigger: bool, cursor) -> list:
        events = self.sb.step(dt, controls, trigger, cursor, set_mine=self._set_mine)
        self._set_mine = False
        if self.window.settings.tuning.map_size != self._size:
            self._size = self.window.settings.tuning.map_size
            self.hud.notice(f"MAP SIZE {self._size:.0f}X ON THE NEXT NEW GAME (BACKSPACE)")
        return events

    def place_arrows(self) -> None:
        super().place_arrows()
        cx, cy = self.view_centre()
        half = (VIEW[0] / 2 + 4, VIEW[1] / 2 + 4)
        self.hud.place_marks(self.sb.marks((cx, cy), half))
