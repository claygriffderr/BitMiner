"""Sprint 10: the lasso, the collector ring, sentries mounted on it, and drills that float free."""

import math

import pytest

from bitminer.combat.campaign import Campaign
from bitminer.combat.haul import FIELD_R, INNER, MOUNT_DIRS, MOUNT_R, RING_HOOP, RING_RADIUS, Haul
from bitminer.combat.shop import PAGE_ITEMS
from bitminer.combat.specs import DRILLS, HAUL, SHOP
from bitminer.combat.stage import Shot, dist
from bitminer.field import wrap_delta
from bitminer.flight import Controls
from bitminer.settings import Tuning

DT = 1 / 60
LASSO = SHOP["upgrades"]["lasso"]
RING = SHOP["items"]["ring"]


class Quiet:
    def burst(self, *a, **k):
        pass

    def emit(self, *a, **k):
        pass


def campaign(credits: int = 0, **tuning) -> Campaign:
    game = Campaign(Quiet(), Quiet(), Tuning(**tuning), scale=3)
    game.credits = credits
    return game


def clear_space(game: Campaign, dx: float = 2500.0, dy: float = 1500.0, r: float = 700.0) -> tuple[float, float]:
    """Fly the ship far from base and take every asteroid within `r` away. Returns where the ship is."""
    st = game.stage
    f = st.field
    st.ship.x = (st.ship.x + dx) % f.width
    st.ship.y = (st.ship.y + dy) % f.height
    st.ship.vx = st.ship.vy = 0.0
    idx, _, _ = f.near(st.ship.x, st.ship.y, r, r)
    for i in idx.tolist():
        f.remove(i)
    st.recentre()
    return st.ship.x, st.ship.y


def rock(game: Campaign, x: float, y: float, size: int = 48, ore: bool = True) -> int:
    f = game.stage.field
    f.add(x, y, size, 0, ore)
    return len(f) - 1


def step(game: Campaign, seconds: float = DT, controls: Controls | None = None, **keys) -> list:
    events = []
    n = max(1, round(seconds / DT))
    for k in range(n):
        press = {key: v for key, v in keys.items() if key in ("lasso", "place_sentry", "set_drill") and k == 0}
        held = {key: v for key, v in keys.items() if key in ("ring_key",)}
        events += game.step(DT, controls or Controls(), False, None, **press, **held)
    return events


def towed_gap(game: Campaign) -> float:
    h = game.haul
    ax, ay = h.tail()
    rx, ry = h.rock_pos(h.rock)
    return math.hypot(rx - ax, ry - ay)


# ------------------------------------------------------------ the lasso


def test_the_lasso_is_a_3_level_upgrade_at_500_700_900_on_the_tools_page():
    game = campaign(10_000)
    assert LASSO["prices"] == [500, 700, 900]
    assert "lasso" in PAGE_ITEMS["tools"] and "ring" in PAGE_ITEMS["tools"]
    for lv, price in enumerate(LASSO["prices"], start=1):
        o = game.shop.offer("lasso")
        assert o.upgrade and o.price == price
        assert game.shop.buy("lasso") and game.gear.level("lasso") == lv
    assert game.shop.offer("lasso").blocked == "MAX"
    assert game.credits == 10_000 - 2100


def test_each_level_tows_bigger_asteroids():
    sizes = LASSO["max_size"]
    assert sizes == sorted(sizes) and sizes[-1] >= 96
    assert Haul.max_size(0) == 0
    assert Haul.level_for(sizes[0]) == 1 and Haul.level_for(sizes[0] + 1) == 2 and Haul.level_for(96) == 3


def test_q_needs_a_lasso_and_something_in_reach():
    game = campaign()
    x, y = clear_space(game)
    i = rock(game, x + 60, y, 24)
    events = step(game, lasso=True)
    assert ("lasso", "none") in events and game.haul.rock < 0
    game.gear.levels["lasso"] = 1
    game.stage.field.remove(i)
    events = step(game, lasso=True)
    assert ("lasso", "nothing") in events


