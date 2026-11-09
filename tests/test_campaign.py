"""Secure the Base: the big map, drills, the mothership's waves and enemies that have to find you."""

import json
import math

import pytest

from bitminer import sector
from bitminer.combat.ai import Battle
from bitminer.combat.campaign import Campaign, autopilot
from bitminer.combat.hunt import Fleet, Hunt, Task
from bitminer.combat.specs import DRILLS, FLEET, HUNT
from bitminer.combat.stage import Stage, Structure, dist
from bitminer.field import AsteroidField, collision_radius, wrap_delta
from bitminer.flight import Controls
from bitminer.settings import Tuning

W, H = 12000.0, 8000.0
DT = 1 / 60
SMALL = 3              # map scale for whole-game tests: quick to build


class Quiet:
    def burst(self, *a, **k):
        pass

    def emit(self, *a, **k):
        pass


def hunt_stage(ship=(2000.0, 2000.0), home=(9000.0, 6000.0), spec=None):
    """An empty wrapping stage with a Battle, a Hunt and a mothership at `home`."""
    st = Stage(Quiet(), Quiet())
    st.ship.x, st.ship.y = ship
    st.ship.ux, st.ship.uy = ship
    st.field = AsteroidField(W, H)
    st.world = (W, H)
    battle = Battle(st, seed=3)
    ms = st.spawn("mothership", *home, warp=False)
    ms.immune = True
    battle.hunt = Hunt(battle, ship, ms, spec=spec)
    return st, battle, ms


def tick(st: Stage, battle: Battle, seconds: float, fleet: Fleet | None = None) -> list:
    events = []
    for _ in range(round(seconds / DT)):
        st.recentre()
        if fleet is not None:
            fleet.step(DT)
        battle.step(DT)
        st.step(DT)
        events += st.events
        st.events = []
    return events


def campaign(**kw) -> Campaign:
    return Campaign(Quiet(), Quiet(), Tuning(), scale=kw.pop("scale", SMALL), **kw)


def idle(game: Campaign, seconds: float, set_drill=False) -> list:
    events = []
    for i in range(round(seconds / DT)):
        events += game.step(DT, Controls(), False, None, set_drill=set_drill and i == 0)
    return events


# ------------------------------------------------------------ the map


def test_the_map_scales_and_keeps_base_and_mothership_far_apart():
    small, big = sector.layout(scale=4), sector.layout(scale=10)
    assert big.width == pytest.approx(small.width * 2.5)
    for lay in (small, big):
        dx = wrap_delta(lay.mothership[0] - lay.base[0], lay.width)
        dy = wrap_delta(lay.mothership[1] - lay.base[1], lay.height)
        assert math.hypot(dx, dy) > 0.4 * math.hypot(lay.width, lay.height)


def test_the_same_seed_builds_the_same_field():
    lay = sector.layout(scale=SMALL)
    a, b = sector.build_field(lay, seed=4), sector.build_field(lay, seed=4)
    c = sector.build_field(lay, seed=5)
    assert len(a) == len(b) and (a.x == b.x).all() and (a.size == b.size).all()
    assert len(c) != len(a) or not (c.x == a.x).all()


def test_home_base_the_mothership_and_the_start_are_kept_clear():
    lay = sector.layout(scale=SMALL)
    f = sector.build_field(lay)
    spec = sector.MAP
    for (px, py), clear in ((lay.base, spec["home_base"]["clear"]), (lay.mothership, spec["mothership"]["clear"]),
                            (lay.spawn, spec["spawn_clear"])):
        for x, y, size in zip(f.x, f.y, f.size):
            d = math.hypot(wrap_delta(x - px, f.width), wrap_delta(y - py, f.height))
            assert d >= clear + collision_radius(int(size)) - 1e-6


def test_rocks_never_start_overlapping():
    f = sector.build_field(sector.layout(scale=SMALL))
    for i in range(0, len(f), 7):
        idx, dx, dy = f.near(float(f.x[i]), float(f.y[i]), 200, 200)
        for j, a, b in zip(idx.tolist(), dx, dy):
            if j != i:
                assert math.hypot(a, b) >= f.r[i] + f.r[j]


def test_the_map_size_slider_sets_how_big_a_new_game_is():
    t = Tuning()
    t.map_size = 4
    game = Campaign(Quiet(), Quiet(), t, scale=t.map_size)
    assert game.world.width == pytest.approx(sector.layout(scale=4).width)


