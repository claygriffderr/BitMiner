"""Sprint 8: the 3-level upgrades, explosive mines and sentries in Secure the Base."""

import math

import pytest

from bitminer.combat.campaign import Campaign
from bitminer.combat.specs import MINES, SENTRIES, SHOP, WEAPONS
from bitminer.flight import Controls
from bitminer.settings import Tuning

DT = 1 / 60
UP = SHOP["upgrades"]


class Quiet:
    def burst(self, *a, **k):
        pass

    def emit(self, *a, **k):
        pass


def campaign(credits: int = 0) -> Campaign:
    game = Campaign(Quiet(), Quiet(), Tuning(), scale=3)
    game.credits = credits
    return game


def open_space(game: Campaign, dx: float = 1500.0) -> None:
    """Move the ship out into open space, clear of the station and asteroids."""
    st = game.stage
    st.ship.x += dx
    for _ in range(40):
        if not game.defenses.sentry_room(st.ship.x, st.ship.y):
            break
        st.ship.x += 37
        st.ship.y += 23
    st.recentre()


# ------------------------------------------------------------ upgrades


def test_upgrades_go_up_one_level_at_a_time_at_rising_prices():
    game = campaign(100_000)
    for key in ("shield", "armor", "boost", "auto"):
        prices = [int(p) for p in UP[key]["prices"]]
        assert prices == sorted(prices) and prices[2] > prices[0] * 4
        for lv in range(3):
            o = game.shop.offer(key)
            assert o.upgrade and o.level == lv and o.price == prices[lv]
            assert game.shop.buy(key)
        assert game.gear.level(key) == 3
        assert game.shop.offer(key).blocked == "MAX" and not game.shop.buy(key)


def test_you_start_with_no_shield_and_buying_one_charges_it():
    game = campaign(10_000)
    st = game.stage
    assert st.shield_max == 0 and st.shield == 0
    game.shop.buy("shield")
    assert st.shield_max == UP["shield"]["strength"][0] and st.shield == st.shield_max
    assert st.shield_level == 1
    game.shop.buy("shield")
    assert st.shield_max == UP["shield"]["strength"][1] and st.shield_level == 2


def test_stronger_shields_recharge_more_slowly():
    up = UP["shield"]
    assert list(up["delay"]) == sorted(up["delay"])
    assert list(up["regen"]) == sorted(up["regen"], reverse=True)


def test_armor_stops_more_of_each_hit_and_adds_mass():
    game = campaign(100_000)
    st = game.stage
    start = st.armor_factor
    assert start == pytest.approx(1 - UP["armor"]["block"][0])
    game.shop.buy("armor")
    assert st.armor_factor < start
    st.invulnerable = 0
    before = st.hull
    st.damage_player(10, st.ship.x + 5, st.ship.y)
    assert before - st.hull == pytest.approx(10 * (1 - UP["armor"]["block"][1]))
    assert game.gear.flight(game.tuning).mass == pytest.approx(game.tuning.mass * UP["armor"]["mass"][1])


def test_auto_cannon_and_sniper_hit_harder_and_the_sniper_pierces_more():
    game = campaign(100_000)
    st = game.stage
    game.shop.buy("auto")
    st.fire_auto()
    assert st.shots[-1].damage == pytest.approx(WEAPONS["auto"]["damage"] * UP["auto"]["damage"][0])
    game.shop.buy("sniper")                      # the gun first
    assert game.shop.offer("sniper").level == 0
    game.shop.buy("sniper")
    game.shop.buy("sniper")
    st.fire_sniper()
    shot = st.shots[-1]
    assert shot.damage == pytest.approx(WEAPONS["sniper"]["damage"] * UP["sniper"]["damage"][1])
    assert shot.pierce == UP["sniper"]["pierce"][1] == 5


def test_boost_needs_buying_drains_while_held_and_refills_after_a_pause():
    game = campaign(100_000)
    gear = game.gear
    fly = Controls(forward=True)
    game.step(DT, fly, False, None, boost=True)
    assert not gear.boosting and gear.boost == 1.0
    game.shop.buy("boost")
    game.step(DT, Controls(), False, None, boost=True)
    assert not gear.boosting                     # only while you fly
    for _ in range(round(1.0 / DT)):
        game.step(DT, fly, False, None, boost=True)
    assert gear.boosting and gear.boost == pytest.approx(1 - 1.0 / UP["boost"]["seconds"], abs=0.03)
    tuned = gear.flight(game.tuning)
    assert tuned.top_speed == pytest.approx(game.tuning.top_speed * (1 + UP["boost"]["gain"][0]))
    low = gear.boost
    for _ in range(round((UP["boost"]["delay"] - 0.3) / DT)):
        game.step(DT, Controls(), False, None)
    assert gear.boost == pytest.approx(low)      # still waiting out the pause
    for _ in range(round((UP["boost"]["refill"] + 0.6) / DT)):
        game.step(DT, Controls(), False, None)
    assert gear.boost == 1.0


