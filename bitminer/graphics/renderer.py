"""Draws a frame of the game, following the art pipeline.

1. Scene: backdrop, asteroids, warning lanes, particles, enemy hulls and then the ship (each
   rotated at screen resolution and outlined after rotating, so outlines never break up), booster
   flames, then shots, beams, explosions and sparks.
2. Light: the glowing pixels of everything, at game resolution, blurred into bloom.
3. Composite: bloom screen-blended over the scene, then the HUD and tuning panel on top.
4. Present: integer-scaled into the window with black bars, through the optional CRT filter.

The game is 640x360 game pixels. Each one is k x k screen pixels, with k as big as the window allows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import arcade
import numpy as np
from pyglet import gl

from art.palette import rgba

from ..field import AsteroidField, wrap_delta
from .backdrop import Backdrop
from .gpu import render_texture
from .particles import Particles
from .postfx import Bloom, Composite, Outline, Present
from .textures import GameTextures

VIEW = (640, 360)
BLOOM = 1.0


@dataclass
class FrameView:
    cam_x: float          # View centre in world coordinates (wrapped into the field).
    cam_y: float
    cam_ux: float         # The same, but never wrapped: drives the parallax backdrop.
    cam_uy: float
    ship_x: float
    ship_y: float
    ship_angle: float
    boosters: tuple[str, ...]
    flame_frame: int
    flash: float          # 0..1, the white flash after a hit.
    crt: bool
    ship_visible: bool = True
    stage: Any = None     # a StageDrawer with this frame's combat layers, or None


def snap(v, k: int):
    """Round to the nearest screen pixel, in game pixel units."""
    return np.round(np.asarray(v) * k) / k


class Renderer:
    def __init__(self, window: arcade.Window, art: GameTextures, field: AsteroidField,
                 under: Particles, over: Particles):
        self.window = window
        self.ctx = window.ctx
        self.art = art
        self.field = field
        self.under = under      # exhaust and dust, drawn behind the ship
        self.over = over        # sparks, drawn in front of it
        self.backdrop = Backdrop(self.ctx)
        self.outline = Outline(self.ctx, rgba("hull_outline"))
        self.enemy_outline = Outline(self.ctx, rgba("alien_purple_black"))
        self.composite = Composite(self.ctx)
        self.present = Present(self.ctx)
        self.light_tex, self.light_fbo = render_texture(self.ctx, VIEW, nearest=False)
        self.bloom = Bloom(self.ctx, VIEW)
        self.light_cam = arcade.Camera2D(viewport=arcade.LBWH(0, 0, *VIEW), position=(0, 0), zoom=1,
                                         render_target=self.light_fbo)
        self.light_screen = arcade.Camera2D(viewport=arcade.LBWH(0, 0, *VIEW),
                                            position=(VIEW[0] / 2, VIEW[1] / 2), zoom=1,
                                            render_target=self.light_fbo)

        self.set_field(field)

        # The ship: its interior is drawn into a small patch, then outlined into the scene.
        self.hw_list = arcade.SpriteList()
        self.body = arcade.Sprite(art.ship_body)
        self.flash = arcade.Sprite(art.ship_flash)
        self.hw_list.append(self.body)
        self.hw_list.append(self.flash)
        self.flames = arcade.SpriteList()
        self.flame = {key: arcade.Sprite(art.flame[key, 0]) for key in "WSAD"}
        for s in self.flame.values():
            self.flames.append(s)
        self.ship_light = arcade.SpriteList()
        self.body_light = arcade.Sprite(art.ship_body_light)
        self.ship_light.append(self.body_light)
        self.flame_light = {key: arcade.Sprite(art.flame_light[key, 0]) for key in "WSAD"}
        for s in self.flame_light.values():
            self.ship_light.append(s)

        self.k = 0
        self.fb = (0, 0)
        self.origin = (0, 0)
        self.resize(*window.get_framebuffer_size())

    def set_field(self, field: AsteroidField) -> None:
        """Show this asteroid field: one sprite per rock, plus a glow sprite for ore rocks."""
        art = self.art
        self.field = field
        self.rocks = arcade.SpriteList(capacity=max(1, len(field)))
        self.rock_glow = arcade.SpriteList()
        self.rock_sprites: list[arcade.Sprite] = []
        self.glow_sprites: dict[int, arcade.Sprite] = {}
        for i in range(len(field)):
            key = (int(field.size[i]), int(field.variant[i]), bool(field.ore[i]))
            s = arcade.Sprite(art.rock[key])
            self.rocks.append(s)
            self.rock_sprites.append(s)
            if key in art.rock_light:
                g = arcade.Sprite(art.rock_light[key])
                self.rock_glow.append(g)
                self.glow_sprites[i] = g
        self._rx = np.full(len(field), np.nan)
        self._ry = np.full(len(field), np.nan)
        self.reach = float(field.size.max()) / 2 + 4 if len(field) else 0.0

    # ------------------------------------------------------------ sizing

    def resize(self, fb_w: int, fb_h: int) -> None:
        fb_w, fb_h = max(1, fb_w), max(1, fb_h)
        k = max(1, min(fb_w // VIEW[0], fb_h // VIEW[1]))
        W, H = VIEW[0] * k, VIEW[1] * k
        self.fb = (fb_w, fb_h)
        self.origin = ((fb_w - W) // 2, (fb_h - H) // 2)
        if k == self.k:
            return
        self.k = k
        self.size = (W, H)
        self.scene_tex, self.scene_fbo = render_texture(self.ctx, (W, H))
        self.comp_tex, self.comp_fbo = render_texture(self.ctx, (W, H))
        self.hull_tex, self.hull_fbo = render_texture(self.ctx, (W, H))
        side = self.art.ship_canvas * k + 2       # same parity as the ship, so it sits on whole pixels
        self.hw_tex, self.hw_fbo = render_texture(self.ctx, (side, side))
        self.hw_side = side
        self.world_cam = arcade.Camera2D(viewport=arcade.LBWH(0, 0, W, H), position=(0, 0), zoom=k,
                                         render_target=self.scene_fbo)
        self.hull_cam = arcade.Camera2D(viewport=arcade.LBWH(0, 0, W, H), position=(0, 0), zoom=k,
                                        render_target=self.hull_fbo)
        self.screen_cam = arcade.Camera2D(viewport=arcade.LBWH(0, 0, W, H), position=(W / 2, H / 2),
                                          zoom=1, render_target=self.scene_fbo)
        self.hw_cam = arcade.Camera2D(viewport=arcade.LBWH(0, 0, side, side), position=(0, 0), zoom=1,
                                      render_target=self.hw_fbo)
        self.ui_cam = arcade.Camera2D(viewport=arcade.LBWH(0, 0, W, H),
                                      position=(VIEW[0] / 2, VIEW[1] / 2), zoom=k,
                                      render_target=self.comp_fbo)
        for s in (self.body, self.flash, *self.flame.values()):
            s.scale = k
        self._rx[:] = np.nan     # re-snap every rock for the new pixel size

    def to_game(self, wx: float, wy: float) -> tuple[float, float]:
        """Window framebuffer pixels to game pixels."""
        return (wx - self.origin[0]) / self.k, (wy - self.origin[1]) / self.k

    # ------------------------------------------------------------ syncing sprites

    def _sync_rocks(self) -> None:
        f = self.field
        moved = np.nonzero(~((f.x == self._rx) & (f.y == self._ry)))[0]
        if not len(moved):
            return
        k = self.k
        half = (f.size[moved] + 4) / 2
        cx = snap(f.x[moved] - half, k) + half
        cy = snap(f.y[moved] - half, k) + half
        for j, i in enumerate(moved):
            pos = (float(cx[j]), float(cy[j]))
            self.rock_sprites[i].position = pos
            g = self.glow_sprites.get(int(i))
            if g is not None:
                g.position = pos
        self._rx[moved] = f.x[moved]
        self._ry[moved] = f.y[moved]

    def _wrap_offsets(self, cam_x: float, cam_y: float, half_w: float, half_h: float) -> list[tuple[float, float]]:
        W, H = self.field.width, self.field.height
        xs = [0.0]
        if cam_x - half_w - self.reach < 0:
            xs.append(W)
        if cam_x + half_w + self.reach > W:
            xs.append(-W)
        ys = [0.0]
        if cam_y - half_h - self.reach < 0:
            ys.append(H)
        if cam_y + half_h + self.reach > H:
            ys.append(-H)
        return [(x, y) for x in xs for y in ys]

    # ------------------------------------------------------------ drawing

    def draw(self, view: FrameView, draw_ui) -> None:
        k = self.k
        W, H = self.size
        ctx = self.ctx
        self._sync_rocks()
        cam_x = float(snap(view.cam_x, k))
        cam_y = float(snap(view.cam_y, k))
        offsets = self.backdrop.offsets(view.cam_ux, view.cam_uy, VIEW, k)
        wraps = self._wrap_offsets(cam_x, cam_y, VIEW[0] / 2, VIEW[1] / 2)
        self.under.sync(cam_x, cam_y, k)
        self.over.sync(cam_x, cam_y, k)

        # Where the ship lands on screen, in whole screen pixels.
        rel_x = wrap_delta(view.ship_x - cam_x, self.field.width)
        rel_y = wrap_delta(view.ship_y - cam_y, self.field.height)
        side = self.hw_side
        qx = int(round(rel_x * k + W / 2 - side / 2))
        qy = int(round(rel_y * k + H / 2 - side / 2))
        ship_cx, ship_cy = qx + side / 2, qy + side / 2
        frame = view.flame_frame % 2
        for key in "WSAD":
            lit = key in view.boosters
            s, ls = self.flame[key], self.flame_light[key]
            s.visible = ls.visible = lit
            if lit:
                s.texture = self.art.flame[key, frame]
                ls.texture = self.art.flame_light[key, frame]
            s.angle = ls.angle = view.ship_angle
            s.position = (ship_cx, ship_cy)
            ls.position = (ship_cx / k, ship_cy / k)
        self.body.angle = self.flash.angle = self.body_light.angle = view.ship_angle
        self.body.position = self.flash.position = (0, 0)
        self.flash.alpha = int(255 * max(0.0, min(1.0, view.flash)))
        self.flash.visible = view.flash > 0
        self.body_light.position = (ship_cx / k, ship_cy / k)
        self.body.visible = self.body_light.visible = view.ship_visible
        if not view.ship_visible:
            self.flash.visible = False
            for key in "WSAD":
                self.flame[key].visible = self.flame_light[key].visible = False
        stage = view.stage

        # 1. Scene.
        self.scene_fbo.use()
        self.backdrop.draw(offsets, k, (W, H))
        for ox, oy in wraps:
            self.world_cam.position = (cam_x + ox, cam_y + oy)
            self.world_cam.use()
            self.rocks.draw(pixelated=True)
        self.world_cam.position = (cam_x, cam_y)
        self.world_cam.use()
        if stage is not None:
            stage.under.draw()
        self.under.sprites.draw(pixelated=True)

        # Enemy hulls get their own layer, outlined in one pass after they have turned.
        if stage is not None:
            rect = stage.hull_rect(cam_x, cam_y, k, (W, H))
            if rect is not None:
                self.hull_fbo.use()
                self.hull_fbo.clear(color=(0, 0, 0, 0))
                self.hull_cam.position = (cam_x, cam_y)
                self.hull_cam.use()
                stage.hulls.draw()
                self.scene_fbo.use()
                ctx.viewport = (0, 0, W, H)
                self.enemy_outline.draw_rect(self.hull_tex, rect, k, (W, H))

        if view.ship_visible:
            self.hw_cam.use()
            self.hw_fbo.clear(color=(0, 0, 0, 0))
            self.hw_list.draw(pixelated=True)
            self.scene_fbo.use()
            ctx.viewport = (0, 0, W, H)
            self.outline.draw(self.hw_tex, (qx, qy), k, (W, H))
            self.screen_cam.use()
            self.flames.draw(pixelated=True)
        self.world_cam.use()
        if stage is not None:
            stage.over.draw()
        self.over.sprites.draw(pixelated=True)

        # 2. Light, combined with max() like the art's light layer.
        self.light_fbo.use()
        ctx.viewport = (0, 0, *VIEW)
        self.backdrop.draw_light(offsets, VIEW)
        gl.glBlendEquation(gl.GL_MAX)
        try:
            for ox, oy in wraps:
                self.light_cam.position = (cam_x + ox, cam_y + oy)
                self.light_cam.use()
                self.rock_glow.draw(pixelated=True)
            self.light_cam.position = (cam_x, cam_y)
            self.light_cam.use()
            self.under.light_sprites.draw(pixelated=True)
            self.over.light_sprites.draw(pixelated=True)
            if stage is not None:
                stage.light.draw()
            self.light_screen.use()
            self.ship_light.draw(pixelated=True)
        finally:
            gl.glBlendEquation(gl.GL_FUNC_ADD)
        self.bloom.run(self.light_tex)

        # 3. Composite, then the HUD on top.
        self.comp_fbo.use()
        ctx.viewport = (0, 0, W, H)
        self.composite.draw(self.scene_tex, self.bloom, BLOOM, (W, H))
        self.ui_cam.use()
        draw_ui()

        # 4. Into the window.
        ctx.screen.use()
        ctx.viewport = (0, 0, *self.fb)
        ctx.screen.clear(color=(0, 0, 0, 255))
        self.present.draw(self.comp_tex, self.origin, k, view.crt, self.fb)

    def screenshot(self):
        """The finished frame as a Pillow image (call right after draw)."""
        from PIL import Image
        W, H = self.size
        data = self.ctx.screen.read(viewport=(self.origin[0], self.origin[1], W, H), components=3)
        return Image.frombytes("RGB", (W, H), data).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