# ------------------------------------------------------------ what they know


def test_one_enemy_seeing_you_tells_them_all_and_they_lose_you_after_a_while():
    st, battle, ms = hunt_stage()
    hunt = battle.hunt
    far = battle.add_group("infantry", 3, 7000, 5000, warp=False)
    assert not hunt.known
    near = battle.add("infantry", st.ship.x + HUNT["sight"] - 60, st.ship.y, warp=False)
    events = tick(st, battle, 0.1)
    assert hunt.known and ("spotted",) in events
    assert all(battle.knows for _ in far)
    # You get away: nobody sees you any more.
    near.alive = False
    st.ship.x += 4000
    st.ship.ux += 4000
    rev = hunt.rev
    events = tick(st, battle, HUNT["lose_after"] - 0.5)
    assert hunt.known
    events = tick(st, battle, 1.0)
    assert not hunt.known and ("lost",) in events and hunt.rev == rev + 1
    assert hunt.last_seen[0] == pytest.approx(st.ship.x - 4000, abs=50)


def test_hitting_one_of_them_gives_you_away():
    st, battle, ms = hunt_stage()
    battle.hunt.reveal()
    tick(st, battle, DT)
    assert battle.hunt.known


def test_a_task_goes_to_where_you_were_seen_searches_then_goes_home():
    spec = dict(HUNT, search_time=3.0)
    st, battle, ms = hunt_stage(spec=spec)
    hunt = battle.hunt
    hunt.last_seen = (5000.0, 4000.0)
    task = Task(battle)
    x, y, kind = task.tick(DT, 3000.0, 3000.0)
    assert kind == "travel" and (x, y) == pytest.approx((5000.0, 4000.0))
    x, y, kind = task.tick(DT, 5000.0, 4000.0 + spec["arrive"] - 1)
    assert kind == "search"
    assert dist(x, y, 5000.0, 4000.0) <= spec["search_radius"] + 1
    for _ in range(round(3.1 / DT)):
        x, y, kind = task.tick(DT, 5000.0, 4000.0)
    assert kind == "home" and (x, y) == pytest.approx((ms.x, ms.y))
    # Losing you again starts a fresh search.
    hunt.rev += 1
    assert task.tick(DT, 5000.0, 4000.0)[2] == "search"


def test_they_remember_a_drill_they_fly_past_and_raid_it():
    st, battle, ms = hunt_stage()
    mine = Structure("drill", 6000.0, 4000.0, radius=8.0, health=900.0, max_health=900.0, uid=st.uid())
    st.structures.append(mine)
    sq_ships = battle.add_group("infantry", 3, 6000.0 + HUNT["sight"] - 100, 4000.0, warp=False)
    events = tick(st, battle, 0.2)
    assert ("drill_found", mine.uid) in events
    task = Task(battle)
    assert task.tick(DT, 6200.0, 4000.0)[2] == "raid"
    # Left alone, they shoot it to bits.
    events = tick(st, battle, 60.0)
    assert any(ev[0] == "struct_hit" and ev[2] == mine.uid for ev in events)
    assert all(e.alive for e in sq_ships)
    hits = sum(ev[3] for ev in events if ev[0] == "struct_hit" and ev[2] == mine.uid)
    assert hits > 100


def test_ships_that_give_up_go_back_into_the_mothership():
    spec = dict(HUNT, search_time=0.5)
    st, battle, ms = hunt_stage(home=(3000.0, 2000.0), spec=spec)
    battle.hunt.last_seen = (3000.0, 2600.0)
    battle.add_group("infantry", 2, 3000.0, 2700.0, warp=False)
    events = tick(st, battle, 30.0)
    assert sum(1 for ev in events if ev[0] == "docked") == 2


def test_squads_march_fast_a_long_way_then_slow_to_search():
    st, battle, ms = hunt_stage()
    battle.hunt.last_seen = (7000.0, 2000.0)
    ships = battle.add_group("infantry", 3, 2600.0, 2000.0, warp=False)
    tick(st, battle, 3.0)
    speed = max(math.hypot(e.mx, e.my) for e in ships)
    assert speed > HUNT["cruise_speed"] * 0.8


# ------------------------------------------------------------ waves


