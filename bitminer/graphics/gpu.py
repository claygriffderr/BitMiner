"""Small OpenGL helpers shared by the renderer: textures from Pillow images, shaders, a full-screen quad."""

from __future__ import annotations

import arcade
from PIL import Image

# Every post-processing pass draws this quad. `rect` places it in target pixels, so a pass can
# cover a whole framebuffer or just a small patch of it (like the ship's outline pass).
RECT_VS = """
#version 330
uniform vec4 rect;      // x, y, width, height in target pixels
uniform vec2 target;    // target size in pixels
in vec2 in_uv;
out vec2 v_uv;
void main() {
    vec2 p = rect.xy + in_uv * rect.zw;
    gl_Position = vec4(p / target * 2.0 - 1.0, 0.0, 1.0);
    v_uv = in_uv;
}
"""


def gl_texture(ctx, img: Image.Image, nearest: bool = True):
    """Upload a Pillow image as a raw GL texture, flipped so it appears upright."""
    img = img.convert("RGBA").transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    tex = ctx.texture(img.size, components=4, data=img.tobytes())
    f = ctx.NEAREST if nearest else ctx.LINEAR
    tex.filter = (f, f)
    return tex


def render_texture(ctx, size: tuple[int, int], nearest: bool = True, hdr: bool = False):
    """An empty texture to draw into, with a framebuffer around it."""
    tex = ctx.texture(size, components=4, dtype="f2" if hdr else "f1")
    f = ctx.NEAREST if nearest else ctx.LINEAR
    tex.filter = (f, f)
    tex.wrap_x = ctx.CLAMP_TO_EDGE
    tex.wrap_y = ctx.CLAMP_TO_EDGE
    return tex, ctx.framebuffer(color_attachments=[tex])


class Pass:
    """One shader drawn as a rectangle into whatever framebuffer is bound."""

    def __init__(self, ctx, fragment_shader: str):
        self.ctx = ctx
        self.program = ctx.program(vertex_shader=RECT_VS, fragment_shader=fragment_shader)
        # Each pass keeps its own quad: vertex arrays belong to one GL context.
        self.quad = arcade.gl.geometry.quad_2d(size=(2.0, 2.0))

    def __setitem__(self, name, value):
        self.program[name] = value

    def draw(self, rect: tuple[float, float, float, float], target: tuple[int, int]) -> None:
        self.program["rect"] = tuple(float(v) for v in rect)
        self.program["target"] = (float(target[0]), float(target[1]))
        self.quad.render(self.program)
