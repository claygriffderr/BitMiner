import numpy as np
import pytest

from bitminer.field import AsteroidField, collision_radius, wrap_delta
from bitminer.flight import Ship

W, H = 3200.0, 2000.0


def lone_rock(x, y, size=48, vx=0.0, vy=0.0) -> AsteroidField:
    f = AsteroidField(W, H)
    f.add(x, y, size, 0, False)
    f.vx[0], f.vy[0] = vx, vy
    return f


def test_wrap_delta_takes_the_short_way():
    assert wrap_delta(10, 100) == 10
    assert wrap_delta(90, 100) == -10
    assert wrap_delta(-90, 100) == 10
    assert np.allclose(wrap_delta(np.array([60.0, -60.0]), 100), [-40, 40])


def test_flight_test_field_is_valid_and_repeatable():
    spawn = (1600.0, 1230.0)
    a = AsteroidField.flight_test(W, H, seed=7, spawn=spawn)
    b = AsteroidField.flight_test(W, H, seed=7, spawn=spawn)
    assert len(a) > 400
    assert np.array_equal(a.x, b.x) and np.array_equal(a.size, b.size)
    assert np.all((a.x >= 0) & (a.x < W) & (a.y >= 0) & (a.y < H))
    # No rock overlaps another.
    for i in range(len(a)):
        dx = wrap_delta(a.x - a.x[i], W)
        dy = wrap_delta(a.y - a.y[i], H)
        d = np.hypot(dx, dy)
        d[i] = np.inf
        assert np.all(d >= a.r + a.r[i])
    # The spawn point is clear.
    d = np.hypot(wrap_delta(a.x - spawn[0], W), wrap_delta(a.y - spawn[1], H))
    assert np.all(d > 150 + a.r)
    # A mix of sizes, some carrying ore.
    assert len(set(a.size.tolist())) >= 6
    assert 0 < a.ore.sum() < len(a)


def test_head_on_hit_bounces_the_ship_and_keeps_momentum():
    f = lone_rock(110, 100, size=24)
    ship = Ship(110 - collision_radius(24) - 6.5, 100, vx=200)   # overlapping by half a pixel
    mass = 1.0
    before = mass * ship.vx + f.m[0] * f.vx[0]
    impacts = f.collide_ship(ship, mass, bounce=0.4)
    after = mass * ship.vx + f.m[0] * f.vx[0]
    assert len(impacts) == 1
    assert after == pytest.approx(before)
    assert f.vx[0] > 0                 # the rock is knocked away
    assert ship.vx < 200               # the ship loses speed
    assert impacts[0].nx == pytest.approx(1) and impacts[0].impulse > 0
    # Pushed apart, so they no longer overlap.
    assert abs(f.x[0] - ship.x) >= f.r[0] + ship.radius - 1e-6


def test_hits_never_add_energy():
    for bounce in (0.0, 0.4, 1.0):
        f = lone_rock(110, 100, size=32)
        ship = Ship(110 - collision_radius(32) - 6.5, 100.3, vx=180, vy=-30)
        e0 = 0.5 * 1.2 * (ship.vx ** 2 + ship.vy ** 2)
        f.collide_ship(ship, 1.2, bounce)
        e1 = 0.5 * 1.2 * (ship.vx ** 2 + ship.vy ** 2) + 0.5 * f.m[0] * (f.vx[0] ** 2 + f.vy[0] ** 2)
        assert e1 <= e0 + 1e-6


def test_heavier_ship_knocks_rocks_harder_and_is_knocked_less():
    results = {}
    for mass in (0.5, 3.0):
        f = lone_rock(110, 100, size=32)
        ship = Ship(110 - collision_radius(32) - 6.5, 100, vx=150)
        f.collide_ship(ship, mass, 0.4)
        results[mass] = (f.vx[0], 150 - ship.vx)
    assert results[3.0][0] > results[0.5][0]
    assert results[3.0][1] < results[0.5][1]