def test_the_first_wave_comes_on_a_timer_and_the_next_only_when_few_are_left():
    st, battle, ms = hunt_stage(home=(2600.0, 2000.0))
    fleet = Fleet(battle, ms)
    events = tick(st, battle, FLEET["first"] - 0.5, fleet)
    assert fleet.number == 0 and not any(ev[0] == "wave" for ev in events)
    events = tick(st, battle, 1.0, fleet)
    assert fleet.number == 1 and ("wave", 1, FLEET["list"][0]["name"]) in events
    first = [e for e in st.enemies if e.alive and e.kind != "mothership"]
    # A long time later, with all of them still out, there's still only one wave.
    tick(st, battle, 60.0, fleet)
    assert fleet.number == 1
    # Shoot them down to the few the rule allows, and the next comes `gap` seconds later.
    for e in first[: len(first) - fleet.few_left]:
        e.alive = False
    tick(st, battle, FLEET["gap"] - 0.5, fleet)
    assert fleet.number == 1
    tick(st, battle, 1.0, fleet)
    assert fleet.number == 2


def test_a_small_wave_has_to_be_mostly_beaten_before_the_next():
    st, battle, ms = hunt_stage()
    fleet = Fleet(battle, ms)
    fleet.last_size = 3
    assert fleet.few_left == min(int(FLEET["few_left"]), int(3 * FLEET["few_left_share"]))
    fleet.last_size = 40
    assert fleet.few_left == int(FLEET["few_left"])


def test_waves_leave_from_the_mothership_toward_where_they_think_you_are():
    st, battle, ms = hunt_stage(ship=(2000.0, 2000.0), home=(6000.0, 2000.0))
    fleet = Fleet(battle, ms)
    fleet.call_now()
    fleet.step(DT)
    ships = [e for e in st.enemies if e.kind != "mothership"]
    assert ships and all(dist(e.x, e.y, ms.x, ms.y) < 260 for e in ships)
    assert sum(e.x for e in ships) / len(ships) < ms.x       # on the side facing you


def test_the_mothership_and_home_base_cannot_be_destroyed_yet():
    game = campaign()
    st = game.stage
    st.damage_enemy(game.mothership, 1e9, game.mothership.x, game.mothership.y)
    st.damage_structure(game.base, 1e9, game.base.x, game.base.y)
    assert game.mothership.alive and game.mothership.dying < 0 and game.base.alive


# ------------------------------------------------------------ drills


def put_ship_by_ore_rock(game: Campaign, size: int = 64) -> int:
    """Move your ship next to a fresh ore asteroid of this size; returns its index."""
    st = game.stage
    f = st.field
    f.add(st.ship.x + 300, st.ship.y, size, 0, True)
    i = len(f) - 1
    st.ship.x = float(f.x[i]) - f.r[i] - 20
    st.ship.ux = st.ship.x
    st.ship.vx = st.ship.vy = 0.0
    return i


def move_ship_round(game: Campaign, rock: int, heading: float, gap: float = 20.0) -> None:
    """Park your ship off asteroid `rock` on the side `heading` points to."""
    st = game.stage
    f = st.field
    a = math.radians(heading)
    r = float(f.r[rock]) + gap
    st.ship.x = float(f.x[rock]) + math.sin(a) * r
    st.ship.y = float(f.y[rock]) + math.cos(a) * r
    st.ship.vx = st.ship.vy = 0.0


def test_you_start_with_one_drill_the_auto_cannon_and_no_shield():
    game = campaign()
    st = game.stage
    assert game.drills_carried == 1 and game.arsenal.owned == ["auto"]
    assert st.shield == 0 and st.shield_max == 0 and st.missiles_total == 0 and game.credits == 0


def test_a_drill_goes_only_on_an_ore_asteroid_big_enough_and_near_enough():
    game = campaign()
    st = game.stage
    f = st.field
    f.add(st.ship.x + 500, st.ship.y + 500, 64, 0, False)
    plain = len(f) - 1
    st.ship.x, st.ship.y = float(f.x[plain]) - f.r[plain] - 20, float(f.y[plain])
    assert game.drill_spot() != plain
    i = put_ship_by_ore_rock(game, 64)
    assert game.drill_spot() == i
    st.ship.x -= DRILLS["reach"] + 40
    assert game.drill_spot() is None