def test_a_rock_too_big_for_your_level_says_which_level_you_need():
    game = campaign()
    x, y = clear_space(game)
    game.gear.levels["lasso"] = 1
    rock(game, x + 70, y, 64)
    assert game.haul.target()[1] is False
    events = step(game, lasso=True)
    assert any(ev[0] == "lasso" and ev[1] == "heavy" and ev[2] == Haul.level_for(64) for ev in events)
    assert game.haul.rock < 0


def test_the_beam_holds_the_rock_at_a_fixed_length_so_it_never_hits_you():
    game = campaign()
    x, y = clear_space(game)
    game.gear.levels["lasso"] = 3
    i = rock(game, x + 75, y, 48)
    events = step(game, lasso=True)
    assert ("lasso", "grab", i, 48) in events and game.haul.rock == i
    want = game.haul.set_length(i)
    assert want == pytest.approx(HAUL["beam"] + 24)
    st = game.stage
    f = st.field
    # Fly around: forward, a hard turn, then back toward the rock.
    for aim, back in ((270.0, False), (0.0, False), (90.0, True)):
        for _ in range(round(1.5 / DT)):
            step(game, controls=Controls(forward=not back, back=back, aim=aim))
            assert towed_gap(game) == pytest.approx(game.haul.length, abs=0.01)
            sx, sy = st.ship.x, st.ship.y
            rx, ry = game.haul.rock_pos(i)
            assert math.hypot(rx - sx, ry - sy) > float(f.r[i]) + st.ship.radius
    assert game.haul.rock == i and game.haul.length == pytest.approx(want)    # eased in to its set length


def test_a_rock_keeps_its_momentum_when_you_let_go():
    game = campaign()
    x, y = clear_space(game)
    game.gear.levels["lasso"] = 3
    i = rock(game, x + 75, y, 32)
    step(game, lasso=True)
    step(game, 2.0, Controls(forward=True, aim=270.0))
    f = game.stage.field
    v = (float(f.vx[i]), float(f.vy[i]))
    assert math.hypot(*v) > 150
    events = step(game, lasso=True)
    assert any(ev[0] == "lasso" and ev[1] == "let_go" for ev in events) and game.haul.rock < 0
    assert (float(f.vx[i]), float(f.vy[i])) == pytest.approx(v, rel=0.05)
    assert i in game.haul.flying


def test_heavier_tows_speed_up_more_slowly_and_tow_weight_scales_it():
    def speed_after(size, weight):
        game = campaign(tow_weight=weight)
        x, y = clear_space(game)
        game.gear.levels["lasso"] = 3
        rock(game, x + 50 + size / 2, y, size)
        step(game, lasso=True)
        step(game, 0.4)            # let the grip close
        step(game, 1.0, Controls(forward=True, aim=270.0))
        st = game.stage
        return math.hypot(st.ship.vx, st.ship.vy)

    free = speed_after(10, 0.25)
    assert speed_after(96, 0.25) < speed_after(48, 0.25) < free
    assert speed_after(96, 0.1) > speed_after(96, 0.5)


def throw_at(game: Campaign, kind: str, speed: float, size: int = 48):
    """Send a rock you just let go of at `speed` into an enemy sitting in its path."""
    x, y = clear_space(game)
    game.gear.levels["lasso"] = 3
    st = game.stage
    f = st.field
    i = rock(game, x + 300, y + 200, size)
    f.vx[i], f.vy[i] = speed, 0.0
    game.haul.flying.add(i)
    e = game.battle.add(kind, x + 300 + 70, y + 200, warp=False) if kind != "mothership" else game.mothership
    if kind == "mothership":
        e.x, e.y = x + 300 + 120, y + 200
    hp = e.health
    events = step(game, 1.0)
    return events, e, hp, i


