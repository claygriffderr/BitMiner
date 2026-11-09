"""Checks on the sprint 9 art: the lasso's tow beam and the collector ring."""

import math

import numpy as np

from art import haul as Hl, hud, pix, sprites as S
from art.palette import rgba


def _count(img, *names):
    a = np.array(img)
    return sum(int(np.all(a == np.array(rgba(n)), axis=2).sum()) for n in names)


def test_four_of_the_largest_rocks_fit_inside_the_field():
    largest = 96
    gap = math.dist(Hl.slot_point((0, 0), 0), Hl.slot_point((0, 0), 1))
    assert gap >= largest                                   # neighbours don't overlap
    assert Hl.SLOT_R + largest / 2 <= Hl.FIELD_R            # and none pokes through the field


def test_ring_has_four_mounts_on_the_outside_and_lit_nodes_turn_gold():
    c = Hl.ring_centre()
    ring = np.array(Hl.collector_ring(0))
    for i in range(4):
        x, y = (int(round(v)) for v in Hl.mount_point((c, c), i))
        assert tuple(ring[y, x]) == rgba("hull_black")      # the turret socket
        assert math.dist((x, y), (c, c)) > Hl.R_OUT
    assert _count(Hl.collector_ring(0), "ore_hi") == 0
    assert _count(Hl.collector_ring(0, lit_nodes=(1,)), "ore_hi") > 0


def test_damage_darkens_the_ring():
    healthy = _count(Hl.collector_ring(0, 1.0), "hull_black")
    hurt = _count(Hl.collector_ring(0, 0.3), "hull_black")
    assert hurt > healthy


def test_beam_is_thicker_at_each_level():
    lit = []
    for lv in (1, 2, 3):
        sc = pix.Scene(40, 60, 1)
        Hl.draw_tow_beam(sc, (20, 5), (20, 55), 0, "A", lv)
        lit.append(int((np.array(sc.base)[:, :, :3] != np.array(rgba("space"))[:3]).any(axis=2).sum()))
    assert lit[0] < lit[1] < lit[2]


def test_shop_icons_exist():
    for kind in ("lasso", "ring"):
        icon = S.tight(hud.item_icon(kind))
        assert icon.width <= 17 and icon.height <= 17
