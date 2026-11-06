"""The HUD for Secure the Base: the sandbox's ship console, plus

- Top: kills and enemies out on the left; the wave and whether the enemy knows where you are
  (HIDDEN or SPOTTED) in the middle, with no countdown; ore carried and credits on the right.
- Alerts under the top bar: a wave on its way, being spotted or lost, mines set, hit, lost or run dry.
- Screen edges: arrows toward close enemies, and constant dim arrows toward home base and each of
  your mines, a mine's with its health and ore bars beside it (pink while it is under attack).
- Bottom centre: a prompt when the asteroid next to you can take a mine.
"""

from __future__ import annotations

import math

import arcade

from art import hud
from art.palette import rgba

from ..combat.specs import MINES
from ..graphics.textures import GameTextures
from .combat_hud import ALERT_SHOW, ARROW_STEPS, VIEW_H, VIEW_W, CombatHud
from .panel import set_rect, solid
from .text import text_width

HELP = [("WASD", " FLY  "), ("CLICK", " FIRE  "), ("1-4", "/"), ("WHEEL", " WEAPON  "), ("F", " SET MINE  "),
        ("N", " CALL WAVE  "), ("P", " PAUSE  "), ("TAB", " TUNING  "), ("ESC", " MENU")]
MARK_COLOR = {"mine": "ore", "base": "hull_hi", "mine_hit": "danger_pink"}
ALERT_COLOR = {"mine_set": "ore_hi", "unload": "ore_hi", "mine_dry": "ore", "lost": "alien_green_hi",
               "notice": "hud_text"}      # the rest are warnings, in pink
MARK_ALPHA = 0.5          # your mines and base: constant, dim
HIT_SHOW = 1.5            # seconds a mine's arrow stays pink after a hit
EDGE = (10, VIEW_W - 10, 22, VIEW_H - 28)      # left, right, bottom, top: where edge arrows sit
BAR_W = 12


