"""The HUD for Secure the Base:

- Lower right: the ship console (`campaign_console.py`): only the weapons you own, shield (NONE
  until you buy one), hull and armor, the drills you carry and your downs. Hidden while the
  station screen is open.
- Top: kills and enemies out on the left; the wave and whether the enemy knows where you are
  (HIDDEN or SPOTTED) in the middle, with no countdown; ore carried and credits on the right.
- Alerts under the top bar: a wave on its way, being spotted or lost, drills set, hit, lost or used
  up, sentries placed, hit or lost, asteroids crumbling, ore sold, and things bought or upgraded.
- Screen edges: arrows toward close enemies, a constant dim arrow toward home base, and for each of
  your drills an arrow with a tiny copy of its gold bar and its health (pink while under attack).
- Bottom centre: a prompt when you can press E for the station, F to set a drill or R to place a
  sentry you carry.
- In the world: a gold "+3" rises from each enemy you destroy, the credits it paid.
"""

from __future__ import annotations

import math

import arcade

from art import hud

from ..combat.specs import DRILLS
from ..graphics.textures import GameTextures, tex
from .campaign_console import CampaignConsole
from .combat_hud import ALERT_SHOW, ARROW_STEPS, VIEW_H, VIEW_W, CombatHud
from .text import text_width

# N (call the next wave) and Tab (tuning) still work; there's no room left on the line for them.
HELP = [("WASD", " FLY  "), ("CLICK", " FIRE  "), ("1-4", " WEAPON  "), ("SHIFT", " BOOST  "), ("F", " DRILL  "),
        ("G", " MINES  "), ("R", " SENTRY  "), ("E", " STATION  "), ("P", " PAUSE  "), ("ESC", " MENU")]
ALERT_COLOR = {"drill_set": "ore_hi", "unload": "ore_hi", "crumble": "ore", "lost": "alien_green_hi",
               "bought": "ion_hi", "notice": "hud_text", "sentry_set": "ion_hi"}   # the rest are warnings, in pink
MARK_ALPHA = 0.5          # your drills and base: constant, dim
HIT_SHOW = 1.5            # seconds a drill's arrow stays pink after a hit
EDGE = (10, VIEW_W - 10, 22, VIEW_H - 28)      # left, right, bottom, top: where edge arrows sit
MARKER_STEPS = 10         # a drill marker's gauges are drawn in this many steps
POP_TIME = 1.1            # seconds a kill's "+3" stays up
POP_RISE = 14             # game pixels it floats up in that time
POP_MAX = 12              # at most this many at once (the oldest make way)
BOUGHT = {"drill": "DRILL", "sniper": "SNIPER", "missiles": "MISSILES", "laser": "LASER", "repair": "HULL PATCHED",
          "mine": "MINE", "shield": "SHIELD", "armor": "ARMOR", "boost": "BOOST", "auto": "AUTO CANNON",
          "sentry_auto": "AUTO SENTRY", "sentry_sniper": "SNIPER SENTRY", "sentry_missile": "MISSILE SENTRY"}
SENTRY_NAME = {"auto": "AUTO", "sniper": "SNIPER", "missile": "MISSILE"}
NO_ROOM = {"ROCK": "NO ROOM FOR A SENTRY: TOO CLOSE TO AN ASTEROID",
           "CROWDED": "NO ROOM FOR A SENTRY: TOO CLOSE TO SOMETHING ELSE",
           "MAX": "THAT'S AS MANY SENTRIES AS YOU CAN HAVE OUT"}


