"""The combat sandbox: bumping, rocks in the way, enemy brains, waves, respawns and the play log."""

import json
import math

import pytest

from bitminer.combat import shapes
from bitminer.combat.ai import Battle, Waves
from bitminer.combat.arsenal import Arsenal
from bitminer.combat.sandbox import Sandbox, autopilot
from bitminer.combat.specs import AI, DEFENSE, ENEMIES, SANDBOX, WAVES, WEAPONS
from bitminer.combat.stage import Stage, dist
from bitminer.field import AsteroidField
from bitminer.flight import Controls
from bitminer.playdata import PlayLog
from bitminer.settings import Tuning

W, H = 3200.0, 2000.0
C = (1600.0, 1000.0)
DT = 1 / 60


class Quiet:
    def burst(self, *a, **k):
        pass

    def emit(self, *a, **k):
        pass


def stage(rocks=()) -> Stage:
    """A stage in wrapping space with your ship at C and the given rocks: (x, y, size)."""
    st = Stage(Quiet(), Quiet())
    st.ship.x, st.ship.y = C
    st.ship.ux, st.ship.uy = C
    f = AsteroidField(W, H)
    for x, y, size in rocks:
        f.add(x, y, size, 0, False)
    st.field = f
    st.world = (W, H)
    st.collide_bodies = True
    st.regen = True
    st.can_die = True
    return st


def run(st: Stage, seconds: float, battle: Battle | None = None) -> list:
    events = []
    for _ in range(round(seconds / DT)):
        st.recentre()
        if battle is not None:
            battle.step(DT)
        st.step(DT)
        events += st.events
        st.events = []
    return events


def ship_points(st: Stage):
    from bitminer.flight import forward_vector, right_vector
    ship = st.ship
    pts = shapes.mask_points()
    fx, fy = forward_vector(ship.angle)
    rx, ry = right_vector(ship.angle)
    return ship.x + pts[:, 0] * rx + pts[:, 1] * fx, ship.y + pts[:, 0] * ry + pts[:, 1] * fy


# ---------------------------------------------------------------- bumping

def test_ship_and_enemy_hulls_push_apart_and_trade_momentum():
    st = stage()
    e = st.spawn("infantry", C[0], C[1] + 9, warp=False, heading=180)
    st.ship.vy = 150.0                         # flying up into it
    st.step(DT)
    wx, wy = ship_points(st)
    assert not shapes.hits_many(e.mask, e.x, e.y, e.sprite_angle, wx, wy).any()
    assert st.ship.vy < 150.0                  # slowed by the hit
    assert e.vy > st.ship.vy                   # and shoved it away faster than you follow
    assert any(ev[0] == "bump" for ev in st.events)


def test_a_hard_bump_hurts_and_a_soft_one_does_not():
    safe = DEFENSE["impact"]["safe_speed"]
    for speed, hurt in ((safe * 0.3, False), (safe * 3.0, True)):
        st = stage()
        st.spawn("guard", C[0], C[1] + 13, warp=False, heading=180)
        st.ship.vy = speed
        st.step(DT)
        assert (st.shield < st.shield_max) == hurt, speed


def test_the_mothership_does_not_budge():
    st = stage()
    ms = st.spawn("mothership", C[0], C[1] + 110, warp=False, heading=180, health=1000)
    st.ship.vy = 200
    for _ in range(30):
        st.ship.x += st.ship.vx * DT
        st.ship.y += st.ship.vy * DT
        st.step(DT)
    assert (ms.x, ms.y) == (C[0], C[1] + 110)
    assert st.ship.vy < 0


def test_enemies_slide_off_rocks_without_shoving_them():
    st = stage([(C[0], C[1] + 100, 24)])
    e = st.spawn("infantry", C[0], C[1] + 100 - 14, warp=False)
    e.my = 70.0                                # flying straight at the rock
    run(st, 1.0)
    f = st.field
    assert dist(e.x, e.y, f.x[0], f.y[0]) >= f.r[0] + e.body_r - 0.5
    assert (f.vx[0], f.vy[0]) == (0.0, 0.0)


# ---------------------------------------------------------------- wrapping space

