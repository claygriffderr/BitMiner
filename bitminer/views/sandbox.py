"""The combat sandbox: fight wave after wave in the flight test's asteroid field.

WASD flies, the mouse aims, click fires, 1 to 4 or the mouse wheel picks a weapon, N calls the
next wave early, P pauses. Going down costs nothing here: you are back a moment later.
"""

from __future__ import annotations

import random

import arcade

from ..camera import FollowCamera
from ..combat.sandbox import Sandbox, autopilot
from ..flight import Controls, angle_to
from ..graphics.combat_draw import StageDrawer
from ..graphics.particles import Particles
from ..graphics.renderer import VIEW, FrameView
from ..ui.combat_hud import CombatHud
from .flight import FLAME_FPS, boosters_exhaust

FLY_KEYS = {arcade.key.W: "forward", arcade.key.S: "back", arcade.key.A: "left", arcade.key.D: "right"}
WEAPON_KEYS = {arcade.key.KEY_1: "auto", arcade.key.KEY_2: "sniper", arcade.key.KEY_3: "missile",
               arcade.key.KEY_4: "laser"}
BLINK_HZ = 12             # how fast your ship blinks while it can't be hit


class SandboxView(arcade.View):
    HUD = CombatHud
    MODE = "sandbox"

    def __init__(self, window):
        super().__init__(window)
        tex = window.textures
        self.args = window.args
        self.sparks = Particles(tex.pixel, (3200.0, 2000.0), capacity=1800)
        self.smoke = Particles(tex.pixel, (3200.0, 2000.0), capacity=1800)
        self.drawer = StageDrawer(tex.pixel)
        self.camera = FollowCamera()
        self.hud = self.HUD(tex)
        self.rng = random.Random(5)
        self.puff: dict = {}
        self.down: set[int] = set()
        self.trigger = False
        self.paused = False
        self.flame_clock = 0.0
        self.clock = 0.0
        self._controls = Controls()
        self.log = None
        self.sb: Sandbox | None = None
        self.new_fight()

    # ------------------------------------------------------------ the fight

    def new_fight(self) -> None:
        if self.sb is not None and self.log is not None:
            self.log.close(self.sb)
        self.sb = self.make_game()
        self.sparks.alive[:] = False
        self.smoke.alive[:] = False
        self.camera.reset()
        self.clock = 0.0
        self.log = self._open_log()
        if self.window.current_view is self:
            self.window.renderer.set_field(self.sb.world.field)

    def make_game(self):
        return Sandbox(self.sparks, self.smoke, self.window.settings.tuning)

    def _open_log(self):
        from ..combat.specs import PLAYDATA
        args = self.args
        if not PLAYDATA.get("on", True) or ((args.smoke or args.record) and not args.settings):
            return None             # scripted runs leave no files behind
        from ..playdata import PlayLog
        tuning = self.window.settings.tuning
        meta = {"mode": self.MODE, "seed": self.sb.world.field.seed,
                "tuning": {k: getattr(tuning, k) for k in vars(tuning)}}
        return PlayLog(self.window.settings_path.parent / "playdata", meta)

    # ------------------------------------------------------------ input

    def on_show_view(self):
        w = self.window
        w.renderer.set_field(self.sb.world.field)
        w.renderer.under = self.smoke
        w.renderer.over = self.sparks

    def on_hide_view(self):
        self.down.clear()
        self.trigger = False
        if self.log is not None:
            self.log.flush()

    def on_key_press(self, key, modifiers):
        arsenal = self.sb.arsenal
        if key == arcade.key.ESCAPE:
            self.window.go("menu")
            return True
        if key in FLY_KEYS:
            self.down.add(key)
        elif key in WEAPON_KEYS:
            arsenal.select(WEAPON_KEYS[key])
        elif key == arcade.key.Q:
            arsenal.cycle(-1)
        elif key == arcade.key.E:
            arsenal.cycle(1)
        elif key == arcade.key.N and not self.paused:
            self.sb.waves.call_now()
        elif key == arcade.key.P:
            self.paused = not self.paused
            self.hud.show_paused(self.paused)
        elif key == arcade.key.BACKSPACE:
            self.new_fight()

    def on_key_release(self, key, modifiers):
        self.down.discard(key)

    def on_deactivate(self):
        self.down.clear()
        self.trigger = False

    def on_mouse_press(self, x, y, button, modifiers):
        w = self.window
        if w.panel.contains(*w.mouse):
            return
        if button == arcade.MOUSE_BUTTON_LEFT:
            self.trigger = True
        elif button == arcade.MOUSE_BUTTON_RIGHT:
            self.sb.arsenal.cycle(1)

    def on_mouse_release(self, x, y, button, modifiers):
        if button == arcade.MOUSE_BUTTON_LEFT:
            self.trigger = False

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        w = self.window
        if w.panel.contains(*w.mouse) or not scroll_y:
            return
        self.sb.arsenal.cycle(-1 if scroll_y > 0 else 1)
        return True

    # ------------------------------------------------------------ game loop

    def view_centre(self) -> tuple[float, float]:
        ship = self.sb.ship
        ox, oy = self.camera.offset()
        return ship.x + ox, ship.y + oy

    def cursor_world(self) -> tuple[float, float]:
        cx, cy = self.view_centre()
        mx, my = self.window.mouse
        return cx + mx - VIEW[0] / 2, cy + my - VIEW[1] / 2

    def controls(self) -> Controls:
        w = self.window
        held = {FLY_KEYS[k] for k in self.down}
        aim = None
        if w.mouse_seen and not w.over_panel():
            ship = self.sb.ship
            cx, cy = self.cursor_world()
            dx, dy = cx - ship.x, cy - ship.y
            if dx * dx + dy * dy > 4:
                aim = angle_to(dx, dy)
        return Controls(forward="forward" in held, back="back" in held, left="left" in held,
                        right="right" in held, aim=aim)

    def on_update(self, delta_time):
        w = self.window
        dt = w.frame_dt(delta_time)
        if self.paused:
            w.tick(dt, delta_time)
            return
        self.advance(dt)
        w.tick(dt, delta_time)

    def advance(self, dt: float) -> None:
        w = self.window
        sb = self.sb
        st = sb.stage
        self.clock += dt
        controls, trigger, cursor = self.pilot()
        # No flames while the ship can't move: down, docked, or holding still to charge the laser.
        still = st.ship_down or sb.arsenal.charging or getattr(sb, "station_open", False)
        self._controls = Controls() if still else controls
        events = self.step_game(dt, controls, trigger, cursor)
        if self.log is not None:
            self.log.record(dt, events, sb)
        if not st.ship_down:
            boosters_exhaust(self.smoke, self.puff, self.rng, st.ship, controls, dt)
        self.sparks.step(dt)
        self.smoke.step(dt)
        if st.kick:
            self.camera.kick(min(1.0, st.kick))
            st.kick = 0.0
        if self.args.smoke:
            aim = None if cursor is None else ((cursor[0] - st.ship.x) * 0.5, (cursor[1] - st.ship.y) * 0.5)
        elif w.mouse_seen and not w.over_panel():
            aim = (w.mouse[0] - VIEW[0] / 2, w.mouse[1] - VIEW[1] / 2)
        else:
            aim = None
        self.camera.update(st.ship, w.settings.tuning, dt, aim, hold=self.camera_hold())
        self.flame_clock += dt
        self.hud.update(dt, sb)
        self.hud.set_fps(w.fps)
        self.place_arrows()
        over_ui = w.panel.contains(*w.mouse)
        self.hud.set_cursor(*w.mouse, over_ui, w.mouse_inside or bool(self.args.smoke))

    def pilot(self):
        """Controls, trigger and cursor for this frame: yours, or the autopilot's in a scripted run."""
        if self.args.smoke:
            return autopilot(self.sb, self.clock)
        w = self.window
        return self.controls(), self.trigger and not w.over_panel(), self.cursor_world()

    def step_game(self, dt: float, controls: Controls, trigger: bool, cursor) -> list:
        return self.sb.step(dt, controls, trigger, cursor)

    def camera_hold(self):
        """Where the view should sit relative to the ship, or None to follow it as usual."""
        return None

    def place_arrows(self) -> None:
        """Arrows at the screen edge toward enemies just off screen."""
        cx, cy = self.view_centre()
        half = (VIEW[0] / 2 + 4, VIEW[1] / 2 + 4)
        self.hud.place_arrows([(e.x - cx, e.y - cy, e.kind, d) for e, d in self.sb.offscreen((cx, cy), half)])

    def frame(self) -> FrameView:
        w = self.window
        st = self.sb.stage
        cx, cy = self.view_centre()
        self.drawer.sync(st, w.renderer.k)
        ship = st.ship
        ox, oy = self.camera.offset()
        blink = st.invulnerable > 0 and int(st.invulnerable * BLINK_HZ) % 2 == 1
        gear = getattr(self.sb, "gear", None)          # Secure the Base's upgrades
        boost = gear.levels["boost"] if gear is not None and gear.boosting else 0
        return FrameView(
            cam_x=cx, cam_y=cy, cam_ux=ship.ux + ox, cam_uy=ship.uy + oy,
            ship_x=ship.x, ship_y=ship.y, ship_angle=ship.angle,
            boosters=self._controls.boosters(), flame_frame=int(self.flame_clock * FLAME_FPS),
            flash=st.ship_flash, crt=w.settings.display.crt, ship_visible=st.ship_visible and not blink,
            stage=self.drawer, missiles=st.missiles_loaded if "missile" in self.sb.arsenal.owned else 0,
            boost=boost)

    def on_draw(self):
        w = self.window
        w.renderer.draw(self.frame(), self.draw_ui)
        w.after_draw()
        return True

    def draw_ui(self) -> None:
        w = self.window
        self.hud.draw()
        w.panel.draw()
        if w.mouse_inside or self.args.smoke:
            self.hud.draw_cursor()

    def shutdown(self) -> None:
        """The window is closing: finish the play log."""
        if self.log is not None:
            self.log.close(self.sb)
            self.log = None