def test_setting_a_drill_digging_loading_and_selling():
    game = campaign()
    i = put_ship_by_ore_rock(game, 64)
    events = idle(game, DT, set_drill=True)
    assert any(ev[0] == "drill_set" for ev in events)
    d = game.drills[0]
    assert game.drills_carried == 0
    assert game.rocks[i].total == pytest.approx(DRILLS["ore_per_area"] * 64 ** 2)
    # It stands on the edge of its asteroid's picture, on your side.
    f = game.stage.field
    gap = dist(d.x, d.y, float(f.x[i]), float(f.y[i]))
    assert 64 * 0.37 + 4 < gap < 64 / 2 + 7
    assert d.x < float(f.x[i])
    # Keep the ship clear while it digs, then fly over.
    st = game.stage
    st.ship.x -= 200
    idle(game, 5.0)
    assert d.hold == pytest.approx(DRILLS["dig_rate"] * 5.0, abs=0.2)
    st.ship.x, st.ship.y = d.x, d.y
    idle(game, DT)
    assert game.cargo == pytest.approx(DRILLS["dig_rate"] * 5.0, abs=0.3) and d.hold < 0.1
    st.ship.x, st.ship.y = game.base.x, game.base.y - 60
    events = idle(game, DT)
    assert any(ev[0] == "unload" for ev in events) and game.cargo == 0 and game.credits >= 9


def test_you_need_a_drill_to_set_one():
    game = campaign()
    put_ship_by_ore_rock(game, 64)
    game.drills_carried = 0
    assert game.drillable() is not None and game.drill_spot() is None
    idle(game, DT, set_drill=True)
    assert not game.drills


def test_a_drill_stops_digging_when_its_hold_is_full():
    game = campaign()
    i = put_ship_by_ore_rock(game, 96)
    idle(game, DT, set_drill=True)
    game.stage.ship.x -= 300
    idle(game, DRILLS["hold"] / DRILLS["dig_rate"] + 5)
    d = game.drills[0]
    assert d.hold == pytest.approx(DRILLS["hold"]) and not d.working
    pool = game.rocks[i]
    assert pool.left == pytest.approx(pool.total - DRILLS["hold"], abs=0.1)


def test_several_drills_share_an_asteroid_but_not_the_same_spot():
    game = campaign()
    game.drills_carried = 3
    i = put_ship_by_ore_rock(game, 96)
    move_ship_round(game, i, 270)
    idle(game, DT, set_drill=True)
    move_ship_round(game, i, 275)           # right next to the first: no room
    assert game.drill_spot() is None
    move_ship_round(game, i, 0)
    idle(game, DT, set_drill=True)
    assert len(game.drills) == 2 and {d.rock for d in game.drills} == {i}
    # Both dig from the same ore, so it empties twice as fast.
    game.stage.ship.x += 400
    idle(game, 4.0)
    pool = game.rocks[i]
    assert pool.total - pool.left == pytest.approx(2 * DRILLS["dig_rate"] * 4.0, abs=0.5)


def test_an_asteroid_cracks_in_stages_as_it_empties():
    game = campaign()
    i = put_ship_by_ore_rock(game, 96)
    idle(game, DT, set_drill=True)
    f = game.stage.field
    pool = game.rocks[i]
    stages = []
    for drained in (0.1, 0.3, 0.6, 0.9):
        pool.left = pool.total * (1 - drained)
        events = idle(game, DT)
        stages.append(int(f.wear[i]))
    assert stages == [0, 1, 2, 3]
    assert ("crack", i, 3) in events


def test_a_worked_out_asteroid_crumbles_once_unloaded_and_its_drills_float_free():
    game = campaign()
    game.drills_carried = 2
    i = put_ship_by_ore_rock(game, 48)
    move_ship_round(game, i, 270)
    idle(game, DT, set_drill=True)
    move_ship_round(game, i, 90)
    idle(game, DT, set_drill=True)
    a, b = game.drills
    st = game.stage
    f = st.field
    st.ship.x += 300
    game.rocks[i].left = 0.0
    a.hold, b.hold = 10.0, 0.0
    events = idle(game, 0.5)
    assert not f.gone[i] and a.alive               # it waits until you pick up the last ore
    st.ship.x, st.ship.y = a.x, a.y
    events = idle(game, 0.2)
    assert any(ev[0] == "crumble" and ev[1] == i for ev in events)
    assert f.gone[i] and not game.drills and not a.alive and not b.alive and i not in game.rocks
    # Not used up: they float free (the one under your ship goes straight back in your hold).
    assert len(st.loose) + game.drills_carried == 2 and game.shop.drills_owned() == 2
    assert any(an.name == "crumble" for an in st.anims)
    # Nothing can find it any more: no lookups, no collisions, no new drill.
    idx, _, _ = f.near(float(f.x[i]), float(f.y[i]), 10, 10)
    assert i not in idx.tolist()
    assert game.drillable() is None or game.drillable()[0] != i


