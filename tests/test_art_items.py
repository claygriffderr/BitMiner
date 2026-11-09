"""Checks on the sprint 6 art: drills, cracks, sentries, mines, ship extras and the station screen."""

import numpy as np

from art import hud, items as I, sprites as S, station
from art.palette import rgba


def _count(img, *names):
    a = np.array(img)
    return sum(int(np.all(a == np.array(rgba(n)), axis=2).sum()) for n in names)


def test_drill_bar_fills_from_the_bottom_in_eight_steps():
    gold = ("ore", "ore_hi", "ore_dark")
    assert _count(I.drill_interior(0.0), *gold) == 0
    assert _count(I.drill_interior(0.5), *gold) == 4 * 3
    assert _count(I.drill_interior(1.0), *gold) == 8 * 3 + 1      # plus the tip light, gold when full
    a = np.array(I.drill_interior(0.25))
    lit_rows = [y for y in range(I.TUBE_TOP, I.TUBE_TOP + I.TUBE_ROWS) if a[y, 5, 3] and tuple(a[y, 5]) != rgba("hull_black")]
    assert lit_rows == [I.TUBE_TOP + I.TUBE_ROWS - 2, I.TUBE_TOP + I.TUBE_ROWS - 1]


def test_full_drill_turns_its_light_gold():
    a = np.array(I.drill_interior(1.0, frame=0))
    assert tuple(a[0, 5]) == rgba("ore_hi")
    b = np.array(I.drill_interior(0.5, frame=0))
    assert tuple(b[0, 5]) == rgba("ion_hi")


def test_cracks_grow_with_each_stage_and_ore_fades():
    rock = S.asteroid(64, 4242, 12)
    cracks = I.crack_points(rock, [I.rim_point(rock, 25), I.rim_point(rock, 240)], 9)
    counts = [_count(I.crack_overlay(rock, cracks, st), "rock_shadow") for st in range(4)]
    assert counts[0] == 0
    assert counts[0] < counts[1] < counts[2] < counts[3]
    ore = [_count(I.drained_rock(64, 4242, 12, st), "ore", "ore_hi", "ore_dark") for st in range(4)]
    assert ore[0] > ore[1] > ore[2] > ore[3]


def test_shatter_breaks_apart_and_crumbles_away():
    rock = I.drained_rock(48, 106, 6, 3)
    frames = I.shatter(rock, 9, 8, seed=4)
    solid = [int((np.array(f)[:, :, 3] > 0).sum()) for f in frames]
    assert solid[0] == int((np.array(rock)[:, :, 3] > 0).sum())
    assert solid[-1] < solid[0] * 0.1


def test_sentries_grow_with_tier_and_turrets_share_a_canvas():
    sizes = [I.sentry_base(t).size for t in (1, 2, 3)]
    assert sizes[0][0] < sizes[1][0] < sizes[2][0]
    for kind in I.SENTRY_KINDS:
        assert I.turret_interior(kind).size == I.TURRET_CANVAS
        for style in ("shape", "blue"):
            assert I.sentry_shot(kind, style=style).getbbox()


def test_missiles_show_on_the_pods_and_the_left_empties_first():
    assert I.pods_split(6) == (3, 3)
    assert I.pods_split(5) == (2, 3)
    assert I.pods_split(0) == (0, 0)
    assert _count(I.player_interior_loaded(6), "ion_hi") - _count(I.player_interior_loaded(0), "ion_hi") == 6


def test_boost_flame_gets_longer_each_level():
    lengths = [I.boost_flame(level, 1).getbbox()[3] for level in (1, 2, 3)]
    assert lengths[0] < lengths[1] < lengths[2]


def test_mine_blast_frames_and_states():
    for state in ("laid", "armed", "triggered"):
        assert I.mine(0, state).size == (13, 13)
    full = I.mine_blast(2, 40)
    assert _count(full, "ion_white") > 0 and _count(full, "ion_dark") > 0


def test_station_pages_and_console_render():
    for page in station.PAGES:
        assert station.page_panel(page).size == (station.PANEL_W, station.PANEL_H)
    early = hud.campaign_console(weapons=("auto",), shield_level=0, boost_level=0, mines=0, sentries=0)
    full = hud.campaign_console(weapons=("auto", "sniper", "missiles", "laser"), current="laser")
    assert early.height < full.height
    for kind in ("shield", "armor", "boost", "repair", "drill", "mine", "sentry_auto", "sentry_sniper",
                 "sentry_missile", "auto", "sniper", "missiles", "laser"):
        icon = hud.item_icon(kind)
        assert icon.width <= 17 and icon.height <= 19


def test_wrap_fits_the_pane():
    lines = station.wrap("PLACE IT ANYWHERE. IT NEVER MOVES, BUT ENEMIES CAN DESTROY IT.", 120)
    from art import pixfont
    assert len(lines) > 1 and all(pixfont.text_width(line) <= 120 for line in lines)
