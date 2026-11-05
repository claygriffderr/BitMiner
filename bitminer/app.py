"""The flight test window: input, the game loop, hit effects, and saving tuning as you go."""

from __future__ import annotations

import math
import random
from pathlib import Path

import arcade
import pyglet

from art import sprites as S
from art import pix

from . import settings as settings_mod
from .camera import FollowCamera
from .field import Impact
from .flight import Controls, angle_to, forward_vector, right_vector
from .graphics.particles import Particles
from .graphics.renderer import VIEW, FrameView, Renderer
from .graphics.textures import GameTextures
from .ui.hud import FlightHud
from .ui.panel import TuningPanel
from .world import FlightWorld

TITLE = "BitMiner - Flight Test"
FLAME_FPS = 15            # Booster flames flicker between their two frames this fast.
SAVE_DELAY = 0.5          # Seconds after the last slider change before saving.

# Booster nozzles in ship space (x to the right, y forward, game pixels from the centre), with the
# direction the exhaust leaves in and how many exhaust pixels per second each one puffs out.
NOZZLES = {
    "W": [((0.0, -12.5), (0.0, -1.0), 70.0)],
    "S": [((-6.0, 5.5), (0.0, 1.0), 26.0), ((6.0, 5.5), (0.0, 1.0), 26.0)],
    "A": [((11.0, -1.5), (1.0, 0.0), 38.0)],
    "D": [((-11.0, -1.5), (-1.0, 0.0), 38.0)],
}

MOVE_KEYS = {
    arcade.key.W: "forward", arcade.key.UP: "forward",
    arcade.key.S: "back", arcade.key.DOWN: "back",
    arcade.key.A: "left", arcade.key.LEFT: "left",
    arcade.key.D: "right", arcade.key.RIGHT: "right",
}

# The scripted flight used by --smoke: (until second, controls, aim angle or None).
SMOKE_SCRIPT = [
    (0.6, dict(), 0.0),
    (2.4, dict(forward=True), 0.0),
    (3.4, dict(forward=True, right=True), 35.0),
    (4.6, dict(left=True), -60.0),
    (5.8, dict(forward=True), -20.0),
    (6.6, dict(back=True), 30.0),
    (99.0, dict(forward=True, left=True), 120.0),
]


