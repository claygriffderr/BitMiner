import math

import pytest

from bitminer.camera import MAX_LEAD, FollowCamera
from bitminer.flight import Controls, Ship
from bitminer.settings import Tuning
from bitminer.world import FlightWorld


def test_camera_looks_ahead_along_the_drift():
    cam = FollowCamera()
    ship = Ship(0, 0, vx=200, vy=0)
    for _ in range(600):
        cam.update(ship, Tuning(camera_lead=1.0), 1 / 120)
    assert cam.offset()[0] == pytest.approx(min(MAX_LEAD[0], 200 * 0.6), rel=0.02)
    for _ in range(600):
        cam.update(ship, Tuning(camera_lead=0.0), 1 / 120)
    assert abs(cam.offset()[0]) < 1


def test_shake_scales_with_setting_and_fades():
    cam = FollowCamera()
    ship = Ship(0, 0)
    cam.kick(0.8)
    peak = 0.0
    for _ in range(30):
        cam.update(ship, Tuning(shake=1.0, camera_lead=0), 1 / 120)
        peak = max(peak, math.hypot(*cam.offset()))
    assert peak > 1
    for _ in range(240):
        cam.update(ship, Tuning(shake=1.0, camera_lead=0), 1 / 120)
    assert cam.trauma == 0 and math.hypot(*cam.offset()) == 0
    cam.kick(0.8)
    cam.update(ship, Tuning(shake=0.0, camera_lead=0), 1 / 120)
    assert cam.offset() == (0, 0)


def test_world_runs_long_flights_without_breaking():
    world = FlightWorld()
    tuning = Tuning()
    hits = 0
    for i in range(60 * 40):
        t = i / 60
        controls = Controls(forward=(i // 90) % 3 != 2, left=(i // 200) % 2 == 0, back=(i // 300) % 4 == 3,
                            aim=(t * 70) % 360 - 180)
        hits += len(world.step(controls, tuning, 1 / 60))
        s = world.ship
        assert 0 <= s.x < world.width and 0 <= s.y < world.height
        assert math.isfinite(s.vx) and math.isfinite(s.vy)
        assert s.speed < tuning.top_speed * 1.6
    assert hits > 0
    assert world.time == pytest.approx(40, abs=1e-6)


def test_long_frames_are_split_into_small_steps():
    world = FlightWorld()
    world.step(Controls(forward=True), Tuning(), 0.04)
    assert world.time == pytest.approx(0.04)
    world.step(Controls(), Tuning(), 5.0)          # a hitch is capped
    assert world.time == pytest.approx(0.09)


def test_respawn_resets_the_ship():
    world = FlightWorld()
    for _ in range(120):
        world.step(Controls(forward=True, aim=90), Tuning(), 1 / 60)
    world.respawn()
    assert (world.ship.x, world.ship.y) == world.spawn
    assert world.ship.speed == 0 and world.ship.angle == 0