def test_a_fast_thrown_rock_hurts_the_enemy_it_hits_and_slows_down():
    game = campaign()
    events, e, hp, i = throw_at(game, "guard", 300.0)
    hits = [ev for ev in events if ev[0] == "rock_hit"]
    assert hits and hits[0][1] == "guard"
    m = float(game.stage.field.m[i])
    low = HAUL["throw_min_speed"]
    assert hits[0][2] == pytest.approx(HAUL["throw_damage"] * m * (300 - low), rel=0.2)
    assert e.health < hp
    assert math.hypot(float(game.stage.field.vx[i]), float(game.stage.field.vy[i])) < 300 * (1 - HAUL["hit_slow"]) + 40


def test_a_kill_with_a_thrown_rock_pays_credits():
    game = campaign()
    events, e, hp, i = throw_at(game, "infantry", 320.0)
    assert any(ev[0] == "kill" and ev[2] == "rock" for ev in events) and not e.alive
    assert any(ev[0] == "bounty" and ev[1] == "infantry" for ev in events)


def test_a_slow_rock_only_bumps():
    game = campaign()
    events, e, hp, i = throw_at(game, "guard", HAUL["throw_min_speed"] * 0.8)
    assert not any(ev[0] == "rock_hit" for ev in events) and e.health == hp


def test_throw_power_zero_makes_thrown_rocks_harmless():
    game = campaign(throw_power=0.0)
    events, e, hp, i = throw_at(game, "guard", 300.0)
    assert e.health == hp


def test_the_mothership_takes_no_more_than_the_cap():
    game = campaign()
    game.mothership.immune = False
    events, e, hp, i = throw_at(game, "mothership", 400.0, size=96)
    hits = [ev for ev in events if ev[0] == "rock_hit"]
    assert hits and all(ev[2] <= HAUL["mothership_cap"] + 1e-6 for ev in hits)


def test_going_down_lets_go():
    game = campaign()
    x, y = clear_space(game)
    game.gear.levels["lasso"] = 3
    rock(game, x + 75, y, 32)
    step(game, lasso=True)
    st = game.stage
    st.hull = 1
    st.shield = 0
    st.damage_player(50, st.ship.x, st.ship.y)
    step(game, 0.2)
    assert st.ship_down and game.haul.rock < 0


# ------------------------------------------------------------ the collector ring


def place_ring(game: Campaign):
    game.haul.rings_carried = 1
    step(game, 0.1, ring_key=True)
    events = step(game, ring_key=False)
    return game.haul.ring, events


def test_the_ring_costs_4000_and_you_have_one_at_a_time():
    game = campaign(10_000)
    assert RING["price"] == 4000
    assert game.shop.buy("ring") and game.haul.rings_carried == 1 and game.credits == 6000
    assert game.shop.offer("ring").blocked == "OWNED" and not game.shop.buy("ring")


def test_hold_t_to_see_where_it_goes_and_let_go_to_place_it():
    game = campaign()
    x, y = clear_space(game)
    game.haul.rings_carried = 1
    step(game, 0.2, ring_key=True)
    assert game.haul.placing and game.haul.room == "" and game.haul.ring is None
    events = step(game, ring_key=False)
    ring = game.haul.ring
    assert ring is not None and ("ring_set", ring.uid) in events and game.haul.rings_carried == 0
    assert (ring.x, ring.y) == pytest.approx((game.stage.ship.x, game.stage.ship.y), abs=1)
    assert ring in game.stage.structures and ring.radius == RING_RADIUS


def test_no_room_for_the_ring_across_an_asteroid_or_by_home_base():
    game = campaign()
    x, y = clear_space(game)
    rock(game, x + RING_RADIUS, y, 32)
    ring, events = place_ring(game)
    assert ring is None and ("no_room", "ring", "ROCK") in events and game.haul.rings_carried == 1
    game2 = campaign()
    st = game2.stage
    st.ship.x, st.ship.y = game2.base.x + 100, game2.base.y
    assert game2.haul.ring_room(st.ship.x, st.ship.y) == "BASE"


