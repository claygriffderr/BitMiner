"""The game window: settings, the shared renderer and tuning panel, and the screens you move between.

The window starts on the menu (or straight into a mode with --mode), and each screen is an
Arcade View: the menu, the flight test and the weapon gallery. Keys that work everywhere (full
screen, CRT filter, the tuning panel) and scripted runs for the build machine live here.
"""

from __future__ import annotations

import time
from pathlib import Path

import arcade
import pyglet

from art import pix
from art import sprites as S

from . import settings as settings_mod
from .field import AsteroidField
from .graphics.particles import Particles
from .graphics.renderer import VIEW, Renderer
from .graphics.textures import GameTextures
from .ui.panel import TuningPanel

TITLE = "BitMiner"
SAVE_DELAY = 0.5          # Seconds after the last slider change before saving.


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


class GameWindow(arcade.Window):
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
        scripted = bool(args.smoke or args.record)
        if args.size:
            w, h = args.size
        else:
            screen = pyglet.display.get_display().get_default_screen()
            w, h = window_size(screen.width, screen.height)
        fullscreen = self.settings.display.fullscreen and not args.size and not scripted
        super().__init__(w, h, TITLE, fullscreen=fullscreen, resizable=True, vsync=not scripted,
                         antialiasing=False, update_rate=1 / 240, draw_rate=1 / 240, center_window=True)
        self.set_minimum_size(VIEW[0], VIEW[1])
        try:
            self.set_icon(*app_icon())
        except Exception:
            pass
        self.background_color = (0, 0, 0, 255)

        self.textures = GameTextures()
        self.empty_field = AsteroidField(3200.0, 2000.0)
        self.no_particles = Particles(self.textures.pixel, (3200.0, 2000.0), capacity=1)
        self.renderer = Renderer(self, self.textures, self.empty_field, self.no_particles, self.no_particles)
        self.panel = TuningPanel(self.textures, self.settings.tuning, self.settings.display)
        self.panel.open = False
        self.set_mouse_visible(False)

        self.mouse = (VIEW[0] / 2 + 60, VIEW[1] / 2 + 80)   # game pixels
        self.mouse_inside = False
        self.mouse_seen = False
        self.clock = 0.0          # seconds since start, in game time
        self._save_at: float | None = None
        self._shots = sorted(args.shots or [])
        self._fps_frames, self._fps_time, self.fps = 0, 0.0, None
        self.views: dict[str, arcade.View] = {}

    # ------------------------------------------------------------ screens

    def go(self, name: str) -> None:
        """Show a screen by name: menu, flight, sandbox or gallery. Each is built the first time."""
        if name == "quit":
            self.close()
            return
        view = self.views.get(name)
        if view is None:
            if name == "menu":
                from .views.menu import MenuView
                view = MenuView(self)
            elif name == "flight":
                from .views.flight import FlightView
                view = FlightView(self)
            elif name == "sandbox":
                from .views.sandbox import SandboxView
                view = SandboxView(self)
            else:
                from .views.gallery import GalleryView
                view = GalleryView(self)
            self.views[name] = view
        self.show_view(view)

    # ------------------------------------------------------------ input that works everywhere

    def game_mouse(self, x: float, y: float) -> tuple[float, float]:
        ratio = self.get_pixel_ratio()
        return self.renderer.to_game(x * ratio, y * ratio)

    def on_key_press(self, key, modifiers):
        if key == arcade.key.TAB:
            self.panel.open = not self.panel.open
            self.panel.dragging = None
        elif key == arcade.key.C:
            self.settings.display.crt = not self.settings.display.crt
            self.panel.refresh()
            self.save_now()
        elif key == arcade.key.F11 or (key == arcade.key.ENTER and modifiers & arcade.key.MOD_ALT):
            self.set_fullscreen(not self.fullscreen)
            self.settings.display.fullscreen = self.fullscreen
            self.save_now()

    def on_mouse_motion(self, x, y, dx, dy):
        self.mouse = self.game_mouse(x, y)
        self.mouse_inside = self.mouse_seen = True
        if self.panel.open and self.panel.on_motion(*self.mouse) == "tuning":
            self.schedule_save()

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        self.on_mouse_motion(x, y, dx, dy)

    def on_mouse_press(self, x, y, button, modifiers):
        self.mouse = self.game_mouse(x, y)
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
        gx, gy = self.game_mouse(x, y)
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
        for view in self.views.values():
            if hasattr(view, "shutdown"):
                view.shutdown()
        super().on_close()

    def over_panel(self) -> bool:
        return self.panel.contains(*self.mouse) or self.panel.dragging is not None

    # ------------------------------------------------------------ saving

    def schedule_save(self) -> None:
        self._save_at = self.clock + SAVE_DELAY

    def save_now(self) -> None:
        self._save_at = None
        if (self.args.smoke or self.args.record) and not self.args.settings:
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

    # ------------------------------------------------------------ the clock, scripted runs

    def tick(self, dt: float, real_dt: float) -> None:
        """Called by the current screen every update."""
        self.clock += dt
        self.panel.update(dt)
        self._fps_frames += 1
        self._fps_time += real_dt
        if self._fps_time >= 0.5:
            self.fps = self._fps_frames / self._fps_time
            self._fps_frames, self._fps_time = 0, 0.0
        if self._save_at is not None and self.clock >= self._save_at:
            self.save_now()
        if self.args.smoke:
            self._smoke_progress()
            if self.clock >= self.args.smoke and not self._shots:
                self.close()

    def frame_dt(self, delta_time: float) -> float:
        return 1 / 60 if (self.args.smoke or self.args.record) else min(delta_time, 0.1)

    def after_draw(self) -> None:
        """Take any screenshots that are due (scripted runs)."""
        if self._shots and self.clock >= self._shots[0]:
            self._shots.pop(0)
            out = Path(self.args.shot_dir or ".")
            out.mkdir(parents=True, exist_ok=True)
            self.renderer.screenshot().save(out / f"shot_{self.clock:05.2f}.png")
            if not self._shots and self.args.smoke and self.clock >= self.args.smoke:
                self.close()

    def _smoke_progress(self) -> None:
        """Every half second of game time, note how far a scripted run has got and how fast it runs."""
        frame = round(self.clock * 60)
        if frame % 30 or not self.args.shot_dir:
            return
        now = time.perf_counter()
        if not hasattr(self, "_smoke_start"):
            self._smoke_start = now
            info = self.ctx.info
            line = f"GL {self.ctx.gl_version} {info.RENDERER} / {info.VENDOR}, framebuffer {self.get_framebuffer_size()}"
        else:
            line = f"game time {self.clock:.1f}s after {now - self._smoke_start:.1f}s real"
        path = Path(self.args.shot_dir)
        path.mkdir(parents=True, exist_ok=True)
        with open(path / "progress.txt", "a") as f:
            f.write(line + "\n")


def run(args) -> None:
    window = GameWindow(args)
    mode = args.mode or ("gallery" if args.record else "flight" if args.smoke else "menu")
    window.go(mode)
    arcade.run()
