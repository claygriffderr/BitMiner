"""Shader passes: the ship's outline, bloom, and the final picture with the optional CRT filter.

All of them follow the art pipeline (`art/pix.py`): the outline is drawn after rotating, glow is
two Gaussian blurs of the light layer screen-blended over the picture, and the CRT filter darkens
the last row of every game pixel, fringes red and blue, and adds a vignette.
"""

from __future__ import annotations

from .gpu import Pass, render_texture

OUTLINE_FS = """
#version 330
uniform sampler2D hw;        // the rotated ship interior, drawn at screen resolution
uniform vec2 origin;         // where that patch sits in the target, in pixels
uniform int radius;          // outline thickness: one game pixel
uniform vec4 outline_color;
out vec4 frag;
void main() {
    ivec2 p = ivec2(gl_FragCoord.xy - origin);
    ivec2 size = textureSize(hw, 0);
    vec4 c = texelFetch(hw, p, 0);
    if (c.a > 0.0) { frag = vec4(c.rgb, 1.0); return; }
    int r2 = radius * radius + 1;
    for (int dy = -radius; dy <= radius; dy++) {
        for (int dx = -radius; dx <= radius; dx++) {
            if (dx * dx + dy * dy > r2) continue;
            ivec2 q = p + ivec2(dx, dy);
            if (q.x < 0 || q.y < 0 || q.x >= size.x || q.y >= size.y) continue;
            if (texelFetch(hw, q, 0).a > 0.0) { frag = outline_color; return; }
        }
    }
    discard;
}
"""

BLUR_FS = """
#version 330
uniform sampler2D src;
uniform vec2 dir;        // one texel step along x or y
uniform float sigma;     // in texels of the target
in vec2 v_uv;
out vec4 frag;
void main() {
    int r = int(ceil(sigma * 3.0));
    vec3 sum = vec3(0.0);
    float wsum = 0.0;
    for (int i = -r; i <= r; i++) {
        float w = exp(-0.5 * float(i * i) / (sigma * sigma));
        sum += texture(src, v_uv + dir * float(i)).rgb * w;
        wsum += w;
    }
    frag = vec4(sum / wsum, 1.0);
}
"""

COPY_FS = """
#version 330
uniform sampler2D src;
in vec2 v_uv;
out vec4 frag;
void main() { frag = vec4(texture(src, v_uv).rgb, 1.0); }
"""

COMPOSITE_FS = """
#version 330
uniform sampler2D scene;
uniform sampler2D near;
uniform sampler2D far;
uniform float bloom;
in vec2 v_uv;
out vec4 frag;
void main() {
    vec3 base = texelFetch(scene, ivec2(gl_FragCoord.xy), 0).rgb;
    vec3 glow = texture(near, v_uv).rgb * 0.9 + texture(far, v_uv).rgb * 0.8;
    glow = clamp(glow * bloom, 0.0, 1.0);
    frag = vec4(1.0 - (1.0 - base) * (1.0 - glow), 1.0);   // screen blend
}
"""

PRESENT_FS = """
#version 330
uniform sampler2D frame;
uniform vec2 origin;     // letterbox offset in window pixels
uniform int k;           // screen pixels per game pixel
uniform int crt;
out vec4 frag;
void main() {
    ivec2 size = textureSize(frame, 0);
    ivec2 p = clamp(ivec2(gl_FragCoord.xy - origin), ivec2(0), size - 1);
    vec3 c = texelFetch(frame, p, 0).rgb;
    if (crt == 1) {
        vec3 l = texelFetch(frame, ivec2(max(p.x - 1, 0), p.y), 0).rgb;
        vec3 r = texelFetch(frame, ivec2(min(p.x + 1, size.x - 1), p.y), 0).rgb;
        c = vec3(0.85 * c.r + 0.15 * l.r, c.g, 0.85 * c.b + 0.15 * r.b);
        int row_from_top = size.y - 1 - p.y;
        if (k > 1 && row_from_top % k == k - 1) c *= 0.62;
        vec2 d = (vec2(p) + 0.5 - vec2(size) * 0.5) / (vec2(size) * 0.5);
        c *= 1.0 - 0.28 * clamp(d.x * d.x * 0.6 + d.y * d.y * 0.8, 0.0, 1.5);
        c *= 1.08;
    }
    frag = vec4(clamp(c, 0.0, 1.0), 1.0);
}
"""