def test_recentre_brings_things_to_the_copy_nearest_you():
    st = stage()
    st.ship.x, st.ship.y = 10.0, 20.0
    battle = Battle(st)
    e = battle.add("infantry", W - 10.0, 20.0, warp=False)
    e.brain.goal = (W - 30.0, 20.0)
    shot_owner = st.shots
    st.enemy_shot(e, "infantry", (0.0, 20.0))
    st.recentre()
    assert e.x == pytest.approx(-10.0)
    assert e.brain.goal == pytest.approx((-30.0, 20.0))
    assert shot_owner[0].x < 0


# ---------------------------------------------------------------- rocks in the way

def test_your_shots_stop_on_a_rock():
    st = stage([(C[0], C[1] + 60, 28)])
    e = st.spawn("infantry", C[0], C[1] + 140, warp=False, health=1000)
    for _ in range(10):
        st.fire_auto(0.0)
    events = run(st, 1.0)
    assert e.health == 1000
    assert ("rock", "player", "auto") in events


def test_a_missile_bursts_on_a_rock_in_its_way():
    st = stage([(C[0], C[1] + 160, 80)])
    e = st.spawn("infantry", C[0], C[1] + 215, warp=False, health=1000)     # hiding behind it
    st.ship.angle = 0.0
    st.fire_missile(e)
    run(st, 2.0)
    assert e.health == 1000
    assert not st.missiles


def test_the_laser_stops_at_a_rock():
    st = stage([(C[0], C[1] + 80, 40)])
    behind = st.spawn("infantry", C[0], C[1] + 200, warp=False, health=1000)
    beam = st.start_laser()
    run(st, WEAPONS["laser"]["warmup"] + 0.3)
    assert beam.reach < 80
    assert behind.health == 1000


def test_the_laser_kills_infantry_and_rapid_at_once_and_guards_in_a_quarter_second():
    spec = WEAPONS["laser"]
    for kind, most in (("infantry", 0.06), ("rapid", 0.06), ("guard", 0.3)):
        st = stage()
        e = st.spawn(kind, C[0], C[1] + 60, warp=False)
        st.start_laser()
        t = 0.0
        while e.alive and e.dying < 0 and t < 2.0:
            st.step(DT)
            t += DT
        assert not e.alive, kind
        assert t - spec["warmup"] <= most + DT, (kind, t)
    assert 90 / spec["dps"] >= 0.2                      # a guard isn't instant either


def test_the_laser_burns_through_every_enemy_in_its_path():
    st = stage()
    line = [st.spawn("guard", C[0], C[1] + 40 + 30 * i, warp=False, health=1000) for i in range(4)]
    st.start_laser()
    run(st, WEAPONS["laser"]["warmup"] + 0.2)
    assert all(e.health < 1000 for e in line)


def test_the_laser_stops_on_the_mothership():
    st = stage()
    ms = st.spawn("mothership", C[0], C[1] + 200, warp=False, heading=180, health=10 ** 6)
    behind = st.spawn("infantry", C[0], C[1] + 400, warp=False, health=1000)
    beam = st.start_laser()
    run(st, WEAPONS["laser"]["warmup"] + 0.3)
    assert ms.health < 10 ** 6
    assert behind.health == 1000
    assert beam.reach < 200


def test_a_laser_cut_short_on_the_nose_still_has_a_picture():
    from art import sprites as S
    for length in range(1, 12):
        for frame in (0, 1):
            assert S.laser_player(length, frame).size == (9, length)


def test_infantry_hold_fire_with_a_rock_in_the_way():
    st = stage([(C[0], C[1] + 70, 40)])
    battle = Battle(st)
    battle.add("infantry", C[0], C[1] + 140, warp=False)
    events = run(st, 4.0, battle)
    assert not any(ev[0] == "enemy_fire" for ev in events)


# ---------------------------------------------------------------- the laser's charges

def test_the_laser_has_charges_that_recharge():
    st = stage()
    arsenal = Arsenal(st)
    arsenal.select("laser")
    spec = WEAPONS["laser"]
    beams = 0
    for _ in range(int(spec["charges"]) + 1):
        arsenal.step(DT, True)
        if any(ev == ("fire", "laser") for ev in st.events):
            beams += 1
        empty = ("empty", "laser") in st.events
        st.events = []
        for _ in range(round((spec["warmup"] + spec["duration"] + 0.5) / DT)):
            arsenal.step(DT, False)
            st.step(DT)
    assert beams == spec["charges"]
    assert empty
    assert arsenal.charges == 0
    for _ in range(round(spec["recharge"] / DT) + 2):
        arsenal.step(DT, False)
    assert arsenal.charges == 1


