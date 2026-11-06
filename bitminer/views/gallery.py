"""The weapon gallery: every weapon against every enemy, and every enemy attack against you.

Left and Right pick a weapon or an enemy attack, Up and Down pick the target or your defense.
The auto pilot plays each scene on a loop; F switches to free-fly so you can try it yourself.
"""

from __future__ import annotations

import random

import arcade

from ..camera import FollowCamera
from ..combat.specs import WEAPONS
from ..combat.stage import Stage
from ..flight import Controls, angle_to
from ..gallery import scenes as SC
from ..gallery.director import ARENA, Director
from ..graphics.combat_draw import StageDrawer
from ..graphics.particles import Particles
from ..graphics.renderer import VIEW, FrameView
from ..ui.gallery_hud import GalleryHud
from .flight import FLAME_FPS, boosters_exhaust

WORLD = (3200.0, 2000.0)
CENTRE = (WORLD[0] / 2, WORLD[1] / 2)
FLY_KEYS = {arcade.key.W: "forward", arcade.key.S: "back", arcade.key.A: "left", arcade.key.D: "right"}
WEAPON_KEYS = {arcade.key.KEY_1: "auto", arcade.key.KEY_2: "sniper", arcade.key.KEY_3: "missile",
               arcade.key.KEY_4: "laser"}


