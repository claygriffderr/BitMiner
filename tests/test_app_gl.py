"""Drives the real window: needs OpenGL, so it only runs when BITMINER_GL_TESTS=1 (under xvfb in CI)."""

import json
import os

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("BITMINER_GL_TESTS") != "1", reason="needs an OpenGL display")


@pytest.fixture
def make_window(tmp_path):
    made = []

    def make(mode: str = "flight", *extra):
        from bitminer.__main__ import parse
        from bitminer.app import GameWindow

        args = parse(["--size", "1280x720", "--settings", str(tmp_path / "flight_tuning.json"), "--mode", mode,
                      *extra])
        win = GameWindow(args)
        win._enable_event_queue = False      # deliver test events straight away, not on the next tick
        win.go(mode)
        made.append(win)
        return win
    yield make
    for win in made:
        win.close()


@pytest.fixture
def window(make_window):
    return make_window("flight")


def to_window(win, gx, gy):
    """Game pixels to window coordinates."""
    r = win.renderer
    ratio = win.get_pixel_ratio()
    return (gx * r.k + r.origin[0]) / ratio, (gy * r.k + r.origin[1]) / ratio


def send(win, event, *args):
    """Deliver an event the way Arcade does, so the current screen sees it before the window."""
    win.dispatch_event(event, *args)


def frames(win, n=3, dt=1 / 60):
    for _ in range(n):
        send(win, "on_update", dt)
        send(win, "on_draw")


def test_dragging_a_slider_changes_flight_and_saves(window, tmp_path):
    win = window
    frames(win)
    row = win.panel.rows[0]                       # main thrust
    y = row.track_y + 2
    x0, y0 = to_window(win, row.knob.center_x, y)
    x1, _ = to_window(win, 160, y)                # far right end of the track
    send(win, "on_mouse_press", x0, y0, 1, 0)
    send(win, "on_mouse_drag", x1, y0, x1 - x0, 0, 1, 0)
    send(win, "on_mouse_release", x1, y0, 1, 0)
    assert win.settings.tuning.thrust_main == 700
    saved = json.loads((tmp_path / "flight_tuning.json").read_text())
    assert saved["thrust_main"] == 700
    frames(win)


def test_scroll_reset_and_crt_button(window, tmp_path):
    from bitminer.settings import DEFAULTS
    win = window
    frames(win)
    row = win.panel.rows[6]                       # mass
    x, y = to_window(win, 60, row.track_y + 2)
    send(win, "on_mouse_scroll", x, y, 0, 1)
    assert win.settings.tuning.mass == pytest.approx(DEFAULTS["mass"] + 0.1)
    bx, by = to_window(win, win.panel.reset.left + 3, win.panel.reset.bottom + 3)
    send(win, "on_mouse_press", bx, by, 1, 0)
    assert win.settings.tuning.mass == DEFAULTS["mass"]
    cx, cy = to_window(win, win.panel.crt.left + 3, win.panel.crt.bottom + 3)
    send(win, "on_mouse_press", cx, cy, 1, 0)
    assert win.settings.display.crt is True
    assert json.loads((tmp_path / "flight_tuning.json").read_text())["crt"] is True
    frames(win)


def test_keys_fly_the_ship_and_mouse_aims(window):
    import arcade
    win = window
    frames(win)
    send(win, "on_mouse_motion", *to_window(win, 600, 180), 0, 0)   # far to the right of the ship
    send(win, "on_key_press", arcade.key.W, 0)
    frames(win, 90)
    send(win, "on_key_release", arcade.key.W, 0)
    ship = win.views["flight"].world.ship
    assert ship.angle == pytest.approx(90, abs=8)
    assert ship.vx > 100
    send(win, "on_key_press", arcade.key.TAB, 0)
    assert not win.panel.open
    frames(win)