class Outline:
    def __init__(self, ctx, color: tuple[int, int, int, int]):
        self.pass_ = Pass(ctx, OUTLINE_FS)
        self.pass_["hw"] = 0
        self.pass_["outline_color"] = tuple(c / 255 for c in color)

    def draw(self, hw_texture, origin: tuple[int, int], k: int, target: tuple[int, int]) -> None:
        hw_texture.use(0)
        self.pass_["origin"] = (float(origin[0]), float(origin[1]))
        self.pass_["radius"] = int(k)
        w, h = hw_texture.size
        self.pass_.draw((origin[0], origin[1], w, h), target)


class Bloom:
    """Blurs the light layer twice: a tight glow and a wide haze, like the art's near and far blur."""

    NEAR_SIGMA = 2.2   # game pixels
    FAR_SIGMA = 7.0

    def __init__(self, ctx, view: tuple[int, int]):
        self.ctx = ctx
        self.view = view
        w, h = view
        self.blur = Pass(ctx, BLUR_FS)
        self.copy = Pass(ctx, COPY_FS)
        self.blur["src"] = 0
        self.copy["src"] = 0
        self.tmp_near, self.fbo_tmp_near = render_texture(ctx, (w, h), nearest=False, hdr=True)
        self.near, self.fbo_near = render_texture(ctx, (w, h), nearest=False, hdr=True)
        self.half, self.fbo_half = render_texture(ctx, (w // 2, h // 2), nearest=False, hdr=True)
        self.tmp_far, self.fbo_tmp_far = render_texture(ctx, (w // 2, h // 2), nearest=False, hdr=True)
        self.far, self.fbo_far = render_texture(ctx, (w // 2, h // 2), nearest=False, hdr=True)

    def _blur(self, src, tmp_fbo, tmp, dst_fbo, sigma: float) -> None:
        w, h = src.size
        tmp_fbo.use()
        src.use(0)
        self.blur["dir"] = (1.0 / w, 0.0)
        self.blur["sigma"] = sigma
        self.blur.draw((0, 0, w, h), (w, h))
        dst_fbo.use()
        tmp.use(0)
        self.blur["dir"] = (0.0, 1.0 / h)
        self.blur.draw((0, 0, w, h), (w, h))

    def run(self, light) -> None:
        """`light` is the game-resolution light layer texture."""
        light.filter = (self.ctx.LINEAR, self.ctx.LINEAR)
        self._blur(light, self.fbo_tmp_near, self.tmp_near, self.fbo_near, self.NEAR_SIGMA)
        w, h = self.half.size
        self.fbo_half.use()
        light.use(0)
        self.copy.draw((0, 0, w, h), (w, h))
        self._blur(self.half, self.fbo_tmp_far, self.tmp_far, self.fbo_far, self.FAR_SIGMA / 2)


class Composite:
    def __init__(self, ctx):
        self.pass_ = Pass(ctx, COMPOSITE_FS)
        self.pass_["scene"] = 0
        self.pass_["near"] = 1
        self.pass_["far"] = 2

    def draw(self, scene, bloom: Bloom, strength: float, target: tuple[int, int]) -> None:
        scene.use(0)
        bloom.near.use(1)
        bloom.far.use(2)
        self.pass_["bloom"] = float(strength)
        self.pass_.draw((0, 0, *target), target)


class Present:
    def __init__(self, ctx):
        self.pass_ = Pass(ctx, PRESENT_FS)
        self.pass_["frame"] = 0

    def draw(self, frame, origin: tuple[int, int], k: int, crt: bool, target: tuple[int, int]) -> None:
        frame.use(0)
        self.pass_["origin"] = (float(origin[0]), float(origin[1]))
        self.pass_["k"] = int(k)
        self.pass_["crt"] = 1 if crt else 0
        w, h = frame.size
        self.pass_.draw((origin[0], origin[1], w, h), target)