# ---------------------------------------------------------------- enemy brains

def squad(st: Stage, battle: Battle, n: int = 4, formation: str = "line"):
    return battle.add_group("infantry", n, C[0], C[1] + 300, formation, warp=False)


@pytest.mark.parametrize("formation", ["line", "wedge", "arc"])
def test_a_squad_holds_its_standoff_in_formation(formation):
    st = stage()
    battle = Battle(st, seed=3)
    members = squad(st, battle, 5, formation)
    st.shield = 10 ** 6                       # keep you alive and still
    st.shield_max = 10 ** 6
    run(st, 8.0, battle)
    cfg = AI["infantry"]
    for m in members:
        assert abs(dist(m.x, m.y, *C) - cfg["standoff"]) < cfg["spacing"] * 2.2
    for i, a in enumerate(members):
        for b in members[i + 1:]:
            assert dist(a.x, a.y, b.x, b.y) > cfg["spacing"] * 0.5


def test_infantry_shoot_you():
    st = stage()
    battle = Battle(st, seed=3)
    squad(st, battle, 4)
    events = run(st, 8.0, battle)
    assert any(ev[0] == "enemy_fire" for ev in events)
    assert st.shield < st.shield_max


def test_two_squads_keep_apart():
    st = stage()
    battle = Battle(st, seed=5)
    a = battle.add_group("infantry", 4, C[0], C[1] + 300, "line", warp=False)
    b = battle.add_group("infantry", 4, C[0] + 30, C[1] + 300, "line", warp=False)
    st.shield = st.shield_max = 10 ** 6
    run(st, 10.0, battle)
    ca = (sum(e.x for e in a) / 4, sum(e.y for e in a) / 4)
    cb = (sum(e.x for e in b) / 4, sum(e.y for e in b) / 4)
    assert dist(*ca, *cb) > AI["infantry"]["spacing"] * 3


def test_a_lone_infantry_joins_another_squad():
    st = stage()
    battle = Battle(st, seed=5)
    a = battle.add_group("infantry", 3, C[0], C[1] + 300, "line", warp=False)
    battle.add_group("infantry", 3, C[0] + 200, C[1] - 300, "line", warp=False)
    for e in a[:2]:
        st.damage_enemy(e, 1000, e.x, e.y)
    run(st, 0.1, battle)
    assert len(battle.squads) == 1
    assert len(battle.squads[0].members) == 4


def test_a_guard_walls_off_its_squad():
    st = stage()
    battle = Battle(st, seed=2)
    members = squad(st, battle, 4)
    g = battle.add("guard", C[0] + 100, C[1] + 400, warp=False)
    st.shield = st.shield_max = 10 ** 6
    run(st, 14.0, battle)
    cx = sum(m.x for m in members) / 4
    cy = sum(m.y for m in members) / 4
    # The guard sits between you and the squad's middle.
    assert dist(g.x, g.y, *C) < dist(cx, cy, *C)
    assert dist(g.x, g.y, cx, cy) < AI["guard"]["wall_gap"] * 1.8


def guard_fight(seconds: float, squad_size: int, hurt_guard: bool = False):
    """A guard with a squad, you sitting still and unkillable. Returns what happened, frame by frame."""
    st = stage()
    battle = Battle(st, seed=2)
    members = squad(st, battle, squad_size)
    g = battle.add("guard", C[0], C[1] + 160, warp=False)
    g.brain.cooldown = 0.0
    if hurt_guard:
        st.damage_enemy(g, g.max_health * 0.8, g.x, g.y)
    st.shield = st.shield_max = 10 ** 6
    frames = []
    for _ in range(round(seconds / DT)):
        st.recentre()
        battle.step(DT)
        st.step(DT)
        frames.append((list(st.events), [ln for ln in st.lanes if ln.kind == "ram"], g.brain.state))
        st.events = []
    return st, battle, g, members, frames


