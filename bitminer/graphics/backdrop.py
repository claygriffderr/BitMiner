"""The space backdrop: a dithered nebula and three layers of stars that scroll at different speeds.

The pictures are drawn like the art's `space_backdrop`, but every layer tiles seamlessly so it can
repeat forever behind the wrap-around field. A shader draws all layers in one pass.
"""

from __future__ import annotations

from PIL import Image

from .gpu import Pass, gl_texture
from .images import TILE, light_twin, nebula_tile, star_tile

PARALLAX = (0.12, 0.3, 0.55)  # Nebula with dim stars, mid stars, bright stars. The rocks move at 1.


BACKDROP_FS = """
#version 330
uniform sampler2D layer0;
uniform sampler2D layer1;
uniform sampler2D layer2;
uniform vec2 off0;
uniform vec2 off1;
uniform vec2 off2;
uniform float k;          // screen pixels per game pixel
out vec4 frag;

vec4 fetch(sampler2D t, vec2 p) {
    ivec2 size = textureSize(t, 0);
    ivec2 i = ivec2(floor(p));
    i = ((i % size) + size) % size;
    return texelFetch(t, i, 0);
}

void main() {
    vec2 g = gl_FragCoord.xy / k;
    vec4 c = fetch(layer0, g + off0);
    vec4 m = fetch(layer1, g + off1);
    if (m.a > 0.0) c = m;
    vec4 n = fetch(layer2, g + off2);
    if (n.a > 0.0) c = n;
    frag = vec4(c.rgb, 1.0);
}
"""

# The light layer only needs the bright stars' glow.
BACKDROP_LIGHT_FS = """
#version 330
uniform sampler2D glow;
uniform vec2 off2;
out vec4 frag;
void main() {
    ivec2 size = textureSize(glow, 0);
    ivec2 i = ivec2(floor(gl_FragCoord.xy + off2));
    i = ((i % size) + size) % size;
    frag = vec4(texelFetch(glow, i, 0).rgb, 1.0);
}
"""


class Backdrop:
    def __init__(self, ctx, seed: int = 7):
        self.ctx = ctx
        neb = nebula_tile(seed)
        mid = star_tile(seed + 10, mid=TILE * TILE // 1400, bright=0)
        near = star_tile(seed + 20, mid=0, bright=TILE * TILE // 9000)
        # Flip so texel rows run bottom to top like the screen. The tiles repeat, so this is free.
        self.layers = [gl_texture(ctx, img) for img in (neb, mid, near)]
        self.glow = gl_texture(ctx, light_twin(near) or Image.new("RGBA", near.size))
        self.pass_ = Pass(ctx, BACKDROP_FS)
        self.light_pass = Pass(ctx, BACKDROP_LIGHT_FS)
        self.pass_["layer0"] = 0
        self.pass_["layer1"] = 1
        self.pass_["layer2"] = 2
        self.light_pass["glow"] = 0

    @staticmethod
    def offsets(cam_ux: float, cam_uy: float, view: tuple[int, int], k: int) -> list[tuple[float, float]]:
        """Where each layer's tile starts, in game pixels, snapped so its pixels land on screen pixels."""
        out = []
        for f in PARALLAX:
            ox = (cam_ux * f - view[0] / 2) % TILE
            oy = (cam_uy * f - view[1] / 2) % TILE
            out.append((round(ox * k) / k, round(oy * k) / k))
        return out

    def draw(self, offsets, k: int, target: tuple[int, int]) -> None:
        for i, t in enumerate(self.layers):
            t.use(i)
            self.pass_[f"off{i}"] = offsets[i]
        self.pass_["k"] = float(k)
        self.pass_.draw((0, 0, *target), target)

    def draw_light(self, offsets, target: tuple[int, int]) -> None:
        self.glow.use(0)
        self.light_pass["off2"] = offsets[2]
        self.light_pass.draw((0, 0, *target), target)