def test_boosting_makes_the_ship_faster():
    speeds = []
    for boost in (False, True):
        game = campaign(100_000)
        for _ in range(3):
            game.shop.buy("boost")
        open_space(game)
        ship = game.stage.ship
        ship.angle = 90.0
        for _ in range(round(1.5 / DT)):
            game.step(DT, Controls(forward=True, aim=90.0), False, None, boost=boost)
        speeds.append(math.hypot(ship.vx, ship.vy))
    assert speeds[1] > speeds[0] * 1.3


# ------------------------------------------------------------ mines


def test_mines_one_at_a_time_up_to_five():
    game = campaign(10_000)
    most = int(SHOP["items"]["mine"]["max"])
    while game.shop.can_buy("mine"):
        game.shop.buy("mine")
    assert game.defenses.mines_carried == most and game.shop.offer("mine").blocked == "FULL"


def test_holding_g_lays_mines_one_after_another_behind_you():
    game = campaign(10_000)
    open_space(game)
    for _ in range(3):
        game.shop.buy("mine")
    st = game.stage
    events = []
    for _ in range(round(0.2 / DT)):
        events += game.step(DT, Controls(), False, None, lay_mines=True)
    assert len(st.mines) == 1                    # one, then a gap
    for _ in range(round(1.0 / DT)):
        events += game.step(DT, Controls(), False, None, lay_mines=True)
    assert len(st.mines) == 3 and game.defenses.mines_carried == 0
    assert sum(1 for ev in events if ev[0] == "mine_laid") == 3
    for m in st.mines:
        assert math.hypot(m.x - st.ship.x, m.y - st.ship.y) < MINES["behind"] + MINES["pile_spread"] * 2


def mine_game():
    game = campaign(10_000)
    open_space(game)
    game.shop.buy("mine")
    m = game.defenses.lay_mine()
    for _ in range(round((MINES["arm_time"] + 0.1) / DT)):
        game.step(DT, Controls(), False, None)
    assert m.state == "armed"
    return game, m


def test_a_mine_waits_for_an_enemy_to_fly_right_over_it():
    game, m = mine_game()
    st = game.stage
    e = st.spawn("guard", m.x + 40, m.y, warp=False)       # close, but not over it
    for _ in range(10):
        game.step(DT, Controls(), False, None)
    assert m.state == "armed" and e.health == e.max_health
    e.x, e.y = m.x + 1, m.y
    events = []
    for _ in range(round((MINES["fuse"] + 0.1) / DT)):
        events += game.step(DT, Controls(), False, None)
    assert ("mine_triggered", m.uid) in events and ("mine_blast", m.uid) in events
    assert not st.mines


def test_the_blast_falls_off_evenly_and_only_hurts_enemies():
    game, m = mine_game()
    st = game.stage
    R = MINES["blast_radius"]
    near = st.spawn("tank", m.x, m.y, warp=False)
    far = st.spawn("tank", m.x + R * 0.5 + st.spawn("tank", 0, 0, warp=False).body_r * 0.5, m.y, warp=False)
    out = st.spawn("tank", m.x + R + 40, m.y, warp=False)
    hull = st.hull
    shield = st.shield
    for _ in range(round((MINES["fuse"] + 0.1) / DT)):
        game.step(DT, Controls(), False, None)
    hit_near = near.max_health - near.health
    hit_far = far.max_health - far.health
    assert hit_near == pytest.approx(MINES["damage"], rel=0.05)
    assert hit_far == pytest.approx(MINES["damage"] * 0.5, rel=0.1)
    assert out.health == out.max_health
    assert st.hull == hull and st.shield == shield


def test_your_ship_never_sets_off_your_mines():
    game, m = mine_game()
    st = game.stage
    st.ship.x, st.ship.y = m.x, m.y
    for _ in range(30):
        game.step(DT, Controls(), False, None)
    assert m.state == "armed"


# ------------------------------------------------------------ sentries


def test_sentries_cost_more_for_each_kind_and_tier():
    game = campaign()
    prices = {k: [game.shop.sentry_price(k, t) for t in (1, 2, 3)]
              for k in ("sentry_auto", "sentry_sniper", "sentry_missile")}
    for row in prices.values():
        assert row == sorted(row)
    assert prices["sentry_auto"][0] < prices["sentry_sniper"][0] < prices["sentry_missile"][0]
    for gun in ("auto", "sniper", "missile"):
        health = SENTRIES[gun]["health"]
        assert list(health) == sorted(health) and health[0] < health[2]


