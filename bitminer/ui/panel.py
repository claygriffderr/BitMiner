"""The tuning panel: one slider per flight setting, plus Reset and the CRT switch.

Drag a slider or scroll over it to change a value. The ship uses the new value straight away, and
the app saves it to flight_tuning.json. Layout is in game pixels with y up.
"""

from __future__ import annotations

from dataclasses import fields

import arcade
from PIL import Image

from art import hud, pix
from art.palette import rgba

from ..graphics.textures import GameTextures, tex
from ..settings import SLIDERS, Display, SliderSpec, Tuning
from .text import TextLayer

PANEL_X = 6
PANEL_W = 152
ROW_H = 18          # 16 sliders fit above the help line
HEADER_H = 19
FOOTER_H = 34
TRACK_X = PANEL_X + 8
TRACK_W = PANEL_W - 16


def solid(left: float, bottom: float, w: float, h: float, color: str) -> arcade.SpriteSolidColor:
    s = arcade.SpriteSolidColor(max(1, int(w)), max(1, int(h)), left + w / 2, bottom + h / 2, rgba(color))
    return s


def set_rect(s: arcade.Sprite, left: float, bottom: float, w: float, h: float) -> None:
    w = max(0.0, w)
    s.visible = w >= 1
    s.width = max(1, int(w))
    s.height = h
    s.center_x = left + max(1, int(w)) / 2
    s.center_y = bottom + h / 2


def knob_image(active: bool) -> Image.Image:
    rows = [
        ".kkk.",
        "kwwwk",
        "kwhwk",
        "kwhwk",
        "kwhwk",
        "kwhwk",
        "kwhwk",
        "kwwwk",
        ".kkk.",
    ]
    legend = {"k": "console_black", "w": "ion_white" if active else "hull_outline",
              "h": "ion" if active else "hull_light"}
    return pix.from_grid(rows, legend)


