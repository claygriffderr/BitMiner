import math

import pytest

from bitminer.flight import Controls, Ship, angle_to, forward_vector, right_vector, wrap_angle
from bitminer.settings import Tuning

W, H = 3200.0, 2000.0


def still(**kw) -> Tuning:
    """Tuning with the damper and cap out of the way, so thrust is easy to measure."""
    kw.setdefault("mass", 1.0)
    return Tuning(damper=0.0, top_speed=10_000.0, **kw)


def run(ship, controls, tuning, seconds, dt=1 / 120):
    for _ in range(round(seconds / dt)):
        ship.step(controls, tuning, dt, W, H)


def test_vectors_follow_clockwise_angles():
    assert forward_vector(0) == pytest.approx((0, 1))
    assert forward_vector(90) == pytest.approx((1, 0))
    assert right_vector(0) == pytest.approx((1, 0))
    assert right_vector(90) == pytest.approx((0, -1))
    assert angle_to(1, 0) == pytest.approx(90)
    assert angle_to(0, -1) == pytest.approx(180)


def test_wrap_angle():
    assert wrap_angle(190) == pytest.approx(-170)
    assert wrap_angle(-180) == 180
    assert wrap_angle(540) == 180
    assert wrap_angle(-10) == -10


@pytest.mark.parametrize("key,angle,direction,thrust", [
    ("forward", 0, (0, 1), "thrust_main"),
    ("forward", 90, (1, 0), "thrust_main"),
    ("back", 0, (0, -1), "thrust_retro"),
    ("right", 0, (1, 0), "thrust_side"),
    ("left", 0, (-1, 0), "thrust_side"),
    ("right", 90, (0, -1), "thrust_side"),
])
def test_boosters_push_relative_to_the_ship(key, angle, direction, thrust):
    tuning = still()
    ship = Ship(100, 100, angle=angle)
    ax, ay = ship.thrust(Controls(**{key: True}), tuning)
    strength = getattr(tuning, thrust)
    assert (ax, ay) == pytest.approx((direction[0] * strength, direction[1] * strength), abs=1e-9)


def test_front_booster_is_strongest_by_default():
    t = Tuning()
    assert t.thrust_main > t.thrust_side and t.thrust_main > t.thrust_retro


def test_mass_slows_acceleration():
    light, heavy = Ship(0, 0), Ship(0, 0)
    run(light, Controls(forward=True), still(mass=1.0), 0.5)
    run(heavy, Controls(forward=True), still(mass=2.0), 0.5)
    assert heavy.vy == pytest.approx(light.vy / 2)


def test_turning_is_rate_limited_and_takes_the_short_way():
    ship = Ship(0, 0, angle=170)
    tuning = Tuning(turn_rate=120)
    ship.turn(Controls(aim=-170), tuning, 0.05)   # 20 degrees away through 180, 6 degree step
    assert ship.angle == pytest.approx(176)
    ship.turn(Controls(aim=-170), tuning, 1.0)
    assert ship.angle == pytest.approx(-170)


def test_turning_does_not_change_the_drift():
    ship = Ship(0, 0, vx=50, vy=-20)
    tuning = still()
    run(ship, Controls(aim=135), tuning, 1.0)
    assert ship.angle == pytest.approx(135)
    assert (ship.vx, ship.vy) == pytest.approx((50, -20))


def test_no_aim_keeps_heading():
    ship = Ship(0, 0, angle=33)
    ship.turn(Controls(aim=None), Tuning(), 1.0)
    assert ship.angle == 33


def test_damper_bleeds_speed_and_can_be_switched_off():
    damped, free = Ship(0, 0, vx=100), Ship(0, 0, vx=100)
    run(damped, Controls(), Tuning(damper=0.5, top_speed=1000), 2.0)
    run(free, Controls(), Tuning(damper=0.0, top_speed=1000), 2.0)
    assert damped.vx == pytest.approx(100 * math.exp(-1.0), rel=1e-6)
    assert free.vx == pytest.approx(100)


def test_soft_cap_pulls_back_quickly_but_not_instantly():
    ship = Ship(0, 0, vx=400)
    tuning = Tuning(damper=0.0, top_speed=200)
    ship.step(Controls(), tuning, 1 / 120, W, H)
    assert 200 < ship.speed < 400
    run(ship, Controls(), tuning, 1.5)
    assert ship.speed == pytest.approx(200, abs=0.1)


def test_holding_forward_settles_near_top_speed():
    ship = Ship(0, 0)
    tuning = Tuning(damper=0.0, top_speed=240, thrust_main=260, mass=1.0)
    run(ship, Controls(forward=True), tuning, 8.0)
    assert 240 < ship.speed < 300


def test_position_wraps_but_running_distance_does_not():
    ship = Ship(W - 1, 5, vx=120, vy=-120)
    run(ship, Controls(), still(), 0.1)
    assert 0 <= ship.x < W and 0 <= ship.y < H
    assert ship.x == pytest.approx(11)
    assert ship.y == pytest.approx(H - 7)
    assert ship.ux == pytest.approx(W + 11)
    assert ship.uy == pytest.approx(-7)


def test_boosters_report_lit_flames():
    assert Controls(forward=True, left=True).boosters() == ("W", "A")
    assert Controls().boosters() == ()
