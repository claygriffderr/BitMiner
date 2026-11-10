"""Sprint 12, the pacing guide's sprint B: waves on a shrinking timer, sized by a threat budget,
tanks with escorts, massive waves released in parts, and the work that lets 200 ships fly at once."""

import math

import pytest

from bitminer.combat.ai import TankBrain
from bitminer.combat.hunt import Fleet, share_out
from bitminer.combat.specs import AI, ENEMIES, ENEMY_WEAPONS, FLEET
from bitminer.combat.stage import Structure, dist
from bitminer.settings import Tuning

from .test_campaign import DT, Quiet, campaign, hunt_stage, tick


def fleet_on_a_stage(spec=None, tuning=None, **kw):
    st, battle, ms = hunt_stage(**kw)
    return st, battle, ms, Fleet(battle, ms, spec=spec, tuning=tuning)


def threat(counts: dict) -> float:
    return sum(n * FLEET["threat"][kind] for kind, n in counts.items())


# ------------------------------------------------------------ the timer


def test_the_gap_between_waves_shrinks_to_its_floor():
    *_, fleet = fleet_on_a_stage()
    assert fleet.gap_after(1) == FLEET["gap_start"] == 120
    assert fleet.gap_after(2) == 116
    assert fleet.gap_after(20) == FLEET["gap_min"] == 45
    assert fleet.gap_after(29) == 45
    assert all(fleet.gap_after(n) >= fleet.gap_after(n + 1) for n in range(1, 29))


def test_the_schedule_matches_the_pacing_guide():
    """Wave 6 at 10:20, wave 20 at 27:35, and the first massive wave at 35:05."""
    *_, fleet = fleet_on_a_stage()
    at = {1: float(FLEET["first"])}
    for n in range(1, 50):
        at[n + 1] = at[n] + fleet.gap_after(n)
    assert at[1] == 60
    assert at[6] == 10 * 60 + 20
    assert at[20] == pytest.approx(27 * 60 + 35, abs=2)
    assert at[30] == pytest.approx(35 * 60 + 5, abs=2)
    assert at[31] - at[30] == FLEET["cooloff"] == 150        # the cool-off after a massive wave
    assert at[40] == pytest.approx(44 * 60 + 25, abs=5)


def test_the_wave_gap_slider_stretches_the_timer():
    tuning = Tuning()
    *_, fleet = fleet_on_a_stage(tuning=tuning)
    tuning.wave_gap = 0.5
    assert fleet.gap_after(1) == 60 and fleet.gap_after(30) == 75
    tuning.wave_gap = 2.0
    assert fleet.gap_after(25) == 90


def test_a_wave_waits_while_too_many_enemies_are_out():
    spec = dict(FLEET, cap=6, first=1.0, gap_start=2.0, gap_min=2.0, gap_step=0.0)
    st, battle, ms, fleet = fleet_on_a_stage(spec=spec, home=(2600.0, 2000.0))
    battle.add_group("infantry", 6, 2300.0, 2000.0, warp=False)
    tick(st, battle, 3.0, fleet)
    assert fleet.number == 0 and fleet.held and fleet.next_in is None
    for e in st.enemies[1:4]:
        e.alive = False
    tick(st, battle, 0.5, fleet)
    assert fleet.number == 1 and not fleet.held and fleet.next_in is not None


# ------------------------------------------------------------ size


def test_the_threat_budget_follows_the_curve():
    *_, fleet = fleet_on_a_stage()
    assert fleet.budget(1) == pytest.approx(3.99)
    assert fleet.budget(10) == pytest.approx(21.0)
    assert fleet.budget(29) == pytest.approx(104.79)
    assert fleet.budget(31) == pytest.approx(113.0)          # gentle after the first massive wave
    assert fleet.budget(45) == pytest.approx(155.0)


def test_the_wave_size_slider_scales_every_wave():
    game = campaign()
    plain = game.fleet.counts(10)
    game.tuning.wave_size = 2.0
    assert game.fleet.budget(10) == pytest.approx(42.0)
    assert sum(game.fleet.counts(10).values()) > 1.7 * sum(plain.values())
    assert sum(game.fleet.counts(30).values()) == 400


