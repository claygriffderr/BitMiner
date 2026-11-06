"""The combat stage and the weapon gallery scenes, without a window."""

import math

import pytest

from bitminer.combat import shapes
from bitminer.combat.specs import DEFENSE, ENEMIES, ENEMY_WEAPONS, GALLERY, WEAPONS
from bitminer.combat.stage import Stage
from bitminer.flight import Controls
from bitminer.gallery import scenes as SC
from bitminer.gallery.director import ARENA, Director
from bitminer.settings import Tuning

C = (1600.0, 1000.0)


class Quiet:
    """Stands in for a particle system."""

    def burst(self, *a, **k):
        pass

    def emit(self, *a, **k):
        pass


def stage() -> Stage:
    st = Stage(Quiet(), Quiet())
    st.ship.x, st.ship.y = C
    return st


def run(st: Stage, seconds: float, dt: float = 1 / 60) -> None:
    for _ in range(round(seconds / dt)):
        st.step(dt)


def test_hit_masks_follow_the_turn():
    mask = shapes.enemy_mask("tank")
    h, w = mask.shape
    nose = h / 2 - 1.5                 # just inside the top edge, unturned
    assert shapes.hits(mask, 0, 0, 0, 0, nose)
    assert not shapes.hits(mask, 0, 0, 0, 0, nose + 4)
    # Turned 90 degrees clockwise, the top now points right.
    assert shapes.hits(mask, 0, 0, 90, nose, 0)
    assert not shapes.hits(mask, 0, 0, 90, 0, nose + 3)


def test_sniper_round_goes_through_three_hulls_but_not_four():
    st = stage()
    foes = [st.spawn("infantry", C[0], C[1] + 60 + 22 * i, warp=False, health=1000) for i in range(4)]
    st.fire_sniper()
    run(st, 0.5)
    hit = [e.health < 1000 for e in foes]
    assert hit == [True] * WEAPONS["sniper"]["pierce"] + [False] * (4 - WEAPONS["sniper"]["pierce"])


def test_missile_hits_its_target_harder_than_a_bystander():
    st = stage()
    target = st.spawn("guard", C[0], C[1] + 120, warp=False, health=1000)
    near = st.spawn("guard", C[0] - 24, C[1] + 118, warp=False, health=1000)   # on the left pod's side
    assert st.fire_missile(target)
    run(st, 3.0)
    lost_target, lost_near = 1000 - target.health, 1000 - near.health
    assert lost_target >= WEAPONS["missile"]["damage"]
    assert 0 < lost_near < lost_target