def test_the_ring_catches_rocks_that_drift_in_and_holds_them_in_four_spots():
    game = campaign()
    x, y = clear_space(game)
    ring, _ = place_ring(game)
    st = game.stage
    f = st.field
    st.ship.x -= 400          # out of the way
    rocks = [rock(game, ring.x + 40 * math.cos(a), ring.y + 40 * math.sin(a), 48) for a in (0.3, 1.9, 3.5, 5.0)]
    extra = rock(game, ring.x - 300, ring.y, 48)
    f.vx[extra] = 120.0       # a fifth drifts in once all four spots are taken
    events = step(game, 4.0)
    caught = [ev[1] for ev in events if ev[0] == "ring_caught"]
    assert sorted(caught) == sorted(rocks) and extra not in ring.slots and ring.held == 4
    for k, i in enumerate(ring.slots):
        sx, sy = ring.slot_point(k)
        rx, ry = st.ship.x + wrap_delta(float(f.x[i]) - st.ship.x, f.width), st.ship.y + wrap_delta(float(f.y[i]) - st.ship.y, f.height)
        assert dist(rx, ry, sx, sy) < 2.0 and f.vx[i] == 0 and f.vy[i] == 0


def test_letting_go_of_a_towed_rock_inside_puts_it_in_the_ring_and_q_can_pull_it_out():
    game = campaign()
    x, y = clear_space(game)
    ring, _ = place_ring(game)
    game.gear.levels["lasso"] = 3
    st = game.stage
    i = rock(game, ring.x + 60, ring.y, 32)
    step(game, lasso=True)
    step(game, 0.5)
    assert i not in ring.slots                   # not while it's on the beam
    events = step(game, lasso=True)
    events += step(game, 0.1)
    assert ("ring_caught", i, 32) in events and i in ring.slots
    st.ship.x, st.ship.y = ring.x + 60 - 40, ring.y
    step(game, lasso=True)
    assert game.haul.rock == i and i not in ring.slots


def test_drills_in_the_ring_sell_their_ore_when_full():
    game = campaign()
    x, y = clear_space(game)
    ring, _ = place_ring(game)
    st = game.stage
    i = rock(game, ring.x + 50, ring.y + 50, 64)
    step(game, 3.0)
    assert i in ring.slots
    k = ring.slots.index(i)
    sx, sy = ring.slot_point(k)
    st.ship.x, st.ship.y = sx - 32 - 20, sy
    game.drills_carried = 1
    step(game, set_drill=True)
    d = game.drills[0]
    st.ship.x, st.ship.y = ring.x - 400, ring.y       # well away: you don't pick anything up
    credits = game.credits
    events = step(game, DRILLS["hold"] / DRILLS["dig_rate"] + HAUL["pulse_time"] + 0.5)
    sales = [ev for ev in events if ev[0] == "ring_sale"]
    assert sales and sales[0][1] == pytest.approx(DRILLS["hold"] * DRILLS["credit_per_ore"], abs=1)
    assert game.credits - credits >= sales[0][1] and d.hold < DRILLS["hold"]
    assert any(v > 0 for v in ring.lit) or len(sales) >= 1


def test_enemy_shots_hit_the_rings_band_not_its_open_middle():
    game = campaign()
    x, y = clear_space(game)
    ring, _ = place_ring(game)
    st = game.stage
    st.ship.x -= 600
    st.recentre()
    shot = Shot("enemy", "infantry", ring.x + 200, ring.y, -300.0, 0.0, 6.0, 2.0)
    st.shots.append(shot)
    step(game, 0.4)
    assert ring.health == pytest.approx(ring.max_health - 6.0)
    # A shot that starts inside and stays inside hits nothing.
    st.shots.append(Shot("enemy", "infantry", ring.x - 20, ring.y, 0.0, 100.0, 6.0, 0.5))
    step(game, 0.4)
    assert ring.health == pytest.approx(ring.max_health - 6.0)


