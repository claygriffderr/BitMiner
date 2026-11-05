"""The flight test: fly the ship through the asteroid field, with hit sparks and the tuning panel."""

from __future__ import annotations

import math
import random

import arcade

from ..camera import FollowCamera
from ..field import Impact
from ..flight import Controls, angle_to, forward_vector, right_vector
from ..graphics.particles import Particles
from ..graphics.renderer import VIEW, FrameView
from ..ui.hud import FlightHud
from ..world import FlightWorld

FLAME_FPS = 15            # Booster flames flicker between their two frames this fast.

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


def boosters_exhaust(particles: Particles, puff: dict, rng: random.Random, ship, controls: Controls,
                     dt: float) -> None:
    """Puff exhaust pixels out of every lit booster's nozzles."""
    fx, fy = forward_vector(ship.angle)
    rx, ry = right_vector(ship.angle)
    for key in controls.boosters():
        for n, ((lx, ly), (dx, dy), rate) in enumerate(NOZZLES[key]):
            tag = (key, n)
            puff[tag] = puff.get(tag, rng.random()) + rate * dt
            while puff[tag] >= 1:
                puff[tag] -= 1
                px = ship.x + lx * rx + ly * fx
                py = ship.y + lx * ry + ly * fy
                wx, wy = dx * rx + dy * fx, dx * ry + dy * fy
                speed = rng.uniform(40, 85)
                jitter = rng.uniform(-14, 14)
                vx = ship.vx + wx * speed - wy * jitter
                vy = ship.vy + wy * speed + wx * jitter
                particles.emit("exhaust", px, py, vx, vy, rng.uniform(0.12, 0.28))


class FlightView(arcade.View):
    def __init__(self, window):
        super().__init__(window)
        args = window.args
        self.world = FlightWorld(seed=args.seed)
        world_size = (self.world.width, self.world.height)
        self.particles = Particles(window.textures.pixel, world_size, capacity=600)
        self.sparks = Particles(window.textures.pixel, world_size, capacity=200)
        self.camera = FollowCamera()
        self.hud = FlightHud(window.textures)
        self.down: set[int] = set()       # movement keys held right now
        self.flash = 0.0
        self.flame_clock = 0.0
        self.puff = {}
        self.rng = random.Random(3)
        self.clock = 0.0
        self._last_controls = Controls()
        self._panel_first = not args.no_panel

    def on_show_view(self):
        w = self.window
        w.renderer.set_field(self.world.field)
        w.renderer.under = self.particles
        w.renderer.over = self.sparks
        if self._panel_first:
            w.panel.open = True
            self._panel_first = False

    def on_hide_view(self):
        self.down.clear()

    # ------------------------------------------------------------ input

    def on_key_press(self, key, modifiers):
        if key in MOVE_KEYS:
            self.down.add(key)
        elif key == arcade.key.R:
            self.world.respawn()
            self.camera.reset()
        elif key == arcade.key.ESCAPE:
            self.window.go("menu")
            return True

    def on_key_release(self, key, modifiers):
        self.down.discard(key)

    def on_deactivate(self):
        self.down.clear()   # don't keep a booster stuck on when the window loses focus

    # ------------------------------------------------------------ game loop

    def ship_on_screen(self) -> tuple[float, float]:
        """The ship sits this far from the view centre, opposite the camera's look-ahead."""
        ox, oy = self.camera.offset()
        return VIEW[0] / 2 - ox, VIEW[1] / 2 - oy

    def controls(self) -> Controls:
        w = self.window
        if w.args.smoke:
            for until, keys, aim in SMOKE_SCRIPT:
                if self.clock < until:
                    return Controls(**keys, aim=aim)
        aim = None
        if w.mouse_seen and not w.over_panel():
            sx, sy = self.ship_on_screen()
            dx, dy = w.mouse[0] - sx, w.mouse[1] - sy
            if dx * dx + dy * dy > 4:
                aim = angle_to(dx, dy)
        held = {MOVE_KEYS[k] for k in self.down}
        return Controls(forward="forward" in held, back="back" in held, left="left" in held,
                        right="right" in held, aim=aim)

    def on_update(self, delta_time):
        w = self.window
        dt = w.frame_dt(delta_time)
        self.clock += dt
        tuning = w.settings.tuning
        controls = self.controls()
        self._last_controls = controls
        impacts = self.world.step(controls, tuning, dt)
        self.hit_effects(impacts)
        boosters_exhaust(self.particles, self.puff, self.rng, self.world.ship, controls, dt)
        self.particles.step(dt)
        self.sparks.step(dt)
        self.camera.update(self.world.ship, tuning, dt)
        self.flash = max(0.0, self.flash - dt * 8)
        self.flame_clock += dt
        self.hud.update(dt, self.world.ship.speed, tuning.top_speed, w.fps)
        self.hud.set_cursor(*w.mouse, w.panel.contains(*w.mouse))
        w.tick(dt, delta_time)

    def hit_effects(self, impacts: list[Impact]) -> None:
        mass = max(0.05, self.window.settings.tuning.mass)
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

    def on_draw(self):
        w = self.window
        ship = self.world.ship
        ox, oy = self.camera.offset()
        view = FrameView(
            cam_x=(ship.x + ox) % self.world.width, cam_y=(ship.y + oy) % self.world.height,
            cam_ux=ship.ux + ox, cam_uy=ship.uy + oy,
            ship_x=ship.x, ship_y=ship.y, ship_angle=ship.angle,
            boosters=self._last_controls.boosters(), flame_frame=int(self.flame_clock * FLAME_FPS),
            flash=self.flash, crt=w.settings.display.crt,
        )
        w.renderer.draw(view, self.draw_ui)
        w.after_draw()
        return True

    def draw_ui(self) -> None:
        w = self.window
        self.hud.draw()
        w.panel.draw()
        if w.mouse_inside or w.args.smoke:
            self.hud.draw_cursor()
