"""Secure the Base: the big map, mines, the mothership's waves and enemies that have to find you."""

import json
import math

import pytest

from bitminer import sector
from bitminer.combat.ai import Battle
from bitminer.combat.campaign import Campaign, autopilot
from bitminer.combat.hunt import Fleet, Hunt, Task
from bitminer.combat.specs import FLEET, HUNT, MINES
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


def idle(game: Campaign, seconds: float, set_mine=False) -> list:
    events = []
    for i in range(round(seconds / DT)):
        events += game.step(DT, Controls(), False, None, set_mine=set_mine and i == 0)
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


def test_they_remember_a_mine_they_fly_past_and_raid_it():
    st, battle, ms = hunt_stage()
    mine = Structure("mine", 6000.0, 4000.0, radius=8.0, health=900.0, max_health=900.0, uid=st.uid())
    st.structures.append(mine)
    sq_ships = battle.add_group("infantry", 3, 6000.0 + HUNT["sight"] - 100, 4000.0, warp=False)
    events = tick(st, battle, 0.2)
    assert ("mine_found", mine.uid) in events
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


# ------------------------------------------------------------ mines


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


def test_a_mine_goes_only_on_an_ore_asteroid_big_enough_and_near_enough():
    game = campaign()
    st = game.stage
    f = st.field
    f.add(st.ship.x + 500, st.ship.y + 500, 64, 0, False)
    plain = len(f) - 1
    st.ship.x, st.ship.y = float(f.x[plain]) - f.r[plain] - 20, float(f.y[plain])
    assert game.mine_spot() != plain
    i = put_ship_by_ore_rock(game, 64)
    assert game.mine_spot() == i
    st.ship.x -= MINES["reach"] + 40
    assert game.mine_spot() is None


def test_setting_a_mine_digging_loading_and_selling():
    game = campaign()
    i = put_ship_by_ore_rock(game, 64)
    events = idle(game, DT, set_mine=True)
    assert any(ev[0] == "mine_set" for ev in events)
    m = game.mines[0]
    assert m.ore_max == pytest.approx(MINES["ore_per_area"] * 64 ** 2)
    # It sits on its asteroid's surface, on your side.
    f = game.stage.field
    assert dist(m.x, m.y, float(f.x[i]), float(f.y[i])) == pytest.approx(f.r[i] + 5, abs=1)
    # Keep the ship clear while it digs, then fly over.
    st = game.stage
    st.ship.x -= 200
    idle(game, 5.0)
    assert m.hold == pytest.approx(MINES["dig_rate"] * 5.0, abs=0.2)
    st.ship.x, st.ship.y = m.x, m.y
    idle(game, DT)
    assert game.cargo == pytest.approx(MINES["dig_rate"] * 5.0, abs=0.3) and m.hold < 0.1
    st.ship.x, st.ship.y = game.base.x, game.base.y - 60
    events = idle(game, DT)
    assert any(ev[0] == "unload" for ev in events) and game.cargo == 0 and game.credits >= 9


def test_a_mine_stops_digging_when_its_hold_is_full():
    game = campaign()
    put_ship_by_ore_rock(game, 96)
    idle(game, DT, set_mine=True)
    game.stage.ship.x -= 300
    idle(game, MINES["hold"] / MINES["dig_rate"] + 5)
    m = game.mines[0]
    assert m.hold == pytest.approx(MINES["hold"])
    assert m.ore_left == pytest.approx(m.ore_max - MINES["hold"], abs=0.1)


def test_a_worked_out_asteroid_loses_its_mine_and_its_ore():
    game = campaign()
    i = put_ship_by_ore_rock(game, 24)
    idle(game, DT, set_mine=True)
    m = game.mines[0]
    m.ore_left = 1.0
    st = game.stage
    st.ship.x, st.ship.y = m.x, m.y
    events = idle(game, 2.0)
    assert ("mine_dry", m.uid) in events and not game.mines and not st.field.ore[i]
    assert m not in st.structures


def test_you_can_run_only_so_many_mines():
    game = campaign()
    for _ in range(int(MINES["max"])):
        put_ship_by_ore_rock(game, 64)
        idle(game, DT, set_mine=True)
    assert len(game.mines) == MINES["max"]
    put_ship_by_ore_rock(game, 64)
    assert game.mine_spot() is None


def test_enemy_fire_wears_a_mine_down_until_it_is_lost():
    game = campaign()
    put_ship_by_ore_rock(game, 64)
    idle(game, DT, set_mine=True)
    m = game.mines[0]
    st = game.stage
    st.damage_structure(m, MINES["health"] - 1, m.x, m.y)
    assert m.alive and m.health == pytest.approx(1)
    st.events = []
    st.damage_structure(m, 50, m.x, m.y)
    assert ("struct_lost", "mine", m.uid) in st.events
    idle(game, DT)
    assert not game.mines


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


def test_arrows_point_at_your_base_and_mines_when_they_are_off_screen():
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
        controls, trigger, cursor, set_mine = autopilot(game, clock)
        events += game.step(DT, controls, trigger, cursor, set_mine)
        clock += DT
    kinds = {ev[0] for ev in events}
    assert {"mine_set", "load", "unload", "wave"} <= kinds
    assert game.credits > 0 and game.fleet.number >= 1


def test_campaign_numbers_are_all_in_the_data_files():
    data = json.loads((sector.MAP_FILE.parent / "combat.json").read_text())
    for block in ("hunt", "fleet", "mines"):
        assert "about" in data[block]
    assert "about" in sector.MAP