def test_missiles_leave_one_at_a_time_then_the_rack_reloads():
    st = stage()
    w = WEAPONS["missile"]
    salvo = int(w["salvo"])
    target = st.spawn("tank", C[0], C[1] + 300, warp=False, health=1e6)
    launches = []                                  # (time, which side of the ship)
    t = 0.0
    while t < salvo * w["gap"] + 1.0:              # holding the trigger
        if st.fire_missile(target):
            m = st.missiles[-1]
            side = (m.x - st.ship.x) * math.cos(math.radians(st.ship.angle))
            launches.append((t, "left" if side < 0 else "right"))
        st.step(1 / 60)
        t += 1 / 60
    assert len(launches) == salvo                  # the rack is spent, so the trigger does nothing
    gaps = [b[0] - a[0] for a, b in zip(launches, launches[1:])]
    assert min(gaps) >= w["gap"] - 1e-6
    assert [s for _, s in launches] == ["left", "right"] * (salvo // 2)
    assert st.missiles_loaded == 0 and st.missile_reload > 0
    run(st, w["reload"])
    assert st.missiles_loaded == salvo and st.missile_ready


def test_part_used_rack_tops_up_after_holding_fire():
    st = stage()
    w = WEAPONS["missile"]
    st.fire_missile(None)
    run(st, w["reload"] * 0.5)
    assert st.missiles_loaded == int(w["salvo"]) - 1
    run(st, w["reload"] * 0.5 + 0.05)
    assert st.missiles_loaded == int(w["salvo"])


def test_laser_reaches_off_screen_from_anywhere_the_camera_puts_you():
    from bitminer.camera import MAX_LEAD
    from bitminer.graphics.renderer import VIEW
    corner = math.hypot(VIEW[0] / 2 + MAX_LEAD[0], VIEW[1] / 2 + MAX_LEAD[1])
    assert WEAPONS["laser"]["length"] > corner


def test_laser_burns_everything_in_its_path():
    st = stage()
    foes = [st.spawn("infantry", C[0], C[1] + 50 + 40 * i, warp=False, health=1000) for i in range(3)]
    st.start_laser()
    w = WEAPONS["laser"]
    run(st, w["warmup"] + w["duration"] + 0.1)
    for e in foes:
        assert 1000 - e.health == pytest.approx(w["dps"] * w["duration"], rel=0.1)
    assert not st.beams


def test_shield_takes_hits_then_breaks_then_the_hull_does():
    st = stage()
    st.shield = 10.0
    assert st.damage_player(6, C[0], C[1] + 20) == "shield"
    assert st.hull == st.hull_max
    st.damage_player(6, C[0], C[1] + 20)
    assert st.shield == 0
    assert any(a.name == "shield_break" for a in st.anims)
    assert st.damage_player(6, C[0], C[1] + 20) == "armor"
    assert st.hull == pytest.approx(st.hull_max - 6 * st.armor_factor)   # armor takes its share
    assert st.armor_factor < 1


def test_mothership_beam_stops_at_the_shield():
    st = stage()
    ms = st.spawn("mothership", C[0], C[1] + 200, heading=180, warp=False)
    beam = st.mothership_beam(ms)
    run(st, 0.2)
    assert beam.end[1] == pytest.approx(C[1] + DEFENSE["shield_radius"], abs=4)
    assert st.shield < st.shield_max


def test_tank_missiles_can_be_shot_down():
    st = stage()
    tank = st.spawn("tank", C[0], C[1] + 150, heading=180, warp=False)
    st.tank_missiles(tank)
    m = st.missiles[0]
    from bitminer.combat.stage import Shot
    st.shots.append(Shot("player", "auto", m.x, m.y - 10, 0, 500, 4, 1.0))
    run(st, 0.1)
    assert m not in st.missiles
    assert len(st.missiles) == 1
    assert ENEMY_WEAPONS["tank_missile"]["health"] <= WEAPONS["auto"]["damage"]


@pytest.mark.parametrize("scene", SC.SCENES, ids=lambda s: s.key)
def test_every_gallery_scene_plays_through_and_loops(scene):
    st = stage()
    d = Director(st, Tuning(), C)
    d.start(scene)
    seen = {}
    shield_low, hull_low = st.shield, st.hull
    t = 0.0
    while d.finished == 0:
        d.step(1 / 60)
        t += 1 / 60
        assert t < 16, "the scene never finished"
        for e in st.enemies:
            seen[e.uid] = e
        if not d.finished:
            shield_low, hull_low = min(shield_low, st.shield), min(hull_low, st.hull)
    if scene.column in WEAPONS:
        assert seen and all(not e.alive for e in seen.values()), "every target should be destroyed"
    elif scene.column == "shoot_down":
        assert hull_low == st.hull_max and (shield_low == st.shield_max or scene.row != "shield")
    elif scene.row == "shield":
        assert shield_low < st.shield_max and hull_low == st.hull_max
    elif scene.row == "shield_breaks":
        assert shield_low == 0 and hull_low < st.hull_max
    else:
        assert hull_low < st.hull_max
    assert d.loops == 1 and d.running          # and it started again


def test_gallery_health_comes_from_the_data_file():
    from bitminer.gallery.director import health_for
    w = WEAPONS["auto"]
    assert health_for("auto", "tank") == GALLERY["auto_seconds"]["tank"] * w["fire_rate"] * w["damage"]
    assert set(GALLERY["sniper_hits"]) == set(ENEMIES)


def test_free_fly_stays_in_the_arena_and_fires():
    st = stage()
    d = Director(st, Tuning(), C)
    d.auto = False
    d.weapon = "auto"
    d.start(SC.find("auto", "guard"))
    for _ in range(60 * 6):
        d.step(1 / 60, Controls(forward=True, aim=90.0), trigger=True)
    assert abs(st.ship.x - C[0]) <= ARENA[0] + 1e-6
    assert any(s.owner == "player" for s in st.shots)


def test_holding_fire_in_free_fly_empties_the_missile_rack_then_reloads():
    st = stage()
    d = Director(st, Tuning(), C)
    d.auto = False
    d.weapon = "missile"
    d.start(SC.find("missile", "tank"))
    w = WEAPONS["missile"]
    launched = set()
    for _ in range(round((w["salvo"] * w["gap"] + 0.5) * 60)):
        d.step(1 / 60, Controls(), trigger=True, cursor=(C[0], C[1] + 120))
        launched |= {m.uid for m in st.missiles if m.owner == "player"}
    assert len(launched) == w["salvo"] and st.missile_reload > 0


def test_scene_list_is_complete():
    assert len(SC.SCENES) == len(WEAPONS) * len(ENEMIES) + len(SC.ATTACKS) * len(SC.DEFENSES)
    assert len(SC.BY_KEY) == len(SC.SCENES)
    assert all(math.isfinite(s.focus[1]) for s in SC.SCENES)