def test_collision_works_across_the_wrap_seam():
    f = lone_rock(2.0, 500, size=18)
    ship = Ship(W - 4.0, 500, vx=100)
    impacts = f.collide_ship(ship, 1.0, 0.4)
    assert len(impacts) == 1
    assert f.vx[0] > 0
    assert impacts[0].nx == pytest.approx(1)


def test_separating_contact_is_not_a_hit():
    f = lone_rock(110, 100, size=24)
    ship = Ship(110 - collision_radius(24) - 6.5, 100, vx=-50)
    assert f.collide_ship(ship, 1.0, 0.4) == []


def test_pushed_rocks_drift_bump_and_come_to_rest():
    f = AsteroidField(W, H)
    f.add(100, 100, 24, 0, False)
    f.add(160, 100, 24, 1, False)
    f.vx[0] = 120.0
    hit = False
    for _ in range(120 * 60):
        f.step(1 / 120)
        hit = hit or f.vx[1] > 0
    assert hit                              # the moving rock knocked the other one
    assert len(f.awake) == 0                # and both settled down
    d = np.hypot(wrap_delta(f.x[1] - f.x[0], W), wrap_delta(f.y[1] - f.y[0], H))
    assert d >= f.r[0] + f.r[1] - 1e-6


def test_near_finds_rocks_around_a_point_across_the_seam():
    f = AsteroidField(W, H)
    f.add(5, 5, 24, 0, False)
    f.add(1600, 1000, 24, 0, False)
    idx, dx, dy = f.near(W - 10, H - 10, 50, 50)
    assert idx.tolist() == [0]
    assert dx[0] == pytest.approx(15) and dy[0] == pytest.approx(15)


# ---------------------------------------------------------------- the lookup grid

def brute_near(f, x, y, hw, hh):
    reach = f.size / 2 + 4
    dx = wrap_delta(f.x - x, f.width)
    dy = wrap_delta(f.y - y, f.height)
    return set(np.nonzero((np.abs(dx) <= hw + reach) & (np.abs(dy) <= hh + reach))[0].tolist())


def test_grid_lookups_match_a_full_scan_everywhere_including_the_seam():
    f = AsteroidField.flight_test(W, H, seed=3)
    rng = np.random.default_rng(1)
    spots = [(0.0, 0.0), (W - 1, H - 1), (W / 2, 0.5), (5.0, H / 2)]
    spots += [(float(rng.uniform(0, W)), float(rng.uniform(0, H))) for _ in range(200)]
    for x, y in spots:
        for hw, hh in ((4, 4), (60, 20), (300, 300)):
            idx, dx, dy = f.near(x, y, hw, hh)
            assert set(idx.tolist()) == brute_near(f, x, y, hw, hh)
            assert np.allclose(dx, wrap_delta(f.x[idx] - x, W))
            assert np.allclose(dy, wrap_delta(f.y[idx] - y, H))


def test_rocks_are_refiled_when_they_move():
    f = AsteroidField.flight_test(W, H, seed=3)
    # Shove a handful of rocks hard, across the seam too, and let them drift and bump.
    for i in range(0, 60, 6):
        f.vx[i], f.vy[i] = 400.0, -300.0
    for _ in range(240):
        f.step(1 / 60)
    for x, y in [(float(f.x[i]), float(f.y[i])) for i in range(0, 60, 6)]:
        assert set(f.near(x, y, 40, 40)[0].tolist()) == brute_near(f, x, y, 40, 40)
    # Every rock is filed under exactly the cell it sits in.
    filed = sorted(i for cell in f._grid.values() for i in cell)
    assert filed == list(range(len(f)))
    for i in range(len(f)):
        assert f._cell[i] == f._key(f.x[i], f.y[i])


def test_the_ship_pushing_a_rock_refiles_it():
    f = lone_rock(64.0, 64.0, size=32)
    ship = Ship(64.0 - 40, 64.0)
    ship.vx = 600.0
    for _ in range(120):
        ship.x += ship.vx / 120
        f.collide_ship(ship, 4.0, 0.5)
        f.step(1 / 120)
    assert f._cell[0] == f._key(f.x[0], f.y[0])
    assert 0 in f.near(float(f.x[0]), float(f.y[0]), 1, 1)[0]