def test_a_guard_holds_the_wall_while_its_squad_can_fight():
    st, battle, g, members, frames = guard_fight(8.0, 4, hurt_guard=True)
    assert not any(("ram", "guard") in ev for ev, _, _ in frames)
    assert all(state == "wall" for _, _, state in frames)


def test_a_guard_rams_once_its_squad_is_down_to_a_couple_and_warns_first():
    st, battle, g, members, frames = guard_fight(0.5, 4)
    for m in members[:4 - AI["guard"]["ram_when_left"]]:
        st.damage_enemy(m, 1000, m.x, m.y)
    saw_lane = rammed = hit = False
    for _ in range(round(4.0 / DT)):
        st.recentre()
        battle.step(DT)
        st.step(DT)
        saw_lane |= any(lane.kind == "ram" for lane in st.lanes)
        rammed |= ("ram", "guard") in st.events
        hit |= any(ev[0] == "hurt" and ev[1] == "guard" for ev in st.events)
        if rammed:
            assert saw_lane                        # the lane always shows before the charge
        st.events = []
    assert rammed and hit
    assert not g.ramming


def test_a_guard_keeps_aiming_through_the_warning_then_locks():
    st = stage()
    battle = Battle(st, seed=2)
    g = battle.add("guard", C[0], C[1] + 120, warp=False)      # no squad: it rams when you are close
    g.brain.cooldown = 0.0
    st.shield = st.shield_max = 10 ** 6
    spec, cfg = ENEMIES["guard"], AI["guard"]
    while g.brain.state != "warn":
        battle.step(DT)
        st.step(DT)
    start = g.heading
    # Slide sideways through the warning.
    headings, locked = [], []
    while g.brain.state == "warn":
        st.ship.x += 120 * DT
        battle.step(DT)
        st.step(DT)
        lane = g.brain.lane
        if lane is not None:
            headings.append(lane.heading)
            locked.append(lane.locked)
    assert abs(headings[-1] - start) > 10              # it followed you
    n_locked = sum(locked)
    assert n_locked == pytest.approx(cfg["lock_time"] / DT, abs=2)
    assert len(set(round(h, 3) for h, lk in zip(headings, locked) if lk)) == 1    # and then held still
    assert locked[-1] and not locked[0]
    assert spec["warn_time"] > cfg["lock_time"]


def test_a_guard_shot_down_mid_warning_takes_its_lane_away():
    st = stage()
    battle = Battle(st, seed=2)
    g = battle.add("guard", C[0], C[1] + 100, warp=False)      # no squad and you close: it rams
    g.brain.cooldown = 0.0
    for _ in range(round(2.0 / DT)):
        battle.step(DT)
        st.step(DT)
        if st.lanes:
            break
    assert st.lanes
    st.damage_enemy(g, 10 ** 6, g.x, g.y)
    run(st, 0.1, battle)
    assert not st.lanes


def test_guards_share_out_the_squads_width():
    st = stage()
    battle = Battle(st, seed=2)
    battle.add_group("infantry", 5, C[0], C[1] + 300, "line", warp=False)
    guards = [battle.add("guard", C[0] - 30 + 60 * i, C[1] + 250, warp=False) for i in range(2)]
    st.shield = st.shield_max = 10 ** 6
    run(st, 12.0, battle)
    gap = dist(guards[0].x, guards[0].y, guards[1].x, guards[1].y)
    assert gap > AI["guard"]["spacing"] * 1.5          # spread across the line, not bunched up


def test_rapid_ships_wait_behind_you_then_dive_and_fire_a_burst():
    st = stage()
    battle = Battle(st, seed=4)
    e = battle.add("rapid", C[0], C[1] - 300, warp=False)
    st.shield = st.shield_max = 10 ** 6
    states, fired = set(), 0
    for _ in range(round(10 / DT)):
        battle.step(DT)
        st.step(DT)
        states.add(e.brain.state)
        fired += sum(1 for ev in st.events if ev == ("enemy_fire", "rapid"))
        st.events = []
    assert states == {"hold", "dive"}
    assert fired >= 3


def test_enemies_steer_round_rocks():
    st = stage([(C[0], C[1] + 150, 44)])
    battle = Battle(st)
    e = battle.add("infantry", C[0], C[1] + 230, warp=False)
    e.brain.goal = (C[0] + 1, C[1] + 70)
    for _ in range(round(4 / DT)):
        e.brain.fly(DT)
        st.step(DT)
    assert dist(e.x, e.y, C[0] + 1, C[1] + 70) < 4