class CampaignHud(CombatHud):
    def __init__(self, textures: GameTextures):
        self.marks = arcade.SpriteList()
        self._marker_tex: dict = {}
        super().__init__(textures)
        self.fps.set(y=VIEW_H - 32)            # under the ore and credits plate
        self.prompt = self.text.label("", VIEW_W // 2, 34, "ore_hi", "center", shadow="console_black")
        self._alert_kind = ""
        self._drill_hit_t = 99.0
        self.station_open = False
        self.pops: list = []          # [x, y, label, age] for each kill's credits, in world space

    # ------------------------------------------------------------ building

    def _build_console(self) -> None:
        self.console = CampaignConsole(self.textures, VIEW_W - 6, 6)

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
        self.station_open = game.station_open
        self.console.show(not game.station_open)
        self.console.update(game)
        self._update_top(dt, game)
        self._update_centre(game)
        self.prompt.set(self._prompt(game))

    @staticmethod
    def _prompt(game) -> str:
        if game.station_open:
            return ""
        d = game.defenses
        ship = game.stage.ship
        sentry = ""
        if d.carried and not game.stage.ship_down and not d.sentry_room(ship.x, ship.y):
            gun, tier = d.carried[0]
            sentry = f"R  PLACE YOUR {SENTRY_NAME[gun]} SENTRY T{tier} HERE"
        if game.near_station():
            return "E  OPEN THE STATION" + ("     R  PLACE A SENTRY" if sentry else "")
        if game.drillable() is not None:
            if game.drills_carried > 0:
                return f"F  SET A DRILL HERE   {game.drills_carried} LEFT"
            return "NO DRILLS LEFT: BUY MORE AT THE STATION"
        return sentry

    def _update_top(self, dt: float, game) -> None:
        st = game.stage
        self.kills.set(str(game.kills))
        self.alive.set(str(game.enemies_out()))
        self.ore.set(f"{int(game.cargo)}/{int(DRILLS['cargo'])}")
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

        self._drill_hit_t += dt
        for ev in st.events:
            kind = ev[0]
            text = None
            if kind == "wave":
                text = f"WAVE {ev[1]} ON ITS WAY: {ev[2]}"
            elif kind == "spotted":
                text = "SPOTTED: THEY ALL KNOW WHERE YOU ARE"
            elif kind == "lost":
                text = "THEY LOST YOU"
            elif kind == "drill_set":
                text = "DRILL SET"
            elif kind == "struct_hit" and ev[1] in ("drill", "sentry"):
                what = ev[1] + "_hit"
                if self._drill_hit_t > ALERT_SHOW or self._alert_kind != what:
                    text = f"{ev[1].upper()} UNDER ATTACK"
                    kind = what
                self._drill_hit_t = 0.0
            elif kind == "struct_lost" and ev[1] in ("drill", "sentry"):
                text = f"{ev[1].upper()} DESTROYED"
            elif kind == "sentry_set":
                text = f"{SENTRY_NAME[ev[1]]} SENTRY T{ev[2]} PLACED"
            elif kind == "no_room":
                text = NO_ROOM.get(ev[2], "NO ROOM HERE")
            elif kind == "crumble":
                text = "ASTEROID WORKED OUT: IT CRUMBLED WITH ITS DRILL"
            elif kind == "unload":
                text = f"SOLD {int(round(ev[1]))} ORE  +{ev[2]} CR"
            elif kind == "bought":
                name = BOUGHT.get(ev[1], ev[1].upper())
                if ev[1] == "repair":
                    text = name
                elif ev[1].startswith("sentry_"):
                    text = f"BOUGHT: {name} T{ev[3]}: PRESS R TO PLACE IT"
                elif len(ev) > 3:
                    text = f"UPGRADED: {name} LEVEL {ev[3]}"
                elif ev[1] == "mine":
                    text = "BOUGHT: MINE. HOLD G TO LAY IT"
                else:
                    text = f"BOUGHT: {name}"
            elif kind == "empty" and ev[1] == "missile":
                text = "OUT OF MISSILES: BUY MORE AT THE STATION"
            elif kind == "empty" and ev[1] == "laser":
                text = "LASER RECHARGING"
            elif kind == "bounty":
                self._pop(ev[3], ev[4], ev[2])
            if text is not None:
                self._show_alert(text, kind)
        self._alert_t += dt
        show = self._alert_t < ALERT_SHOW
        self.alert.visible = show and int(self._alert_t * 4) % 4 != 3
        if show:
            self._plate("alert_back", text_width(self.alert.text) + 12, "alert", VIEW_H - 25 - 15, "console_black")
        if self.alert_back is not None:
            self.alert_back.visible = show

    def _pop(self, x: float, y: float, amount: int) -> None:
        if len(self.pops) >= POP_MAX:
            old = self.pops.pop(0)
            old[2].set("")
        self.pops.append([x, y, self.text.label(f"+{amount}", 0, 0, "ore_hi", "center", shadow="console_black"), 0.0])

    def place_pops(self, dt: float, centre: tuple[float, float]) -> None:
        """Float each kill's credits up from where it died. `centre` is the view centre in the world."""
        cx, cy = centre
        keep = []
        for p in self.pops:
            x, y, label, age = p
            age += dt
            if age >= POP_TIME:
                label.set("")
                continue
            p[3] = age
            k = age / POP_TIME
            alpha = 255 if k < 0.6 else int(255 * (1 - k) / 0.4)
            label.set(x=int(x - cx + VIEW_W / 2), y=int(y - cy + VIEW_H / 2 + 8 + POP_RISE * k), alpha=alpha)
            keep.append(p)
        self.pops = keep

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

    # ------------------------------------------------------------ your drills and base

    def place_marks(self, marks: list) -> None:
        """`marks` is [(dx, dy, kind, structure)] from the view centre for your base and drills
        that are off screen. The base gets a dim arrow at the edge; a drill's has its gauges."""
        while len(self.marks) < len(marks):
            self.marks.append(arcade.Sprite(self._arrow(0, "hull_hi")))
        left, right, bottom, top = EDGE
        cx, cy = (left + right) / 2, (bottom + top) / 2
        for i, s in enumerate(self.marks):
            if i >= len(marks):
                s.visible = False
                continue
            dx, dy, kind, t = marks[i]
            a = math.atan2(dy, dx)
            step = int(round(a / math.tau * ARROW_STEPS)) % ARROW_STEPS
            k = min((right - cx) / abs(dx) if dx else 1e9, (top - cy) / abs(dy) if dy else 1e9)
            ax, ay = int(cx + dx * k), int(cy + dy * k)
            hit = kind == "drill" and t.since_hit < HIT_SHOW
            if kind == "drill":
                s.texture = self._marker(step, t, hit)
                # The gauges sit to the right of the arrow; keep them on screen at the right edge.
                w = s.texture.width
                arrow_w = w - 20
                left_x = ax - arrow_w // 2 if ax < cx + 40 else ax - w + arrow_w // 2
                s.center_x, s.center_y = left_x + w / 2, ay + 0.5
            else:
                s.texture = self._arrow(step, "hull_hi")
                s.center_x, s.center_y = ax + 0.5, ay + 0.5
            s.alpha = int(255 * (0.95 if hit and int(t.since_hit * 6) % 2 == 0 else (0.75 if kind == "drill" else MARK_ALPHA)))
            s.visible = True

    def _marker(self, step: int, d, hit: bool) -> arcade.Texture:
        health = round(d.health / max(1.0, d.max_health) * MARKER_STEPS)
        fill = round(d.hold / max(1.0, d.hold_max) * MARKER_STEPS)
        key = (step, health, fill, hit)
        t = self._marker_tex.get(key)
        if t is None:
            angle = -360.0 * step / ARROW_STEPS
            img = hud.drill_marker(angle, health / MARKER_STEPS, fill / MARKER_STEPS, hit)
            t = self._marker_tex[key] = tex(img, "drill_marker_" + "_".join(str(v) for v in key))
        return t

    # ------------------------------------------------------------ drawing

    def draw(self) -> None:
        self.marks.draw(pixelated=True)
        self.arrows.draw(pixelated=True)
        self.sprites.draw(pixelated=True)
        self.console.draw()
        self.text.draw()