class CampaignHud(CombatHud):
    def __init__(self, textures: GameTextures):
        self.marks = arcade.SpriteList()
        self.mark_bars = arcade.SpriteList()
        self._bar_sprites: list[tuple] = []
        super().__init__(textures)
        self.fps.set(y=VIEW_H - 32)            # under the ore and credits plate
        self.prompt = self.text.label("", VIEW_W // 2, 34, "ore_hi", "center", shadow="console_black")
        self._alert_kind = ""
        self._mine_hit_t = 99.0

    # ------------------------------------------------------------ building

    def _build_help(self, help_line=None) -> None:
        super()._build_help(HELP)

    def _build_top(self) -> None:
        super()._build_top()
        self.wave.set("")
        # Ore and credits, top right.
        self._sprite(hud.panel(122, 15), "top_right", VIEW_W - 6 - 122, VIEW_H - 6 - 15)
        y = VIEW_H - 6 - 11
        left = VIEW_W - 6 - 122 + 5
        self.text.label("ORE", left, y, "hud_dim")
        self.ore = self.text.label("0", left + text_width("ORE") + 5, y, "ore")
        self.text.label("CR", left + 70, y, "hud_dim")
        self.credits = self.text.label("0", left + 70 + text_width("CR") + 5, y, "ore_hi")

    # ------------------------------------------------------------ each frame

    def update(self, dt: float, game) -> None:
        """Show the state of `game`, a Campaign."""
        self._update_console(game)
        self._update_top(dt, game)
        self._update_centre(game)
        spot = game.mine_spot() is not None
        if spot:
            self.prompt.set(f"F  SET A MINE HERE   {len(game.mines)}/{int(MINES['max'])}")
        else:
            self.prompt.set("")

    def _update_top(self, dt: float, game) -> None:
        st = game.stage
        self.kills.set(str(game.kills))
        self.alive.set(str(game.enemies_out()))
        self.ore.set(f"{int(game.cargo)}/{int(MINES['cargo'])}")
        self.credits.set(str(game.credits))
        fleet = game.fleet
        wave_txt = f"WAVE {fleet.number}" if fleet.number else "GET READY"
        known = game.hunt.known
        state_txt = "SPOTTED" if known else "HIDDEN"
        mid_w = text_width(wave_txt) + text_width(state_txt) + 22
        self._plate("mid", mid_w, "top_mid", VIEW_H - 6 - 15)
        left = (VIEW_W - mid_w) // 2
        self.wave.set(wave_txt, x=left + 6)
        self.next_wave.set(state_txt, color="danger_pink_hi" if known else "alien_green_hi",
                           x=left + 16 + text_width(wave_txt))

        self._mine_hit_t += dt
        for ev in st.events:
            kind = ev[0]
            text = None
            if kind == "wave":
                text = f"WAVE {ev[1]} ON ITS WAY: {ev[2]}"
            elif kind == "spotted":
                text = "SPOTTED: THEY ALL KNOW WHERE YOU ARE"
            elif kind == "lost":
                text = "THEY LOST YOU"
            elif kind == "mine_set":
                text = "MINE SET"
            elif kind == "struct_hit" and ev[1] == "mine":
                if self._mine_hit_t > ALERT_SHOW or self._alert_kind != "mine_hit":
                    text = "MINE UNDER ATTACK"
                    kind = "mine_hit"
                self._mine_hit_t = 0.0
            elif kind == "struct_lost" and ev[1] == "mine":
                text = "MINE DESTROYED"
            elif kind == "mine_dry":
                text = "MINE RAN DRY"
            elif kind == "unload":
                text = f"SOLD {int(round(ev[1]))} ORE  +{ev[2]} CR"
            if text is not None:
                self._show_alert(text, kind)
        self._alert_t += dt
        show = self._alert_t < ALERT_SHOW
        self.alert.visible = show and int(self._alert_t * 4) % 4 != 3
        if show:
            self._plate("alert_back", text_width(self.alert.text) + 12, "alert", VIEW_H - 25 - 15, "console_black")
        if self.alert_back is not None:
            self.alert_back.visible = show

    def _show_alert(self, text: str, kind: str) -> None:
        self._alert_t = 0.0
        self._alert_kind = kind
        self.alert.set(text, color=ALERT_COLOR.get(kind, "danger_pink_hi"))

    def notice(self, text: str) -> None:
        """Put a message up where the alerts go."""
        self._show_alert(text, "notice")

    def _update_centre(self, game) -> None:
        st = game.stage
        if st.ship_down:
            self.centre.set("SHIP DOWN")
            self.centre_sub.set(f"BACK AT BASE IN {max(0.0, game.respawn_in):.1f}")
        else:
            self.centre.set("")
            self.centre_sub.set("")

    # ------------------------------------------------------------ your mines and base

    def place_marks(self, marks: list) -> None:
        """`marks` is [(dx, dy, kind, structure)] from the view centre for your base and mines
        that are off screen. Each gets a dim arrow at the edge; a mine's has its bars beside it."""
        while len(self.marks) < len(marks):
            self.marks.append(arcade.Sprite(self._arrow(0, "ore")))
        while len(self._bar_sprites) < len(marks):
            parts = (solid(0, 0, BAR_W + 2, 6, "console_black"), solid(0, 0, BAR_W, 2, "console_mid"),
                     solid(0, 0, BAR_W, 2, "ion"), solid(0, 0, BAR_W, 2, "console_mid"), solid(0, 0, BAR_W, 2, "ore"))
            for p in parts:
                self.mark_bars.append(p)
            self._bar_sprites.append(parts)
        left, right, bottom, top = EDGE
        cx, cy = (left + right) / 2, (bottom + top) / 2
        for i, s in enumerate(self.marks):
            parts = self._bar_sprites[i]
            if i >= len(marks):
                s.visible = False
                for p in parts:
                    p.visible = False
                continue
            dx, dy, kind, t = marks[i]
            hit = kind == "mine" and t.since_hit < HIT_SHOW
            color = MARK_COLOR["mine_hit" if hit else kind]
            a = math.atan2(dy, dx)
            step = int(round(a / math.tau * ARROW_STEPS)) % ARROW_STEPS
            s.texture = self._arrow(step, color)
            k = min((right - cx) / abs(dx) if dx else 1e9, (top - cy) / abs(dy) if dy else 1e9)
            ax, ay = int(cx + dx * k), int(cy + dy * k)
            s.center_x, s.center_y = ax + 0.5, ay + 0.5
            s.alpha = int(255 * (0.95 if hit and int(t.since_hit * 6) % 2 == 0 else MARK_ALPHA))
            s.visible = True
            show_bars = kind == "mine"
            for p in parts:
                p.visible = show_bars
            if not show_bars:
                continue
            # Bars just inside the arrow, toward the middle of the screen.
            bx = ax - (BAR_W + 8 if ax > cx + 40 else -8 if ax < cx - 40 else BAR_W // 2)
            by = ay - (12 if ay > cy + 40 else -6 if ay < cy - 40 else 3)
            back, h_back, h_fill, o_back, o_fill = parts
            set_rect(back, bx - 1, by - 1, BAR_W + 2, 6)
            set_rect(h_back, bx, by + 3, BAR_W, 2)
            health = t.health / max(1.0, t.max_health)
            set_rect(h_fill, bx, by + 3, round(BAR_W * health), 2)
            h_fill.color = rgba("danger_pink" if health < 0.3 else "ion")
            set_rect(o_back, bx, by, BAR_W, 2)
            set_rect(o_fill, bx, by, round(BAR_W * t.ore_left / max(1.0, t.ore_max)), 2)
            for p in parts:
                p.alpha = int(255 * (0.9 if hit else 0.6))

    # ------------------------------------------------------------ drawing

    def draw(self) -> None:
        self.marks.draw(pixelated=True)
        self.mark_bars.draw(pixelated=True)
        super().draw()