def test_resizing_keeps_whole_pixel_scaling(window):
    win = window
    send(win, "on_resize", 1920, 1080)
    assert win.renderer.k == min(win.get_framebuffer_size()[0] // 640, win.get_framebuffer_size()[1] // 360)
    frames(win)


def test_menu_opens_the_gallery_and_escape_comes_back(make_window):
    import arcade
    win = make_window("menu")
    frames(win)
    send(win, "on_key_press", arcade.key.DOWN, 0)
    send(win, "on_key_press", arcade.key.ENTER, 0)
    assert win.current_view is win.views["gallery"]
    frames(win, 30)
    send(win, "on_key_press", arcade.key.ESCAPE, 0)
    assert win.current_view is win.views["menu"]
    frames(win)


def test_gallery_picks_scenes_and_draws_them(make_window):
    import arcade
    win = make_window("gallery", "--scene", "missile-tank")
    view = win.views["gallery"]
    assert view.scene.key == "missile-tank"
    frames(win, 90)
    tank = next(e for e in view.stage.enemies if e.kind == "tank")
    assert tank.health < tank.max_health                     # the first salvo has landed
    send(win, "on_key_press", arcade.key.RIGHT, 0)
    assert view.scene.key == "laser-tank"
    send(win, "on_key_press", arcade.key.DOWN, 0)
    assert view.scene.key == "laser-mothership"
    frames(win, 60)
    assert view.drawer.bounds is not None                      # the mothership's hull is on screen
    # Every scene draws without trouble for a moment.
    from bitminer.gallery import scenes as SC
    for scene in SC.SCENES:
        view.column = SC.COLUMNS.index(scene.column)
        view.row = SC.rows_of(scene.column).index(scene.row)
        view.play(view.scene)
        frames(win, 20, dt=1 / 20)


def test_free_fly_fires_the_chosen_weapon(make_window):
    import arcade
    win = make_window("gallery", "--scene", "auto-guard")
    view = win.views["gallery"]
    frames(win, 30)
    send(win, "on_key_press", arcade.key.F, 0)
    assert not view.director.auto
    send(win, "on_key_press", arcade.key.KEY_2, 0)
    assert view.director.weapon == "sniper"
    send(win, "on_mouse_motion", *to_window(win, 320, 300), 0, 0)
    send(win, "on_mouse_press", *to_window(win, 320, 300), arcade.MOUSE_BUTTON_LEFT, 0)
    frames(win, 2)
    assert any(s.kind == "sniper" for s in view.stage.shots)
    send(win, "on_mouse_release", *to_window(win, 320, 300), arcade.MOUSE_BUTTON_LEFT, 0)
    send(win, "on_key_press", arcade.key.W, 0)
    frames(win, 30)
    assert view.stage.ship.speed > 20


def test_menu_starts_on_the_combat_sandbox(make_window):
    import arcade
    win = make_window("menu")
    frames(win)
    send(win, "on_key_press", arcade.key.ENTER, 0)
    assert win.current_view is win.views["sandbox"]
    frames(win, 10)
    send(win, "on_key_press", arcade.key.ESCAPE, 0)
    assert win.current_view is win.views["menu"]


def test_sandbox_fights_draws_and_logs(make_window, tmp_path):
    import arcade
    win = make_window("sandbox")
    view = win.views["sandbox"]
    sb = view.sb
    send(win, "on_key_press", arcade.key.KEY_3, 0)
    assert sb.arsenal.weapon == "missile"
    send(win, "on_mouse_motion", *to_window(win, 320, 300), 0, 0)
    send(win, "on_mouse_scroll", *to_window(win, 320, 300), 0, -1)
    assert sb.arsenal.weapon == "laser"
    send(win, "on_key_press", arcade.key.KEY_1, 0)
    send(win, "on_key_press", arcade.key.N, 0)
    frames(win, 30)
    assert sb.waves.number == 1 and sb.stage.enemies
    send(win, "on_mouse_press", *to_window(win, 320, 300), arcade.MOUSE_BUTTON_LEFT, 0)
    frames(win, 30)
    assert any(s.kind == "auto" for s in sb.stage.shots) or sb.stage.events
    send(win, "on_mouse_release", *to_window(win, 320, 300), arcade.MOUSE_BUTTON_LEFT, 0)
    # Off-screen enemies get arrows at the edge.
    for e in sb.stage.enemies:
        e.x, e.y = sb.ship.x + 900, sb.ship.y
    frames(win, 2)
    assert any(s.visible for s in view.hud.arrows)
    send(win, "on_key_press", arcade.key.P, 0)
    t = sb.time
    frames(win, 5)
    assert sb.time == t                       # paused
    send(win, "on_key_press", arcade.key.P, 0)
    view.shutdown()
    logs = list((tmp_path / "playdata").glob("fight-*.jsonl"))
    assert len(logs) == 1
    lines = [json.loads(line) for line in logs[0].read_text().splitlines()]
    assert lines[0]["type"] == "start" and lines[-1]["type"] == "end"