def test_enemies_remember_the_ring_and_raid_its_band():
    game = campaign()
    x, y = clear_space(game)
    ring, _ = place_ring(game)
    st = game.stage
    st.ship.x += 3000
    st.recentre()
    game.battle.add("infantry", ring.x + 400, ring.y, warp=False)
    step(game, 0.2)
    assert ring.uid in game.hunt.drills
    ax, ay = game.hunt.aim_point(ring, ring.x + 400, ring.y)
    assert dist(ax, ay, ring.x, ring.y) == pytest.approx(RING_RADIUS)


def test_the_ring_row_repairs_a_damaged_ring():
    game = campaign(100_000)
    x, y = clear_space(game)
    ring, _ = place_ring(game)
    assert game.shop.offer("ring").blocked == "OWNED"
    ring.health = ring.max_health * 0.3
    o = game.shop.offer("ring")
    assert o.price == RING["repair_price"] and not o.blocked
    game.shop.buy("ring")
    assert ring.health == pytest.approx(ring.max_health * (0.3 + RING["repair_restores"]))


# ------------------------------------------------------------ sentries on the ring


def test_r_inside_the_ring_mounts_sentries_top_right_bottom_left_then_places_them_normally():
    game = campaign()
    x, y = clear_space(game)
    ring, _ = place_ring(game)
    st = game.stage
    game.defenses.carried = [("auto", 1), ("sniper", 2), ("missile", 1), ("auto", 3), ("auto", 1)]
    st.ship.x, st.ship.y = ring.x + 20, ring.y - 30
    for k in range(4):
        events = step(game, place_sentry=True)
        s = ring.mounts[k]
        assert s is not None and s.host is ring and ("sentry_set", s.gun, s.tier, s.uid, "ring") in events
        dx, dy = MOUNT_DIRS[k]
        assert (s.x, s.y) == pytest.approx((ring.x + dx * MOUNT_R, ring.y + dy * MOUNT_R))
    assert MOUNT_DIRS[0] == pytest.approx((0, 1)) and MOUNT_DIRS[1] == pytest.approx((1, 0))
    # All four mounts full: R places the next sentry the usual way (here, in the open middle).
    st.ship.x, st.ship.y = ring.x, ring.y
    events = step(game, place_sentry=True)
    free = [s for s in game.defenses.sentries if s.host is None]
    assert len(free) == 1 and dist(free[0].x, free[0].y, ring.x, ring.y) < 1


def test_r_outside_the_ring_places_a_sentry_as_before():
    game = campaign()
    x, y = clear_space(game)
    ring, _ = place_ring(game)
    st = game.stage
    game.defenses.carried = [("auto", 1)]
    st.ship.x = ring.x + 400
    step(game, place_sentry=True)
    s = game.defenses.sentries[0]
    assert s.host is None and all(m is None for m in ring.mounts)


def test_hits_on_a_mounted_sentry_hurt_the_ring_and_it_breaks_with_the_ring():
    game = campaign()
    x, y = clear_space(game)
    ring, _ = place_ring(game)
    st = game.stage
    game.defenses.carried = [("auto", 1), ("sniper", 1)]
    st.ship.x, st.ship.y = ring.x, ring.y
    step(game, place_sentry=True)
    step(game, place_sentry=True)
    a, b = ring.mounts[0], ring.mounts[1]
    held = rock(game, ring.x + 30, ring.y + 30, 48)
    step(game, 2.0)
    st.damage_structure(a, 500, a.x, a.y)
    assert a.alive and ring.health == pytest.approx(ring.max_health - 500)
    st.damage_structure(ring, ring.max_health, ring.x, ring.y)
    assert not ring.alive
    step(game)
    assert not a.alive and not b.alive and not game.defenses.sentries and game.haul.ring is None
    assert a not in st.structures and not st.field.gone[held]           # the rocks stay
    assert game.shop.offer("ring").price == RING["price"]                # you can buy another


