"""Game textures, drawn by the same code as the approved sprite sheets in `art/`.

Each texture that gives off light also gets an emissive twin: the same picture with only its
glowing pixels, which the renderer draws into the light layer for bloom.
"""

from __future__ import annotations

import arcade
from PIL import Image

from art import pixfont, sprites as S

from ..field import SIZES, VARIANTS
from .images import crosshair, glyph, light_twin, pointer, rock_image, silhouette

_FAST_HITBOX = arcade.hitbox.algo_bounding_box


def tex(img: Image.Image, name: str) -> arcade.Texture:
    return arcade.Texture(img, hash=f"bitminer:{name}", hit_box_algorithm=_FAST_HITBOX)


class GameTextures:
    """Every texture the flight test draws, built once at start-up."""

    def __init__(self) -> None:
        # Asteroids: 8 sizes x 3 shapes, plain and with gold ore.
        self.rock: dict[tuple[int, int, bool], arcade.Texture] = {}
        self.rock_light: dict[tuple[int, int, bool], arcade.Texture] = {}
        for size in SIZES:
            for v in range(VARIANTS):
                for ore in (False, True):
                    img = rock_image(size, v, ore)
                    key = (size, v, ore)
                    self.rock[key] = tex(img, f"rock{size}_{v}_{int(ore)}")
                    glow = light_twin(img)
                    if glow is not None:
                        self.rock_light[key] = tex(glow, f"rock{size}_{v}_{int(ore)}_light")

        # The ship, on the shared 27x27 canvas: un-outlined body, its glow, a white hit flash.
        body, _ = S.player_parts()
        self.ship_body = tex(body, "ship_body")
        self.ship_body_light = tex(light_twin(body), "ship_body_light")
        self.ship_flash = tex(silhouette(body), "ship_flash")
        self.ship_canvas = body.width
        # One flame texture per booster and flicker frame, so any mix can be lit at once.
        self.flame: dict[tuple[str, int], arcade.Texture] = {}
        self.flame_light: dict[tuple[str, int], arcade.Texture] = {}
        for key in "WSAD":
            for frame in (0, 1):
                img = S.player_flames((key,), frame)
                self.flame[key, frame] = tex(img, f"flame_{key}{frame}")
                self.flame_light[key, frame] = tex(light_twin(img), f"flame_{key}{frame}_light")

        self.pixel = tex(Image.new("RGBA", (1, 1), (255, 255, 255, 255)), "pixel")
        self.crosshair = tex(crosshair(), "crosshair")
        self.pointer = tex(pointer(), "pointer")
        self.glyphs = {ch: tex(glyph(ch), f"glyph_{ord(ch)}") for ch in pixfont.GLYPHS}