def test_each_kind_of_ship_waits_for_its_wave():
    *_, fleet = fleet_on_a_stage()
    unlock = FLEET["unlock"]
    for n in range(1, 30):
        counts = fleet.counts(n)
        for kind in ("guard", "rapid", "tank"):
            if n < unlock[kind]:
                assert counts.get(kind, 0) == 0, (n, kind)
    assert fleet.counts(1) == {"infantry": 4, "rapid": 0, "guard": 0, "tank": 0}
    assert fleet.counts(unlock["guard"])["guard"] >= 1
    assert fleet.counts(unlock["rapid"])["rapid"] >= 1


def test_a_wave_spends_about_its_budget():
    *_, fleet = fleet_on_a_stage()
    for n in list(range(1, 30)) + [31, 35, 45]:
        counts = fleet.counts(n)
        if FLEET["recipes"][-1]["name"] == fleet.recipe(n)["name"] and n < 24:
            continue                                        # the first sieges spend more: a tank and its escort
        assert abs(threat(counts) - fleet.budget(n)) <= 5.0, (n, counts)


def test_waves_grow_much_faster_than_the_old_list():
    *_, fleet = fleet_on_a_stage()
    size = {n: sum(fleet.counts(n).values()) for n in (1, 6, 10, 20, 29)}
    assert size[1] == 4 and 7 <= size[6] <= 10 and 12 <= size[10] <= 17
    assert 34 <= size[20] <= 46 and 52 <= size[29] <= 64


def test_recipes_take_turns_and_the_siege_takes_its_own_waves():
    *_, fleet = fleet_on_a_stage()
    plain = [r["name"] for r in FLEET["recipes"] if "from" not in r]
    assert [fleet.recipe(n)["name"] for n in range(1, 7)] == plain
    assert fleet.recipe(7)["name"] == plain[0]
    assert [n for n in range(1, 30) if fleet.recipe(n)["name"] == "SIEGE"] == [12, 18, 24]


def test_tanks_join_at_wave_12_and_never_come_alone():
    *_, fleet = fleet_on_a_stage()
    assert all(fleet.counts(n)["tank"] == 0 for n in range(1, 12))
    first = fleet.counts(12)
    assert first["tank"] == 1 and first["guard"] >= FLEET["escort"]["guard"]
    assert first["infantry"] >= FLEET["escort"]["infantry"]
    assert fleet.counts(25)["tank"] == 1                   # one for every 80 points of budget
    assert fleet.counts(36)["tank"] == 2                   # a late siege
    name, parts = fleet.compose(12)
    bunch = next(b for b in parts[0] if b[0][0] == "tank")
    assert name == "SIEGE" and [kind for kind, _, _ in bunch] == ["tank", "infantry", "guard"]


def test_infantry_fly_in_squads_of_four_to_six():
    *_, fleet = fleet_on_a_stage()
    lo, hi = FLEET["squad"]
    for n in (7, 13, 20, 29, 35):
        _, parts = fleet.compose(n)
        squads = [count for bunch in parts[0] for kind, count, _ in bunch if kind == "infantry"]
        assert squads and all(lo <= s <= hi for s in squads), (n, squads)
        rapids = [count for bunch in parts[0] for kind, count, _ in bunch if kind == "rapid"]
        assert all(r <= FLEET["rapid_group"] for r in rapids)


def test_share_out_spreads_the_odd_ones():
    assert share_out(10, 5) == [2, 2, 2, 2, 2]
    assert share_out(2, 5) == [0, 1, 0, 1, 0]
    assert share_out(1, 5) == [0, 0, 1, 0, 0]
    assert sum(share_out(36, 5)) == 36 and max(share_out(36, 5)) - min(share_out(36, 5)) == 1
    assert share_out(3, 0) == []


# ------------------------------------------------------------ massive waves


def test_every_tenth_wave_from_30_is_massive():
    *_, fleet = fleet_on_a_stage()
    assert [n for n in range(1, 61) if fleet.is_massive(n)] == [30, 40, 50, 60]
    counts = fleet.counts(30)
    assert sum(counts.values()) == 200 and counts == FLEET["massive"]["ships"]
    name, parts = fleet.compose(30)
    assert name == "MASSIVE WAVE" and len(parts) == 5
    sizes = [sum(count for bunch in part for _, count, _ in bunch) for part in parts]
    assert sum(sizes) == 200 and all(38 <= s <= 42 for s in sizes)
    with_tank = [i for i, part in enumerate(parts) if any(b[0][0] == "tank" for b in part)]
    assert len(with_tank) == 2                              # the two tanks leave in different groups