# ------------------------------------------------------------ drills float free


def worked_out_rock_with_drills(game: Campaign, n: int = 2):
    x, y = clear_space(game)
    st = game.stage
    i = rock(game, x + 100, y, 48)
    game.drills_carried = n
    f = st.field
    for k in range(n):
        a = math.radians(90 + 180 * k)
        st.ship.x = float(f.x[i]) - math.sin(a) * (float(f.r[i]) + 20)
        st.ship.y = float(f.y[i]) - math.cos(a) * (float(f.r[i]) + 20)
        step(game, set_drill=True)
    st.ship.x, st.ship.y = x - 300, y
    game.rocks[i].left = 0.0
    for d in game.drills:
        d.hold = 0.0
    return i


def test_when_a_rock_crumbles_its_drills_float_free_instead_of_being_used_up():
    game = campaign()
    i = worked_out_rock_with_drills(game, 2)
    events = step(game, 0.5)
    st = game.stage
    assert ("crumble", i, 48) in [ev[:3] for ev in events] and st.field.gone[i]
    assert len([ev for ev in events if ev[0] == "drill_loose"]) == 2
    assert not game.drills and len(st.loose) == 2
    assert game.shop.drills_owned() == 2          # they still count toward how many you can own
    # They drift apart, slowing down.
    a, b = st.loose
    assert dist(a.x, a.y, b.x, b.y) > 40
    step(game, 10.0)
    assert math.hypot(a.vx, a.vy) < 0.5 * DRILLS["float_speed"]


def test_fly_over_a_loose_drill_to_pick_it_up():
    game = campaign()
    worked_out_rock_with_drills(game, 1)
    step(game, 0.5)
    st = game.stage
    ld = st.loose[0]
    assert game.drills_carried == 0
    st.ship.x, st.ship.y = ld.x + DRILLS["float_pickup"] - 2, ld.y
    events = step(game)
    assert ("drill_back", ld.uid) in events and game.drills_carried == 1 and not st.loose


def test_loose_drills_get_an_arrow_at_the_screen_edge():
    game = campaign()
    worked_out_rock_with_drills(game, 1)
    step(game, 0.5)
    st = game.stage
    ld = st.loose[0]
    marks = game.marks((ld.x + 1000, ld.y), (320, 180))
    assert any(kind == "loose" for _, _, kind, _ in marks)


def test_a_towed_rock_that_crumbles_lets_go():
    game = campaign()
    i = worked_out_rock_with_drills(game, 1)
    game.rocks[i].left = 1.0
    game.gear.levels["lasso"] = 3
    st = game.stage
    f = st.field
    st.ship.x, st.ship.y = float(f.x[i]) - 75, float(f.y[i]) + 20
    step(game, lasso=True)
    assert game.haul.rock == i
    st.ship.x -= 0
    game.rocks[i].left = 0.0
    step(game, 0.5)
    assert f.gone[i] and game.haul.rock < 0 and len(st.loose) == 1


# ------------------------------------------------------------ the numbers


def test_hauling_numbers_live_in_the_data_files_and_the_tuning_menu():
    for key in HAUL:
        assert key == "about" or f"`{key}`" in HAUL["about"]
    for key in ("float_speed", "float_damper", "float_pickup"):
        assert f"`{key}`" in DRILLS["about"]
    for key in ("max_size", "repair_price", "repair_restores"):
        assert f"`{key}`" in SHOP["about"]
    t = Tuning()
    assert 0 < t.tow_weight <= 1 and t.throw_power > 0
    assert FIELD_R < INNER < RING_RADIUS < INNER + 2 * RING_HOOP
