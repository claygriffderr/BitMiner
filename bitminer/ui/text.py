"""Pixel-font labels for the HUD and tuning panel, built from one white sprite per character.

Coordinates are game pixels with y up; (x, y) is the bottom-left of a label's 7-pixel-tall line.
"""

from __future__ import annotations

import arcade

from art import pixfont
from art.palette import rgba

from ..graphics.textures import GameTextures


def text_width(text: str) -> int:
    width = 0
    for ch in text.upper():
        if ch == " ":
            width += 4
            continue
        if ch not in pixfont.GLYPHS:
            ch = "?"
        width += len(pixfont._columns(ch)) + 1
    return max(0, width - 1)


class Label:
    def __init__(self, layer: "TextLayer", text: str, x: float, y: float, color: str = "hud_text",
                 align: str = "left", shadow: str | None = None):
        self.layer = layer
        self.text = None
        self.x, self.y = x, y
        self.color = color
        self.align = align
        self.shadow = shadow
        self.alpha = 255
        self._sprites: list[arcade.Sprite] = []
        self._visible = True
        self.set(text)

    @property
    def width(self) -> int:
        return text_width(self.text or "")

    def set(self, text: str | None = None, color: str | None = None, x: float | None = None,
            y: float | None = None, alpha: int | None = None) -> None:
        text = self.text if text is None else text.upper()
        changed = (text != self.text or (color is not None and color != self.color)
                   or (x is not None and x != self.x) or (y is not None and y != self.y)
                   or (alpha is not None and alpha != self.alpha))
        if not changed:
            return
        self.text = text
        self.color = color or self.color
        self.x = self.x if x is None else x
        self.y = self.y if y is None else y
        self.alpha = self.alpha if alpha is None else alpha
        self._build()

    @property
    def visible(self) -> bool:
        return self._visible

    @visible.setter
    def visible(self, value: bool) -> None:
        self._visible = value
        for s in self._sprites:
            s.visible = value

    def _build(self) -> None:
        for s in self._sprites:
            s.remove_from_sprite_lists()
        self._sprites = []
        w = self.width
        left = {"left": self.x, "right": self.x - w, "center": self.x - w // 2}[self.align]
        layers = ([(self.shadow, 1, -1)] if self.shadow else []) + [(self.color, 0, 0)]
        glyphs = self.layer.textures.glyphs
        for color, ox, oy in layers:
            c = rgba(color)
            tint = (c[0], c[1], c[2], self.alpha)
            x = left
            for ch in self.text:
                if ch == " ":
                    x += 4
                    continue
                t = glyphs.get(ch) or glyphs["?"]
                s = arcade.Sprite(t)
                s.center_x = x + ox + t.width / 2
                s.center_y = self.y + oy + 3.5
                s.color = tint
                s.visible = self._visible
                self.layer.sprites.append(s)
                self._sprites.append(s)
                x += t.width + 1


class TextLayer:
    def __init__(self, textures: GameTextures):
        self.textures = textures
        self.sprites = arcade.SpriteList()

    def label(self, text: str, x: float, y: float, color: str = "hud_text", align: str = "left",
              shadow: str | None = None) -> Label:
        return Label(self, text, x, y, color, align, shadow)

    def draw(self) -> None:
        self.sprites.draw(pixelated=True)