def window_size(screen_w: int, screen_h: int) -> tuple[int, int]:
    """The biggest whole multiple of 640x360 that fits comfortably on the screen."""
    k = max(1, min(int(screen_w * 0.9) // VIEW[0], int(screen_h * 0.85) // VIEW[1]))
    return VIEW[0] * k, VIEW[1] * k


def app_icon() -> list[pyglet.image.ImageData]:
    images = []
    ship = S.player_ship(0.0)
    for k, side in ((2, 48), (3, 64)):
        img = pix.pad(pix.scale(ship, k), (side, side))
        images.append(pyglet.image.ImageData(side, side, "RGBA", img.tobytes(), pitch=-side * 4))
    return images


class FlightTest(arcade.Window):
    def __init__(self, args):
        self.args = args
        if args.settings:
            self.settings_path = Path(args.settings)
        else:
            self.settings_path = settings_mod.settings_path()
            if not self.settings_path.exists() and settings_mod.fallback_path().exists():
                self.settings_path = settings_mod.fallback_path()
        self.settings = settings_mod.load(self.settings_path)
        if args.crt:
            self.settings.display.crt = True
        if args.size:
            w, h = args.size
        else:
            screen = pyglet.display.get_display().get_default_screen()
            w, h = window_size(screen.width, screen.height)
        fullscreen = self.settings.display.fullscreen and not args.size and not args.smoke
        super().__init__(w, h, TITLE, fullscreen=fullscreen, resizable=True, vsync=not args.smoke,
                         antialiasing=False, update_rate=1 / 240, draw_rate=1 / 240, center_window=True)
        self.set_minimum_size(VIEW[0], VIEW[1])
        try:
            self.set_icon(*app_icon())
        except Exception:
            pass
        self.background_color = (0, 0, 0, 255)

        self.world = FlightWorld(seed=args.seed)
        self.textures = GameTextures()
        world_size = (self.world.width, self.world.height)
        self.particles = Particles(self.textures.pixel, world_size, capacity=600)
        self.sparks = Particles(self.textures.pixel, world_size, capacity=200)
        self.renderer = Renderer(self, self.textures, self.world.field, self.particles, self.sparks)
        self.camera = FollowCamera()
        self.panel = TuningPanel(self.textures, self.settings.tuning, self.settings.display)
        self.panel.open = not args.no_panel
        self.hud = FlightHud(self.textures)
        self.set_mouse_visible(False)

        self.down: set[int] = set()       # movement keys held right now
        self.mouse = (VIEW[0] / 2 + 60, VIEW[1] / 2 + 80)   # game pixels
        self.mouse_inside = False
        self.mouse_seen = False   # until the mouse moves, keep the ship's heading
        self.flash = 0.0
        self.flame_clock = 0.0
        self.puff = {}
        self.rng = random.Random(3)
        self._save_at: float | None = None
        self.clock = 0.0
        self._fps_frames, self._fps_time, self._fps = 0, 0.0, None
        self._shots = sorted(args.shots or [])
        self._last_controls = Controls()

    # ------------------------------------------------------------ input

    def _game_mouse(self, x: float, y: float) -> tuple[float, float]:
        ratio = self.get_pixel_ratio()
        return self.renderer.to_game(x * ratio, y * ratio)

    def on_key_press(self, key, modifiers):
        if key in MOVE_KEYS:
            self.down.add(key)
        elif key == arcade.key.TAB:
            self.panel.open = not self.panel.open
            self.panel.dragging = None
        elif key == arcade.key.C:
            self.settings.display.crt = not self.settings.display.crt
            self.panel.refresh()
            self.save_now()
        elif key == arcade.key.R:
            self.world.respawn()
            self.camera.reset()
        elif key == arcade.key.F11 or (key == arcade.key.ENTER and modifiers & arcade.key.MOD_ALT):
            self.set_fullscreen(not self.fullscreen)
            self.settings.display.fullscreen = self.fullscreen
            self.save_now()
        elif key == arcade.key.ESCAPE:
            self.close()

    def on_key_release(self, key, modifiers):
        self.down.discard(key)

    def on_deactivate(self):
        self.down.clear()   # don't keep a booster stuck on when the window loses focus

    def on_mouse_motion(self, x, y, dx, dy):
        self.mouse = self._game_mouse(x, y)
        self.mouse_inside = self.mouse_seen = True
        if self.panel.open:
            if self.panel.on_motion(*self.mouse) == "tuning":
                self.schedule_save()

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        self.on_mouse_motion(x, y, dx, dy)

    def on_mouse_press(self, x, y, button, modifiers):
        self.mouse = self._game_mouse(x, y)
        if self.panel.contains(*self.mouse):
            changed = self.panel.on_press(*self.mouse)
            if changed == "display":
                self.save_now()
            elif changed == "tuning":
                self.schedule_save()

    def on_mouse_release(self, x, y, button, modifiers):
        if self.panel.on_release():
            self.save_now()

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        gx, gy = self._game_mouse(x, y)
        if self.panel.contains(gx, gy) and scroll_y and self.panel.on_scroll(gx, gy, scroll_y):
            self.schedule_save()

    def on_mouse_leave(self, x, y):
        self.mouse_inside = False

    def on_resize(self, width, height):
        super().on_resize(width, height)
        self.renderer.resize(*self.get_framebuffer_size())

    def on_close(self):
        if self._save_at is not None:
            self.save_now()
        super().on_close()

    # ------------------------------------------------------------ saving

    def schedule_save(self) -> None:
        self._save_at = self.clock + SAVE_DELAY

    def save_now(self) -> None:
        self._save_at = None
        if self.args.smoke and not self.args.settings:
            return   # scripted runs never touch the real settings file
        try:
            settings_mod.save(self.settings, self.settings_path)
            self.panel.flash("SAVED")
            return
        except OSError:
            pass
        try:   # the program's folder can be read-only on some PCs
            self.settings_path = settings_mod.fallback_path()
            settings_mod.save(self.settings, self.settings_path)
            self.panel.flash("SAVED")
        except OSError:
            self.panel.flash("COULD NOT SAVE")

    # ------------------------------------------------------------ game loop

    def ship_on_screen(self) -> tuple[float, float]:
        """The ship sits this far from the view centre, opposite the camera's look-ahead."""
        ox, oy = self.camera.offset()
        return VIEW[0] / 2 - ox, VIEW[1] / 2 - oy

    def controls(self) -> Controls:
        if self.args.smoke:
            for until, keys, aim in SMOKE_SCRIPT:
                if self.clock < until:
                    return Controls(**keys, aim=aim)
        over_ui = self.panel.contains(*self.mouse) or self.panel.dragging is not None
        aim = None
        if self.mouse_seen and not over_ui:
            sx, sy = self.ship_on_screen()
            dx, dy = self.mouse[0] - sx, self.mouse[1] - sy
            if dx * dx + dy * dy > 4:
                aim = angle_to(dx, dy)
        held = {MOVE_KEYS[k] for k in self.down}
        return Controls(forward="forward" in held, back="back" in held, left="left" in held,
                        right="right" in held, aim=aim)

    def on_update(self, delta_time):
        dt = 1 / 60 if self.args.smoke else min(delta_time, 0.1)
        self.clock += dt
        tuning = self.settings.tuning
        controls = self.controls()
        self._last_controls = controls
        impacts = self.world.step(controls, tuning, dt)
        self.hit_effects(impacts)
        self.exhaust(controls, dt)
        self.particles.step(dt)
        self.sparks.step(dt)
        self.camera.update(self.world.ship, tuning, dt)
        self.flash = max(0.0, self.flash - dt * 8)
        self.flame_clock += dt
        self.panel.update(dt)
        self._fps_frames += 1
        self._fps_time += delta_time
        if self._fps_time >= 0.5:
            self._fps = self._fps_frames / self._fps_time
            self._fps_frames, self._fps_time = 0, 0.0
        self.hud.update(dt, self.world.ship.speed, tuning.top_speed, self._fps)
        over_ui = self.panel.contains(*self.mouse)
        self.hud.set_cursor(*self.mouse, over_ui)
        if self._save_at is not None and self.clock >= self._save_at:
            self.save_now()
        if self.args.smoke and self.clock >= self.args.smoke and not self._shots:
            self.close()

    def hit_effects(self, impacts: list[Impact]) -> None:
        mass = max(0.05, self.settings.tuning.mass)
        ship = self.world.ship
        strongest = 0.0
        for hit in impacts:
            dv = hit.impulse / mass
            if dv < 12:
                continue    # resting contact and grazes don't spark
            strongest = max(strongest, hit.impulse)
            away = math.atan2(-hit.ny, -hit.nx)
            carry = (ship.vx * 0.25, ship.vy * 0.25)
            # Sparks skid off along the rock's surface, both ways, angled a little away from it.
            count = int(min(30, max(4, dv / 8)))
            for side in (1, -1):
                self.sparks.burst("spark", hit.x, hit.y, away + side * 1.15, 0.35, count // 2,
                                  (40, 70 + dv * 0.6), (0.18, 0.45), carry)
            self.particles.burst("dust", hit.x + hit.nx * 2, hit.y + hit.ny * 2, away, 1.0,
                                 int(min(14, max(2, dv / 18))), (8, 30 + dv * 0.2), (0.4, 1.0))
            self.camera.kick(max(0.0, min(0.75, (dv - 25) / 260)))
            self.flash = max(self.flash, min(1.0, dv / 160) * 0.7)
        if strongest > 0:
            self.hud.show_hit(strongest)

    def exhaust(self, controls: Controls, dt: float) -> None:
        ship = self.world.ship
        fx, fy = forward_vector(ship.angle)
        rx, ry = right_vector(ship.angle)
        for key in controls.boosters():
            for n, ((lx, ly), (dx, dy), rate) in enumerate(NOZZLES[key]):
                tag = (key, n)
                self.puff[tag] = self.puff.get(tag, self.rng.random()) + rate * dt
                while self.puff[tag] >= 1:
                    self.puff[tag] -= 1
                    px = ship.x + lx * rx + ly * fx
                    py = ship.y + lx * ry + ly * fy
                    wx, wy = dx * rx + dy * fx, dx * ry + dy * fy
                    speed = self.rng.uniform(40, 85)
                    jitter = self.rng.uniform(-14, 14)
                    vx = ship.vx + wx * speed - wy * jitter
                    vy = ship.vy + wy * speed + wx * jitter
                    self.particles.emit("exhaust", px, py, vx, vy, self.rng.uniform(0.12, 0.28))

    def on_draw(self):
        ship = self.world.ship
        ox, oy = self.camera.offset()
        view = FrameView(
            cam_x=(ship.x + ox) % self.world.width, cam_y=(ship.y + oy) % self.world.height,
            cam_ux=ship.ux + ox, cam_uy=ship.uy + oy,
            ship_x=ship.x, ship_y=ship.y, ship_angle=ship.angle,
            boosters=self._last_controls.boosters(), flame_frame=int(self.flame_clock * FLAME_FPS),
            flash=self.flash, crt=self.settings.display.crt,
        )
        self.renderer.draw(view, self.draw_ui)
        if self._shots and self.clock >= self._shots[0]:
            self._shots.pop(0)
            out = Path(self.args.shot_dir or ".")
            out.mkdir(parents=True, exist_ok=True)
            self.renderer.screenshot().save(out / f"shot_{self.clock:05.2f}.png")
            if not self._shots and self.args.smoke and self.clock >= self.args.smoke:
                self.close()

    def draw_ui(self) -> None:
        self.hud.draw()
        self.panel.draw()
        if self.mouse_inside or self.args.smoke:
            self.hud.draw_cursor()


def run(args) -> None:
    FlightTest(args)
    arcade.run()