def test_buying_a_sentry_at_the_picked_tier_then_placing_it_with_r():
    game = campaign(10_000)
    game.shop.pick_tier("sentry_sniper", 2)
    assert game.shop.offer("sentry_sniper").price == game.shop.sentry_price("sentry_sniper", 2)
    assert game.shop.buy("sentry_sniper")
    assert game.credits == 10_000 - game.shop.sentry_price("sentry_sniper", 2)
    assert game.defenses.carried == [("sniper", 2)]
    open_space(game)
    events = game.step(DT, Controls(), False, None, place_sentry=True)
    s = game.defenses.sentries[0]
    assert s.gun == "sniper" and s.tier == 2 and s.max_health == SENTRIES["sniper"]["health"][1]
    assert any(ev[0] == "sentry_set" for ev in events) and not game.defenses.carried
    assert s in game.stage.structures


def test_no_sentry_on_top_of_home_base_or_another_sentry():
    game = campaign(100_000)
    game.shop.buy("sentry_auto")
    game.shop.buy("sentry_auto")
    st = game.stage
    st.ship.x, st.ship.y = game.base.x + 5, game.base.y
    events = game.step(DT, Controls(), False, None, place_sentry=True)
    assert ("no_room", "sentry", "CROWDED") in events and len(game.defenses.carried) == 2
    open_space(game)
    game.step(DT, Controls(), False, None, place_sentry=True)
    events = game.step(DT, Controls(), False, None, place_sentry=True)
    assert ("no_room", "sentry", "CROWDED") in events and len(game.defenses.sentries) == 1


@pytest.mark.parametrize("gun", ["auto", "sniper", "missile"])
def test_a_sentry_turns_to_the_nearest_enemy_and_kills_it(gun):
    game = campaign(100_000)
    game.shop.buy("sentry_" + gun)
    open_space(game)
    game.step(DT, Controls(), False, None, place_sentry=True)
    s = game.defenses.sentries[0]
    st = game.stage
    st.ship.x += 600                 # get out of the way
    st.recentre()
    e = st.spawn("infantry", s.x - 120, s.y + 60, warp=False)
    events = []
    for _ in range(round(5.0 / DT)):
        events += game.step(DT, Controls(), False, None)
        if not e.alive:
            break
    assert not e.alive
    assert any(ev[0] == "fire" and ev[1] == "sentry_" + gun for ev in events)
    assert any(ev[0] == "kill" and ev[2].startswith("sentry_") for ev in events)
    assert game.credits > 0                      # its kills pay too


def test_sentry_hits_dont_give_your_position_away():
    game = campaign(100_000)
    game.shop.buy("sentry_auto")
    open_space(game)
    game.step(DT, Controls(), False, None, place_sentry=True)
    s = game.defenses.sentries[0]
    st = game.stage
    st.ship.x += 3000
    st.recentre()
    st.spawn("guard", s.x + 80, s.y, warp=False)
    for _ in range(round(1.5 / DT)):
        game.step(DT, Controls(), False, None)
    assert not game.hunt.known


def test_enemies_can_destroy_a_sentry():
    game = campaign(100_000)
    game.shop.buy("sentry_auto")
    open_space(game)
    game.step(DT, Controls(), False, None, place_sentry=True)
    s = game.defenses.sentries[0]
    st = game.stage
    st.damage_structure(s, s.health - 1, s.x, s.y)
    assert s.alive
    st.damage_structure(s, 5, s.x, s.y)
    assert not s.alive and ("struct_lost", "sentry", s.uid) in st.events
    game.step(DT, Controls(), False, None)
    assert not game.defenses.sentries and s not in st.structures


def test_enemies_remember_a_sentry_they_fly_past_and_raid_it():
    game = campaign(100_000)
    game.shop.buy("sentry_auto")
    open_space(game)
    game.step(DT, Controls(), False, None, place_sentry=True)
    s = game.defenses.sentries[0]
    st = game.stage
    st.ship.x += 3000
    st.recentre()
    game.battle.add("infantry", s.x + 200, s.y, warp=False)
    for _ in range(10):
        game.step(DT, Controls(), False, None)
    assert s.uid in game.hunt.drills


def test_the_most_sentries_you_can_have():
    game = campaign(10_000_000)
    most = int(SENTRIES["max_out"])
    while game.shop.can_buy("sentry_auto"):
        game.shop.buy("sentry_auto")
    assert game.defenses.sentries_carried == most
    assert game.shop.offer("sentry_auto").blocked == "MAX"


def test_the_test_credits_key_adds_credits_and_marks_the_log():
    game = campaign(50)
    assert game.test_credits() == SHOP["test_credits"]
    assert game.credits == 50 + SHOP["test_credits"]
    events = game.step(DT, Controls(), False)
    assert ("test_credits", SHOP["test_credits"]) in events