def test_an_enemy_wedged_in_rocks_notices_and_breaks_loose():
    # A pocket of rocks open to the south, with the goal straight through its back wall.
    rocks = [(C[0], C[1] + 60, 44), (C[0] - 34, C[1] + 40, 44), (C[0] + 34, C[1] + 40, 44),
             (C[0] - 46, C[1] + 6, 44), (C[0] + 46, C[1] + 6, 44)]
    st = stage(rocks)
    battle = Battle(st, seed=1)
    e = battle.add("infantry", C[0], C[1] + 15, warp=False)
    e.brain.goal = (C[0], C[1] + 140)
    stuck = 0
    for _ in range(round(9 / DT)):
        e.brain.fly(DT)
        st.step(DT)
        stuck += sum(1 for ev in st.events if ev == ("stuck", "infantry"))
        st.events = []
    assert 1 <= stuck <= 3
    assert dist(e.x, e.y, *e.brain.goal) < 12          # out of the pocket and round to the goal


def test_an_enemy_flying_freely_is_never_called_stuck():
    st = stage([(C[0] + 60, C[1] + 70, 40)])
    battle = Battle(st, seed=1)
    e = battle.add("infantry", C[0], C[1], warp=False)
    stuck = 0
    for k in range(round(8 / DT)):
        if k % 120 == 0:                                # a new goal every two seconds, round the rock
            e.brain.goal = (C[0] + 120 * (1 if k % 240 else -1), C[1] + 140)
        e.brain.fly(DT)
        st.step(DT)
        stuck += sum(1 for ev in st.events if ev[0] == "stuck")
        st.events = []
    assert stuck == 0


def test_formation_slots_inside_a_rock_are_moved_out():
    st = stage()
    battle = Battle(st, seed=1)
    members = squad(st, battle, 3)
    sq = battle.squads[0]
    sq.plan()
    x, y = members[1].brain.goal
    st.field.add(x, y, 40, 0, False)
    sq.plan()
    for m in members:
        gx, gy = m.brain.goal
        assert dist(gx, gy, x, y) >= st.field.r[0] + m.body_r - 0.5


# ---------------------------------------------------------------- waves

def test_waves_arrive_on_a_timer_and_grow_each_time_round():
    st = stage()
    battle = Battle(st, seed=1)
    spec = dict(WAVES, first=1.0, every=2.0, cap=10 ** 6,
                list=[{"name": "A", "groups": [{"kind": "infantry", "count": 2, "formation": "line"}]},
                      {"name": "B", "next": 1.0, "groups": [{"kind": "rapid", "count": 1},
                                                            {"kind": "guard", "count": 1}]}])
    waves = Waves(battle, spec)
    seen = []

    def tick(seconds):
        for _ in range(round(seconds / DT)):
            waves.step(DT)
            seen.extend(ev for ev in st.events if ev[0] == "wave")
            st.events = []

    tick(0.9)
    assert not st.enemies
    tick(0.2)
    assert [e.kind for e in st.enemies] == ["infantry"] * 2
    assert all(abs(dist(e.x, e.y, *C) - spec["spawn_distance"]) < 40 for e in st.enemies)
    tick(2.0)
    assert sorted(e.kind for e in st.enemies[2:]) == ["guard", "rapid"]
    tick(1.0)                                  # wave B sets its own short gap
    assert [e.kind for e in st.enemies[4:]] == ["infantry"] * (2 + spec["grow"])
    assert [s[2] for s in seen] == ["A", "B", "A"]


def test_calling_the_next_wave_early_and_the_cap():
    st = stage()
    battle = Battle(st, seed=1)
    spec = dict(WAVES, first=30.0, cap=5,
                list=[{"name": "A", "groups": [{"kind": "infantry", "count": 4, "formation": "line"}]}])
    waves = Waves(battle, spec)
    waves.call_now()
    waves.step(DT)
    assert len(st.enemies) == 4
    waves.call_now()
    waves.step(DT)
    assert len(st.enemies) == 4 + 4 + spec["grow"]     # second time round the list: one more
    n = len(st.enemies)
    waves.call_now()
    waves.step(DT)
    assert len(st.enemies) == n                # 5 or more still flying: it waits