class GalleryView(arcade.View):
    def __init__(self, window):
        super().__init__(window)
        tex = window.textures
        self.sparks = Particles(tex.pixel, WORLD, capacity=1600)
        self.smoke = Particles(tex.pixel, WORLD, capacity=1400)
        self.stage = Stage(self.sparks, self.smoke, seed=11)
        self.director = Director(self.stage, window.settings.tuning, CENTRE)
        self.drawer = StageDrawer(tex.pixel)
        self.camera = FollowCamera()
        self.hud = GalleryHud(tex)
        self.rng = random.Random(4)
        self.puff: dict = {}
        self.down: set[int] = set()
        self.trigger = False
        self.hover = None
        self.flame_clock = 0.0
        self._controls = Controls()
        args = window.args
        first = SC.BY_KEY.get(getattr(args, "scene", None) or "", SC.SCENES[0])
        self.column = SC.COLUMNS.index(first.column)
        self.row = SC.rows_of(first.column).index(first.row)
        self.recorder = None
        self.play(self.scene)
        if getattr(args, "record", None):
            from ..record import Recorder
            self.recorder = Recorder(self, args.record, args.scenes)

    # ------------------------------------------------------------ scenes

    @property
    def scene(self) -> SC.Scene:
        col = SC.COLUMNS[self.column]
        rows = SC.rows_of(col)
        return SC.find(col, rows[min(self.row, len(rows) - 1)])

    def play(self, scene: SC.Scene) -> None:
        self.director.start(scene, keep_ship=not self.director.auto)
        self.sparks.alive[:] = False
        self.smoke.alive[:] = False
        if self.director.auto:
            self.camera.reset()
        self._refresh()

    def pick(self, d_column: int = 0, d_row: int = 0) -> None:
        old = self.scene
        if d_column:
            self.column = (self.column + d_column) % len(SC.COLUMNS)
            # Keep the same target or defense when the new column has it.
            rows = SC.rows_of(SC.COLUMNS[self.column])
            self.row = rows.index(old.row) if old.row in rows else min(self.row, len(rows) - 1)
        if d_row:
            rows = SC.rows_of(SC.COLUMNS[self.column])
            self.row = (self.row + d_row) % len(rows)
        self.play(self.scene)

    def _refresh(self) -> None:
        hover = self.hover[1] if self.hover and self.hover[0] == "row" else None
        self.hud.show_scene(self.scene, self.director.auto, self.director.weapon, hover)

    def set_auto(self, auto: bool) -> None:
        d = self.director
        if d.auto == auto:
            return
        d.auto = auto
        if auto:
            self.down.clear()
            self.trigger = False
            d.start(self.scene)
        else:
            d.restart()
        self.camera.reset()
        self._refresh()

    # ------------------------------------------------------------ input

    def on_show_view(self):
        w = self.window
        w.renderer.set_field(w.empty_field)
        w.renderer.under = self.smoke
        w.renderer.over = self.sparks

    def on_hide_view(self):
        self.down.clear()
        self.trigger = False

    def on_key_press(self, key, modifiers):
        d = self.director
        if key == arcade.key.ESCAPE:
            self.window.go("menu")
            return True
        if key in (arcade.key.LEFT, arcade.key.RIGHT):
            self.pick(d_column=-1 if key == arcade.key.LEFT else 1)
        elif key in (arcade.key.UP, arcade.key.DOWN):
            self.pick(d_row=-1 if key == arcade.key.UP else 1)
        elif key == arcade.key.SPACE:
            self.play(self.scene)
        elif key == arcade.key.F:
            self.set_auto(not d.auto)
        elif not d.auto and key in FLY_KEYS:
            self.down.add(key)
        elif not d.auto and key in WEAPON_KEYS:
            d.weapon = WEAPON_KEYS[key]
            self._refresh()
        elif key == arcade.key.R and not d.auto:
            ship = self.stage.ship
            ship.x, ship.y = CENTRE
            ship.vx = ship.vy = 0.0
            self.camera.reset()

    def on_key_release(self, key, modifiers):
        self.down.discard(key)

    def on_deactivate(self):
        self.down.clear()
        self.trigger = False

    def on_mouse_motion(self, x, y, dx, dy):
        w = self.window
        hover = self.hud.hit(*w.mouse)
        if hover != self.hover:
            self.hover = hover
            self._refresh()

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        self.on_mouse_motion(x, y, dx, dy)

    def on_mouse_press(self, x, y, button, modifiers):
        w = self.window
        if w.panel.contains(*w.mouse):
            return
        target = self.hud.hit(*w.mouse)
        if target is not None:
            if target[0] == "column":
                self.pick(d_column=target[1])
            elif target[0] == "row":
                rows = SC.rows_of(SC.COLUMNS[self.column])
                if target[1] < len(rows):
                    self.row = target[1]
                    self.play(self.scene)
            elif target[0] == "mode":
                self.set_auto(not self.director.auto)
            return
        if button == arcade.MOUSE_BUTTON_LEFT and not self.director.auto:
            self.trigger = True

    def on_mouse_release(self, x, y, button, modifiers):
        if button == arcade.MOUSE_BUTTON_LEFT:
            self.trigger = False

    # ------------------------------------------------------------ game loop

    def view_centre(self) -> tuple[float, float]:
        d = self.director
        if d.auto:
            fx, fy = self.scene.focus
            return CENTRE[0] + fx + self.camera.shake_x, CENTRE[1] + fy + self.camera.shake_y
        ship = self.stage.ship
        ox, oy = self.camera.offset()
        return ship.x + ox, ship.y + oy

    def cursor_world(self) -> tuple[float, float]:
        cx, cy = self.view_centre()
        mx, my = self.window.mouse
        return cx + mx - VIEW[0] / 2, cy + my - VIEW[1] / 2

    def controls(self) -> Controls:
        w = self.window
        if self.director.auto:
            return Controls()
        held = {FLY_KEYS[k] for k in self.down}
        aim = None
        if w.mouse_seen and not w.over_panel() and not self.hud.contains(*w.mouse):
            ship = self.stage.ship
            cx, cy = self.cursor_world()
            dx, dy = cx - ship.x, cy - ship.y
            if dx * dx + dy * dy > 4:
                aim = angle_to(dx, dy)
        return Controls(forward="forward" in held, back="back" in held, left="left" in held,
                        right="right" in held, aim=aim)

    def advance(self, dt: float) -> None:
        """One step of the whole gallery: the scene, particles, camera and HUD."""
        w = self.window
        st = self.stage
        d = self.director
        controls = self.controls()
        self._controls = controls
        d.step(dt, controls, self.trigger and not w.over_panel(), self.cursor_world())
        if not d.auto:
            boosters_exhaust(self.smoke, self.puff, self.rng, st.ship, controls, dt)
        self.sparks.step(dt)
        self.smoke.step(dt)
        if st.kick:
            self.camera.kick(st.kick)
            st.kick = 0.0
        self.camera.update(st.ship, w.settings.tuning, dt)
        self.flame_clock += dt
        boss = next((e for e in st.enemies if e.kind == "mothership" and e.alive), None)
        missile = d.scene.column == "missile" if d.auto else d.weapon == "missile"
        rack = None
        if missile:
            reload = float(WEAPONS["missile"]["reload"])
            rack = (st.missiles_loaded, 1.0 - st.missile_reload / reload if st.missile_reload > 0 else 1.0)
        self.hud.update(dt, st.shield, st.shield_max, st.hull, st.hull_max,
                        None if boss is None else boss.health / boss.max_health, rack)
        over_ui = w.panel.contains(*w.mouse) or self.hud.contains(*w.mouse)
        self.hud.set_cursor(*w.mouse, over_ui, w.mouse_inside or bool(w.args.smoke))

    def on_update(self, delta_time):
        w = self.window
        if self.recorder is not None:
            return          # the recorder steps the gallery itself, in step with its frames
        dt = w.frame_dt(delta_time)
        self.advance(dt)
        w.tick(dt, delta_time)

    def frame(self) -> FrameView:
        w = self.window
        st = self.stage
        cx, cy = self.view_centre()
        arena = None
        if not self.director.auto:
            # The fence your ship's centre stops at, pushed out by the hull so the hull touches it.
            ax, ay = ARENA[0] + 10, ARENA[1] + 10
            arena = (CENTRE[0] - ax, CENTRE[1] - ay, CENTRE[0] + ax, CENTRE[1] + ay)
        self.drawer.sync(st, w.renderer.k, arena, self.director.edge_hit)
        ship = st.ship
        return FrameView(
            cam_x=cx, cam_y=cy, cam_ux=cx, cam_uy=cy,
            ship_x=ship.x, ship_y=ship.y, ship_angle=ship.angle,
            boosters=self._controls.boosters(), flame_frame=int(self.flame_clock * FLAME_FPS),
            flash=st.ship_flash, crt=w.settings.display.crt, ship_visible=st.ship_visible,
            stage=self.drawer)

    def on_draw(self):
        w = self.window
        if self.recorder is not None:
            self.recorder.frame()
            return True
        w.renderer.draw(self.frame(), self.draw_ui)
        w.after_draw()
        return True

    def draw_ui(self) -> None:
        w = self.window
        self.hud.draw()
        w.panel.draw()
        if w.mouse_inside or w.args.smoke:
            self.hud.draw_cursor()