def test_enemy_fire_wears_a_drill_down_until_it_is_lost():
    game = campaign()
    put_ship_by_ore_rock(game, 64)
    idle(game, DT, set_drill=True)
    d = game.drills[0]
    st = game.stage
    st.damage_structure(d, DRILLS["health"] - 1, d.x, d.y)
    assert d.alive and d.health == pytest.approx(1)
    st.events = []
    st.damage_structure(d, 50, d.x, d.y)
    assert ("struct_lost", "drill", d.uid) in st.events
    idle(game, DT)
    assert not game.drills


# ------------------------------------------------------------ the station


def test_e_opens_the_station_only_when_you_are_at_it():
    game = campaign()
    st = game.stage
    st.ship.x, st.ship.y = game.base.x, game.base.y - 300
    assert not game.open_station() and not game.station_open
    st.ship.x, st.ship.y = game.base.x, game.base.y - 60
    assert game.near_station() and game.open_station() and game.station_open
    events = idle(game, DT)
    assert ("station", "open") in events


def test_the_ship_holds_still_and_cannot_fire_while_docked():
    game = campaign()
    st = game.stage
    st.ship.x, st.ship.y = game.base.x, game.base.y - 60
    st.ship.vx = 40.0
    game.open_station()
    for _ in range(120):
        events = game.step(DT, Controls(forward=True), True, None)
        assert not any(ev[0] == "fire" for ev in events)
    assert abs(st.ship.vx) < 1.0 and abs(st.ship.vy) < 1.0
    assert game.station_open             # the game kept running, and you're still docked


def test_the_station_closes_when_you_go_down():
    game = campaign()
    st = game.stage
    st.ship.x, st.ship.y = game.base.x, game.base.y - 60
    game.open_station()
    st.damage_player(1e6, st.ship.x + 5, st.ship.y, source="test")
    idle(game, DT)
    assert not game.station_open


def test_the_station_warns_you_when_enemies_are_near():
    game = campaign()
    st = game.stage
    assert not game.enemy_near()
    st.spawn("infantry", st.ship.x + 200, st.ship.y, warp=False)
    assert game.enemy_near()


def test_going_down_loses_your_cargo_and_brings_you_back_at_base():
    game = campaign()
    game.cargo = 50
    st = game.stage
    st.ship.x += 2000
    st.ship.ux += 2000
    st.shield = 0.0
    st.damage_player(1e6, st.ship.x + 5, st.ship.y, source="test")
    idle(game, DT)
    assert st.ship_down and game.cargo == 0 and game.downs == 1
    events = idle(game, 4.0)
    assert ("respawn",) in events and not st.ship_down
    assert dist(st.ship.x, st.ship.y, game.base.x, game.base.y) < 200


# ------------------------------------------------------------ the HUD's view of it


def test_arrows_point_at_your_base_and_drills_when_they_are_off_screen():
    game = campaign()
    st = game.stage
    centre = (st.ship.x, st.ship.y)
    on = game.marks(centre, (400, 300))
    assert all(kind != "base" for *_, kind, _ in on)
    st.ship.x += 3000
    st.ship.ux += 3000
    st.recentre()
    marks = game.marks((st.ship.x, st.ship.y), (400, 300))
    assert [m[2] for m in marks] == ["base"]
    assert marks[0][0] < -2000


# ------------------------------------------------------------ a whole game on auto pilot


def test_five_minutes_on_auto_pilot():
    game = campaign()
    events = []
    clock = 0.0
    for _ in range(round(300 / DT)):
        controls, trigger, cursor, set_drill = autopilot(game, clock)
        events += game.step(DT, controls, trigger, cursor, set_drill)
        clock += DT
    kinds = {ev[0] for ev in events}
    assert {"drill_set", "load", "unload", "wave", "station", "bought"} <= kinds
    assert sum(1 for ev in events if ev[0] == "bought" and ev[1] == "drill") >= 1
    assert game.fleet.number >= 1


def test_campaign_numbers_are_all_in_the_data_files():
    data = json.loads((sector.MAP_FILE.parent / "combat.json").read_text())
    for block in ("hunt", "fleet", "drills"):
        assert "about" in data[block]
    assert "about" in sector.MAP