def test_the_massive_wave_warning_counts_down_from_three():
    *_, fleet = fleet_on_a_stage()
    seen = {}
    for launched in range(0, 41):
        fleet.launched = launched
        seen[launched] = fleet.warning
    assert seen[25] is None and seen[26] is None
    assert (seen[27], seen[28], seen[29]) == (3, 2, 1)
    assert seen[30] is None and (seen[37], seen[39]) == (3, 1)
    fleet.launched = 30
    assert fleet.massive_in == 10


def test_skipping_ahead_lands_three_waves_before_the_massive_one():
    *_, fleet = fleet_on_a_stage()
    assert fleet.skip_to_massive() == 30 and fleet.launched == 26
    assert fleet.skip_to_massive() == 30 and fleet.launched == 26      # pressing it again changes nothing
    fleet.launched = 30
    assert fleet.skip_to_massive() == 40 and fleet.launched == 36


def test_a_massive_wave_leaves_in_parts_then_the_fleet_cools_off():
    massive = dict(FLEET["massive"], first=1, groups=5, group_gap=2.0,
                   ships={"infantry": 20, "rapid": 5, "guard": 5, "tank": 2})
    spec = dict(FLEET, massive=massive, first=1.0, cap=10 ** 6)
    st, battle, ms, fleet = fleet_on_a_stage(spec=spec, home=(2600.0, 2000.0))
    events = tick(st, battle, 1.5, fleet)
    assert any(ev[:3] == ("wave", 1, "MASSIVE WAVE") and ev[3] == 32 for ev in events)
    out = lambda: [e for e in st.enemies if e.kind != "mothership"]
    assert 5 <= len(out()) <= 8 and len(fleet.parts) == 4
    assert fleet.timer == pytest.approx(FLEET["cooloff"], abs=1.0)
    events = tick(st, battle, 8.5, fleet)
    assert len(out()) == 32 and not fleet.parts
    assert [ev[2] for ev in events if ev[0] == "wave_part"] == [2, 3, 4, 5]
    assert all(e.wave == 1 for e in out())
    assert fleet.number == 1                                # nothing else launched meanwhile


def test_the_parts_of_a_massive_wave_leave_from_different_sides_of_the_hangar():
    st, battle, ms, fleet = fleet_on_a_stage(ship=(2000.0, 2000.0), home=(6000.0, 2000.0))
    bunches = [[("infantry", 5, "line")]]
    fleet._release(30, bunches, 0.0)
    front = [e for e in st.enemies if e.kind != "mothership"]
    fleet._release(30, bunches, 144.0)
    back = [e for e in st.enemies if e.kind != "mothership" and e not in front]
    assert sum(e.x for e in front) / 5 < ms.x - 60          # the side facing you
    assert sum(e.x for e in back) / 5 > ms.x + 40           # round the back


def test_a_wave_of_two_hundred_launches_whole():
    st, battle, ms, fleet = fleet_on_a_stage(home=(2600.0, 2000.0))
    fleet.launched = 29
    fleet.call_now()
    tick(st, battle, FLEET["massive"]["group_gap"] * 4 + 1.0, fleet)
    out = [e for e in st.enemies if e.kind != "mothership" and e.alive]
    assert len(out) == 200 and {e.kind for e in out} == {"infantry", "rapid", "guard", "tank"}
    assert all(e.brain is not None for e in out)


# ------------------------------------------------------------ tanks


def tank_stage(at=(2900.0, 2000.0)):
    """A tank that always knows where you are (as in the sandbox), `at` on an empty stage."""
    st, battle, ms = hunt_stage()
    battle.hunt = None
    tank = battle.add_group("tank", 1, *at, warp=False)[0]
    return st, battle, tank


def test_a_tank_is_slow_and_hard_to_kill():
    spec = ENEMIES["tank"]
    assert spec["health"] == 800 and spec["speed"] == 30
    assert math.ceil(spec["health"] / (34 * 2.7)) in range(8, 11)      # fully upgraded sniper shots, as planned