def test_waves_never_warp_in_inside_a_rock():
    sb = Sandbox(Quiet(), Quiet(), Tuning(), seed=7)
    for _ in range(4):
        sb.waves.launch()
    f = sb.world.field
    for e in sb.stage.enemies:
        idx, dx, dy = f.near(e.x, e.y, 30, 30)
        for i, a, b in zip(idx, dx, dy):
            assert math.hypot(a, b) >= f.r[i] + shapes.reach(e.kind) - 0.5


# ---------------------------------------------------------------- the sandbox

def test_going_down_and_coming_back():
    sb = Sandbox(Quiet(), Quiet(), Tuning(), seed=7)
    st = sb.stage
    sb.waves.timer = 10 ** 6
    st.shield = 0.0
    st.damage_player(10 ** 6, st.ship.x, st.ship.y, source="test")
    assert st.ship_down and not st.ship_visible
    sb.step(DT, Controls(), False)
    assert sb.downs == 1
    for _ in range(round(SANDBOX["respawn"] / DT) + 2):
        sb.step(DT, Controls(), False)
    assert not st.ship_down and st.ship_visible
    assert st.hull == st.hull_max and st.shield == st.shield_max
    assert st.invulnerable > 0
    st.damage_player(50, st.ship.x + 5, st.ship.y)
    assert st.shield == st.shield_max          # blinking: can't be hit


def test_the_shield_comes_back_after_a_quiet_spell():
    sb = Sandbox(Quiet(), Quiet(), Tuning(), seed=7)
    st = sb.stage
    sb.waves.timer = 10 ** 6
    st.damage_player(40, st.ship.x + 5, st.ship.y)
    low = st.shield
    for _ in range(round((DEFENSE["shield_delay"] - 0.5) / DT)):
        sb.step(DT, Controls(), False)
    assert st.shield == low
    for _ in range(round(2.0 / DT)):
        sb.step(DT, Controls(), False)
    assert st.shield > low


def test_a_minute_of_fighting_on_auto_pilot():
    sb = Sandbox(Quiet(), Quiet(), Tuning(), seed=7)
    st = sb.stage
    t = 0.0
    for _ in range(round(60 / DT)):
        controls, trigger, cursor = autopilot(sb, t)
        sb.step(DT, controls, trigger, cursor)
        t += DT
        ship = st.ship
        assert 0 <= ship.x < W and 0 <= ship.y < H
        for e in st.enemies:
            assert math.isfinite(e.x) and abs(e.x - ship.x) <= W / 2 + 50
    assert sb.waves.number >= 1
    assert sb.kills > 0


# ---------------------------------------------------------------- the play log

def test_the_play_log_writes_lines_you_can_read_back(tmp_path):
    sb = Sandbox(Quiet(), Quiet(), Tuning(), seed=7)
    log = PlayLog(tmp_path, {"mode": "test"}, dict(sample_every=0.5, keep=3))
    t = 0.0
    for _ in range(round(8 / DT)):
        controls, trigger, cursor = autopilot(sb, t)
        events = sb.step(DT, controls, trigger, cursor)
        log.record(DT, events, sb)
        t += DT
    log.close(sb)
    lines = [json.loads(line) for line in log.path.read_text().splitlines()]
    kinds = [line["type"] for line in lines]
    assert kinds[0] == "start" and kinds[-1] == "end"
    assert kinds.count("sample") >= 15
    assert "wave" in kinds
    assert any(line.get("counts", {}).get("fire_auto") for line in lines if line["type"] == "sample")


def test_the_play_log_keeps_only_the_newest_files(tmp_path):
    for i in range(5):
        (tmp_path / f"fight-2026010{i}-000000.jsonl").write_text("{}\n")
    PlayLog(tmp_path, {}, dict(sample_every=0.5, keep=3))
    assert len(list(tmp_path.glob("fight-*.jsonl"))) == 2      # the new one makes three


def test_combat_numbers_are_all_in_the_data_files():
    for kind in ("infantry", "guard", "rapid"):
        assert kind in AI and "speed" in ENEMIES[kind]
    assert WAVES["list"] and all(g["kind"] in AI for w in WAVES["list"] for g in w["groups"])