class Button:
    def __init__(self, panel: "TuningPanel", left: int, bottom: int, w: int, h: int, text: str):
        self.left, self.bottom, self.w, self.h = left, bottom, w, h
        self.frame = solid(left, bottom, w, h, "console_edge")
        self.face = solid(left + 1, bottom + 1, w - 2, h - 2, "console_mid")
        self.top = solid(left + 1, bottom + h - 2, w - 2, 1, "console_hi")
        for s in (self.frame, self.face, self.top):
            panel.sprites.append(s)
        self.label = panel.text.label(text, left + w // 2, bottom + (h - 7) // 2, "hud_text", "center")

    def contains(self, x: float, y: float) -> bool:
        return self.left <= x < self.left + self.w and self.bottom <= y < self.bottom + self.h

    def show(self, hover: bool, text: str | None = None) -> None:
        self.face.color = rgba("console_edge" if hover else "console_mid")
        self.label.set(text, color="ion_white" if hover else "hud_text")


class Row:
    def __init__(self, panel: "TuningPanel", spec: SliderSpec, top: int):
        self.spec = spec
        self.top = top
        self.track_y = top - 16
        default = getattr(Tuning(), spec.key)
        tick_x = TRACK_X + 1 + round(spec.fraction(default) * (TRACK_W - 3))
        add = panel.sprites.append
        add(solid(tick_x, self.track_y - 1, 1, 7, "console_hi"))         # where the default sits
        add(solid(TRACK_X, self.track_y, TRACK_W, 5, "console_black"))
        add(solid(TRACK_X + 1, self.track_y + 1, TRACK_W - 2, 3, "console_mid"))
        self.fill = solid(TRACK_X + 1, self.track_y + 1, 1, 3, "ion_dark")
        self.shine = solid(TRACK_X + 1, self.track_y + 3, 1, 1, "ion")
        add(self.fill)
        add(self.shine)
        self.knob = arcade.Sprite(panel.knob_idle)
        add(self.knob)
        self.name = panel.text.label(spec.label, TRACK_X, top - 8, "hud_dim")
        self.value = panel.text.label("", TRACK_X + TRACK_W, top - 8, "hud_text", "right")
        self._state = None

    def contains(self, x: float, y: float) -> bool:
        return PANEL_X <= x < PANEL_X + PANEL_W and self.top - ROW_H < y <= self.top

    def value_at(self, x: float) -> float:
        frac = (x - (TRACK_X + 1)) / (TRACK_W - 3)
        frac = min(1.0, max(0.0, frac))
        return self.spec.snap(self.spec.lo + frac * (self.spec.hi - self.spec.lo))

    def show(self, value: float, hot: bool, panel: "TuningPanel") -> None:
        state = (value, hot)
        if state == self._state:
            return
        self._state = state
        w = 1 + round(self.spec.fraction(value) * (TRACK_W - 3))
        set_rect(self.fill, TRACK_X + 1, self.track_y + 1, w, 3)
        set_rect(self.shine, TRACK_X + 1, self.track_y + 3, w, 1)
        self.fill.color = rgba("ion" if hot else "ion_dark")
        self.shine.color = rgba("ion_white" if hot else "ion")
        self.knob.texture = panel.knob_hot if hot else panel.knob_idle
        self.knob.center_x = TRACK_X + 1 + w - 0.5
        self.knob.center_y = self.track_y + 2.5
        self.name.set(color="hud_text" if hot else "hud_dim")
        self.value.set(self.spec.text(value), color="ion_white" if hot else "hud_text")


class TuningPanel:
    def __init__(self, textures: GameTextures, tuning: Tuning, display: Display, top: int = 354):
        self.tuning = tuning
        self.display = display
        self.open = True
        self.sprites = arcade.SpriteList()
        self.text = TextLayer(textures)
        self.knob_idle = tex(knob_image(False), "knob_idle")
        self.knob_hot = tex(knob_image(True), "knob_hot")
        self.top = top
        self.height = HEADER_H + ROW_H * len(SLIDERS) + FOOTER_H
        self.bottom = top - self.height
        bg = tex(hud.panel(PANEL_W, self.height, alpha=225), "tuning_panel")
        back = arcade.Sprite(bg)
        back.center_x = PANEL_X + PANEL_W / 2
        back.center_y = self.bottom + self.height / 2
        self.sprites.append(back)

        self.text.label("FLIGHT TUNING", TRACK_X, top - 12, "hud_text")
        self.text.label("TAB HIDES", TRACK_X + TRACK_W, top - 12, "hud_dim", "right")
        self.sprites.append(solid(PANEL_X + 5, top - HEADER_H + 2, PANEL_W - 10, 1, "console_edge"))
        self.rows = [Row(self, spec, top - HEADER_H - i * ROW_H) for i, spec in enumerate(SLIDERS)]
        foot = self.bottom
        self.sprites.append(solid(PANEL_X + 5, foot + FOOTER_H - 2, PANEL_W - 10, 1, "console_edge"))
        half = (TRACK_W - 4) // 2
        self.reset = Button(self, TRACK_X, foot + 15, half, 13, "RESET")
        self.crt = Button(self, TRACK_X + half + 4, foot + 15, half, 13, "CRT")
        self.status = self.text.label("AUTO-SAVE ON", TRACK_X, foot + 5, "hud_dim")
        self.hover = None
        self.dragging: Row | None = None
        self._status_time = 0.0
        self.refresh()

    # ------------------------------------------------------------ state

    def contains(self, x: float, y: float) -> bool:
        return self.open and PANEL_X <= x < PANEL_X + PANEL_W and self.bottom <= y < self.top

    def flash(self, message: str) -> None:
        self.status.set(message, color="ion_white")
        self._status_time = 1.6

    def update(self, dt: float) -> None:
        if self._status_time > 0:
            self._status_time -= dt
            if self._status_time <= 0:
                self.status.set("AUTO-SAVE ON", color="hud_dim")

    def refresh(self) -> None:
        for row in self.rows:
            hot = row is self.dragging or (self.dragging is None and row is self.hover)
            row.show(getattr(self.tuning, row.spec.key), hot, self)
        self.reset.show(self.hover is self.reset)
        self.crt.show(self.hover is self.crt, "CRT: ON" if self.display.crt else "CRT: OFF")

    def _target(self, x: float, y: float):
        if not self.contains(x, y):
            return None
        for row in self.rows:
            if row.contains(x, y):
                return row
        for b in (self.reset, self.crt):
            if b.contains(x, y):
                return b
        return None

    # ------------------------------------------------------------ input
    # Each handler returns what changed: None, "tuning" or "display".

    def on_motion(self, x: float, y: float) -> str | None:
        self.hover = self._target(x, y)
        if self.dragging is not None:
            return self._set(self.dragging, self.dragging.value_at(x))
        self.refresh()
        return None

    def on_press(self, x: float, y: float) -> str | None:
        target = self._target(x, y)
        if isinstance(target, Row):
            self.dragging = target
            return self._set(target, target.value_at(x))
        if target is self.reset:
            for f in fields(Tuning):
                setattr(self.tuning, f.name, getattr(Tuning(), f.name))
            self.flash("DEFAULTS RESTORED")
            self.refresh()
            return "tuning"
        if target is self.crt:
            self.display.crt = not self.display.crt
            self.refresh()
            return "display"
        return None

    def on_release(self) -> bool:
        """True if a drag just finished, so the app can save."""
        was = self.dragging is not None
        self.dragging = None
        self.refresh()
        return was

    def on_scroll(self, x: float, y: float, clicks: float) -> str | None:
        target = self._target(x, y)
        if isinstance(target, Row):
            step = target.spec.step * (1 if clicks > 0 else -1)
            return self._set(target, target.spec.snap(getattr(self.tuning, target.spec.key) + step))
        return None

    def _set(self, row: Row, value: float) -> str | None:
        old = getattr(self.tuning, row.spec.key)
        setattr(self.tuning, row.spec.key, value)
        self.refresh()
        return "tuning" if value != old else None

    def draw(self) -> None:
        if not self.open:
            return
        self.sprites.draw(pixelated=True)
        self.text.draw()