def test_a_tank_closes_to_range_then_holds_and_fires_volleys():
    st, battle, tank = tank_stage()
    assert isinstance(tank.brain, TankBrain)
    reach = AI["tank"]["range"]
    events = tick(st, battle, 14.0)
    d = dist(tank.x, tank.y, st.ship.x, st.ship.y)
    assert reach * 0.8 <= d <= reach + 5                     # it stopped at its range
    assert math.hypot(tank.mx, tank.my) == 0
    volleys = sum(1 for ev in events if ev[:2] == ("enemy_fire", "tank"))
    assert volleys >= 1
    fired = 0
    st.missiles.clear()
    tank.brain.volley_in = 0.0
    tick(st, battle, 0.1)
    fired += len(st.missiles)
    tick(st, battle, AI["tank"]["volley_gap"] + 0.1)
    assert len(st.missiles) == AI["tank"]["volley"] == 4
    assert all(m.owner == "enemy" and m.target == "player" for m in st.missiles)
    assert not tank.pods_loaded
    tick(st, battle, AI["tank"]["reload_show"])
    assert tank.pods_loaded


def test_tank_missiles_hurt_a_ship_that_sits_still():
    st, battle, tank = tank_stage(at=(2500.0, 2000.0))
    st.shield = 0.0
    hull = st.hull
    tick(st, battle, 16.0)
    assert st.hull < hull


def test_a_tank_out_of_range_holds_its_fire():
    st, battle, tank = tank_stage(at=(3400.0, 2000.0))
    events = tick(st, battle, 5.0)
    assert not st.missiles and not any(ev[:2] == ("enemy_fire", "tank") for ev in events)
    assert tank.x < 3400.0                                   # but it is on its way


def test_a_tank_mends_slowly_when_left_alone():
    st, battle, tank = tank_stage(at=(3400.0, 2000.0))
    spec = ENEMIES["tank"]
    st.damage_enemy(tank, 300.0, tank.x, tank.y, source="sniper")
    assert tank.health == 500
    tick(st, battle, spec["repair_delay"] - 0.5)
    assert tank.health == 500                                # not yet
    tick(st, battle, 10.5)
    assert tank.health == pytest.approx(500 + spec["repair"] * 10, abs=1.0)
    # Steady fire stops it mending.
    for _ in range(10):
        st.damage_enemy(tank, 1.0, tank.x, tank.y, source="auto")
        tick(st, battle, 1.0)
    assert tank.health < 530
    assert spec["repair"] * 60 < spec["health"] * 0.3         # very slowly: under a third in a minute


def test_a_tank_shells_your_structures_when_it_cannot_find_you():
    st, battle, ms = hunt_stage(ship=(2000.0, 2000.0))
    sentry = Structure("sentry", 5000.0, 2000.0, radius=8.0, health=200.0, max_health=200.0, uid=st.uid())
    st.structures.append(sentry)
    battle.hunt.drills[sentry.uid] = sentry
    tank = battle.add_group("tank", 1, 5400.0, 2000.0, warp=False)[0]
    events = tick(st, battle, 22.0)
    assert not battle.hunt.known
    assert any(ev[0] == "struct_hit" and ev[1] == "sentry" and ev[4] == "missile" for ev in events)
    assert sentry.health < 200.0
    assert dist(tank.x, tank.y, sentry.x, sentry.y) >= 395.0      # from where it was: it never closed in


def test_an_enemy_missile_bursts_on_a_structure_in_its_way():
    st, battle, ms = hunt_stage()
    battle.hunt = None
    drill = Structure("drill", 2300.0, 2000.0, radius=6.0, health=80.0, max_health=80.0, uid=st.uid())
    st.structures.append(drill)
    tank = battle.add_group("tank", 1, 2600.0, 2000.0, warp=False)[0]
    tank.brain.volley_in = 99.0
    tank.heading = 270.0
    st.tank_missiles(tank, drill)
    events = tick(st, battle, 6.0)
    assert drill.health == 80.0 - 2 * ENEMY_WEAPONS["tank_missile"]["damage"]
    assert sum(1 for ev in events if ev[0] == "struct_hit") == 2


