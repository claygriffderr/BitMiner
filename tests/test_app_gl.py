"""Drives the real window: needs OpenGL, so it only runs when BITMINER_GL_TESTS=1 (under xvfb in CI)."""

import json
import os

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("BITMINER_GL_TESTS") != "1", reason="needs an OpenGL display")


@pytest.fixture
def window(tmp_path):
    import arcade
    from bitminer.__main__ import parse
    from bitminer.app import FlightTest

    args = parse(["--size", "1280x720", "--settings", str(tmp_path / "flight_tuning.json")])
    win = FlightTest(args)
    yield win
    win.close()
    arcade.exit() if hasattr(arcade, "exit") else None


def to_window(win, gx, gy):
    """Game pixels to window coordinates."""
    r = win.renderer
    ratio = win.get_pixel_ratio()
    return (gx * r.k + r.origin[0]) / ratio, (gy * r.k + r.origin[1]) / ratio


def frames(win, n=3, dt=1 / 60):
    for _ in range(n):
        win.on_update(dt)
        win.on_draw()


def test_dragging_a_slider_changes_flight_and_saves(window, tmp_path):
    win = window
    frames(win)
    row = win.panel.rows[0]                       # main thrust
    y = row.track_y + 2
    x0, y0 = to_window(win, row.knob.center_x, y)
    x1, _ = to_window(win, 160, y)                # far right end of the track
    win.on_mouse_press(x0, y0, 1, 0)
    win.on_mouse_drag(x1, y0, x1 - x0, 0, 1, 0)
    win.on_mouse_release(x1, y0, 1, 0)
    assert win.settings.tuning.thrust_main == 700
    saved = json.loads((tmp_path / "flight_tuning.json").read_text())
    assert saved["thrust_main"] == 700
    frames(win)


def test_scroll_reset_and_crt_button(window, tmp_path):
    win = window
    frames(win)
    row = win.panel.rows[6]                       # mass
    x, y = to_window(win, 60, row.track_y + 2)
    win.on_mouse_scroll(x, y, 0, 1)
    assert win.settings.tuning.mass == pytest.approx(1.1)
    bx, by = to_window(win, win.panel.reset.left + 3, win.panel.reset.bottom + 3)
    win.on_mouse_press(bx, by, 1, 0)
    assert win.settings.tuning.mass == 1.0
    cx, cy = to_window(win, win.panel.crt.left + 3, win.panel.crt.bottom + 3)
    win.on_mouse_press(cx, cy, 1, 0)
    assert win.settings.display.crt is True
    assert json.loads((tmp_path / "flight_tuning.json").read_text())["crt"] is True
    frames(win)


def test_keys_fly_the_ship_and_mouse_aims(window):
    import arcade
    win = window
    frames(win)
    win.on_mouse_motion(*to_window(win, 600, 180), 0, 0)   # far to the right of the ship
    win.on_key_press(arcade.key.W, 0)
    frames(win, 90)
    win.on_key_release(arcade.key.W, 0)
    ship = win.world.ship
    assert ship.angle == pytest.approx(90, abs=8)
    assert ship.vx > 100
    win.on_key_press(arcade.key.TAB, 0)
    assert not win.panel.open
    frames(win)


def test_resizing_keeps_whole_pixel_scaling(window):
    win = window
    win.on_resize(1920, 1080)
    assert win.renderer.k == min(win.get_framebuffer_size()[0] // 640, win.get_framebuffer_size()[1] // 360)
    frames(win)