def test_a_tanks_escort_stays_between_it_and_you():
    st, battle, tank = tank_stage(at=(3000.0, 2000.0))
    squad = battle.add_group("infantry", 4, 2950.0, 2000.0, warp=False)[0].brain.squad
    squad.escort = tank
    tick(st, battle, 12.0)
    cx, cy = squad.centre()
    leash = AI["tank"]["escort_leash"]
    assert dist(cx, cy, tank.x, tank.y) <= leash + 40
    assert st.ship.x < cx < tank.x and abs(cy - tank.y) < 60          # on the line between you
    # With the tank gone the squad comes for you like any other.
    tank.alive = False
    tick(st, battle, 30.0)
    assert squad.escort is None
    assert dist(*squad.centre(), st.ship.x, st.ship.y) < AI["infantry"]["standoff"] + 60


def test_a_launched_tank_brings_its_escort():
    st, battle, ms, fleet = fleet_on_a_stage(home=(2600.0, 2000.0))
    fleet.launched = 11
    fleet.call_now()
    tick(st, battle, 0.5, fleet)
    tank = next(e for e in st.enemies if e.kind == "tank")
    escorts = [sq for sq in battle.squads if sq.escort is tank]
    assert len(escorts) == 1 and len(escorts[0].members) >= FLEET["escort"]["infantry"]
    assert sum(1 for e in st.enemies if e.kind == "guard") >= FLEET["escort"]["guard"]


# ------------------------------------------------------------ two hundred at once


def test_piled_up_ships_ease_apart_whatever_their_number():
    st, battle, ms = hunt_stage()
    battle.hunt = None
    ships = [st.spawn("infantry", 3000.0 + (i % 16) * 2.0, 2000.0 + (i // 16) * 2.0, warp=False) for i in range(250)]
    ships.append(st.spawn("tank", 3010.0, 2010.0, warp=False))
    for _ in range(240):
        st._separate_enemies()
    r = ships[0].body_r
    worst = min(dist(a.x, a.y, b.x, b.y) for i, a in enumerate(ships[:250]) for b in ships[i + 1:250])
    assert worst >= 2 * r * 0.9
    assert all(dist(e.x, e.y, ships[-1].x, ships[-1].y) >= (r + ships[-1].body_r) * 0.9 for e in ships[:250])


def test_a_ship_far_from_any_rock_is_left_alone_until_one_could_reach_it():
    st, battle, ms = hunt_stage()                            # no rocks at all here
    far = st.spawn("infantry", 3000.0, 2000.0, warp=False)
    st.step(DT)
    assert far.rock_free > st.time + 0.2
    game = campaign()
    f = game.stage.field
    i = int(next(i for i in range(len(f)) if not f.gone[i] and f.size[i] >= 48))
    near = game.stage.spawn("infantry", float(f.x[i]) + float(f.r[i]) + 20.0, float(f.y[i]), warp=False)
    game.stage.step(DT)
    assert near.rock_free <= game.stage.time                 # beside a rock: checked every step
    st.push_enemy(far, 50.0, 0.0)                             # a shove puts it back under watch
    assert far.rock_free == 0.0


def test_a_ship_pushed_into_a_rock_still_slides_off_it():
    game = campaign()
    st = game.stage
    f = st.field
    game.fleet.timer = 1e9
    i = int(next(i for i in range(len(f)) if not f.gone[i] and f.size[i] >= 48))
    e = st.spawn("infantry", float(f.x[i]) + float(f.r[i]) + 150.0, float(f.y[i]), warp=False)
    for _ in range(240):
        e.mx = -220.0                                        # flying straight at the rock
        st.step(DT)
    assert dist(e.x, e.y, float(f.x[i]), float(f.y[i])) >= float(f.r[i]) + e.body_r - 1.0


def test_shots_still_stop_at_rocks():
    game = campaign()
    st = game.stage
    f = st.field
    game.fleet.timer = 1e9
    i = int(next(i for i in range(len(f)) if not f.gone[i] and f.size[i] >= 48))
    x, y = float(f.x[i]), float(f.y[i])
    for start in (120.0, 320.0):
        st.ship.x, st.ship.y = x - float(f.r[i]) - start, y
        st.shots.clear()
        st.fire_auto(heading=90.0)
        st.fire_sniper(heading=90.0)
        events = []
        for _ in range(90):
            st.events = []
            st.step(DT)
            events += st.events
        assert sum(1 for ev in events if ev[0] == "rock" and ev[1] == "player") == 2, start
        assert not st.shots
