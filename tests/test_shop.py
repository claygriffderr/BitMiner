"""The station shop, limited missiles, the laser's charge-up and the station screen's contents."""

import pytest

from bitminer.combat.arsenal import Arsenal
from bitminer.combat.campaign import Campaign
from bitminer.combat.sandbox import Sandbox
from bitminer.combat.shop import PAGE_ITEMS, PAGES, Shop
from bitminer.combat.specs import SHOP, WEAPONS
from bitminer.combat.stage import Stage
from bitminer.flight import Controls, angle_to
from bitminer.settings import Tuning

DT = 1 / 60


class Quiet:
    def burst(self, *a, **k):
        pass

    def emit(self, *a, **k):
        pass


def campaign() -> Campaign:
    return Campaign(Quiet(), Quiet(), Tuning(), scale=3)


def price(key: str) -> int:
    return int(SHOP["items"][key]["price"])


# ------------------------------------------------------------ buying


def test_you_cant_buy_what_you_cant_afford():
    game = campaign()
    game.credits = price("sniper") - 1
    assert not game.shop.buy("sniper")
    assert game.credits == price("sniper") - 1 and "sniper" not in game.arsenal.owned


def test_buying_a_weapon_puts_it_in_your_hands_once():
    game = campaign()
    game.credits = 10_000
    assert game.shop.buy("sniper") and game.shop.buy("laser")
    assert game.arsenal.owned == ["auto", "sniper", "laser"]
    assert game.credits == 10_000 - price("sniper") - price("laser")
    assert game.shop.offer("sniper").blocked == "OWNED" and not game.shop.buy("sniper")
    assert game.arsenal.charges == game.arsenal.laser_max


def test_missiles_come_six_at_a_time_up_to_the_most_you_can_carry():
    game = campaign()
    game.credits = 10_000
    st = game.stage
    pack = int(SHOP["items"]["missiles"]["pack"])
    most = int(SHOP["items"]["missiles"]["max"])
    assert game.shop.buy("missiles")
    assert "missile" in game.arsenal.owned and st.missiles_total == pack and st.missiles_loaded == min(6, pack)
    while game.shop.can_buy("missiles"):
        game.shop.buy("missiles")
    assert st.missiles_total <= most and st.missiles_total + pack > most
    assert game.shop.offer("missiles").blocked == "FULL"


def test_drills_up_to_the_most_you_can_own():
    game = campaign()
    game.credits = 100_000
    most = int(SHOP["items"]["drill"]["max"])
    while game.shop.can_buy("drill"):
        game.shop.buy("drill")
    assert game.drills_carried == most and game.shop.offer("drill").blocked == "MAX"


def test_no_free_drill_when_you_are_broke():
    game = campaign()
    game.drills_carried = 0
    game.credits = 20
    assert game.shop.offer("drill").price == price("drill")
    assert not game.shop.buy("drill") and game.drills_carried == 0 and game.credits == 20


@pytest.mark.parametrize("kind", ["infantry", "rapid", "guard", "tank"])
def test_each_kill_pays_credits_the_moment_it_goes_down(kind):
    game = campaign()
    st = game.stage
    pay = int(SHOP["kill_credits"][kind])
    st.ship.x += 1500                  # out in open space, clear of the station
    e = st.spawn(kind, st.ship.x + 120, st.ship.y, warp=False)
    e.health = 1.0
    game.arsenal.own("sniper")
    game.arsenal.select("sniper")
    events = []
    for _ in range(round(1.5 / DT)):
        aim = angle_to(e.x - st.ship.x, e.y - st.ship.y)
        events += game.step(DT, Controls(aim=aim), True, (e.x, e.y))
        if game.kills:
            break
    assert game.kills == 1 and game.credits == pay
    assert any(ev[:3] == ("bounty", kind, pay) for ev in events)


def test_kill_credits_follow_how_dangerous_the_enemy_is():
    pay = SHOP["kill_credits"]
    assert pay["infantry"] == 3 and pay["guard"] == 5 and pay["tank"] == 50
    assert pay["infantry"] < pay["guard"] < pay["tank"] < pay["mothership"]


def test_health_patches_half_your_hull_and_only_when_hurt():
    game = campaign()
    st = game.stage
    game.credits = 1000
    assert game.shop.offer("repair").blocked == "FULL"
    st.hull = st.hull_max * 0.2
    assert game.shop.buy("repair")
    assert st.hull == pytest.approx(st.hull_max * (0.2 + SHOP["items"]["repair"]["restores"]))
    st.hull = st.hull_max * 0.9
    game.shop.buy("repair")
    assert st.hull == pytest.approx(st.hull_max)


def test_upgrades_mines_and_sentries_are_coming_soon():
    game = campaign()
    game.credits = 100_000
    for key in ("shield", "armor", "boost", "mine", "sentry_auto", "sentry_sniper", "sentry_missile"):
        assert game.shop.offer(key).soon and not game.shop.buy(key)


def test_purchases_show_up_in_the_next_steps_events():
    game = campaign()
    game.credits = 1000
    game.shop.buy("sniper")
    events = game.step(DT, Controls(), False, None)
    assert ("bought", "sniper", price("sniper")) in events


def test_every_page_lists_its_items():
    game = campaign()
    for page in PAGES:
        assert [o.key for o in game.shop.offers(page)] == list(PAGE_ITEMS[page])
    assert Shop.item("drill")["price"] == price("drill")


# ------------------------------------------------------------ missiles you carry


def test_limited_missiles_run_out_and_reload_from_what_you_carry():
    st = Stage(Quiet(), Quiet())
    st.set_missiles(8)
    assert st.missiles_loaded == 6 and st.missile_stock == 2
    fired = 0
    for _ in range(round(12 / DT)):
        if st.missile_ready:
            st.fire_missile(None)
            fired += 1
        st.step(DT)
    assert fired == 8 and st.missiles_total == 0 and not st.missile_ready


def test_the_sandbox_never_runs_out_of_missiles():
    st = Stage(Quiet(), Quiet())
    assert st.missiles_total is None
    for _ in range(3):
        st.fire_missile(None)
        st.missile_wait = 0
    st.missile_idle = 99
    st.step(DT)
    assert st.missiles_loaded == int(WEAPONS["missile"]["salvo"])


def test_firing_with_no_missiles_says_so():
    game = campaign()
    game.arsenal.own("missile")
    game.arsenal.select("missile")
    events = game.step(DT, Controls(), True, None)
    events += game.step(DT, Controls(), True, None)
    assert ("empty", "missile") in events


# ------------------------------------------------------------ the laser's charge-up


def laser_game() -> Campaign:
    game = campaign()
    game.arsenal.own("laser")
    game.arsenal.select("laser")
    game.stage.ship.x += 1500          # out in open space, clear of the station
    return game


def test_the_laser_fires_after_a_two_second_charge():
    game = laser_game()
    charge = float(WEAPONS["laser"]["charge_time"])
    events = []
    for _ in range(round((charge - 0.2) / DT)):
        events += game.step(DT, Controls(), True, None)
    assert ("charge", "laser") in events and not any(ev == ("fire", "laser") for ev in events)
    assert game.arsenal.charging and game.stage.charging > 0.8
    for _ in range(round(0.4 / DT)):
        events += game.step(DT, Controls(), True, None)
    assert ("fire", "laser") in events and not game.arsenal.charging
    assert game.arsenal.charges == game.arsenal.laser_max - 1
    beam = game.arsenal.beam
    assert beam.burst > 0 and beam.warmup == 0


def test_letting_go_early_cancels_without_using_a_charge():
    game = laser_game()
    events = []
    for _ in range(round(1.0 / DT)):
        events += game.step(DT, Controls(), True, None)
    events += game.step(DT, Controls(), False, None)
    assert ("cancel", "laser") in events and not game.arsenal.charging
    assert game.arsenal.charges == game.arsenal.laser_max
    assert game.stage.charge_cancel > 0 and not game.stage.beams


def test_your_ship_holds_still_but_can_turn_while_charging():
    game = laser_game()
    ship = game.stage.ship
    ship.vx, ship.vy = 120.0, 0.0
    game.step(DT, Controls(), True, None)
    for _ in range(round(1.5 / DT)):
        game.step(DT, Controls(forward=True, aim=90.0), True, None)
    assert abs(ship.vx) < 5 and abs(ship.vy) < 5
    assert abs(ship.angle - 90.0) < 5


def test_the_gallery_laser_fires_straight_away():
    st = Stage(Quiet(), Quiet())
    ars = Arsenal(st, unlimited_laser=True)
    ars.select("laser")
    ars.step(DT, True)
    assert st.beams and not ars.charging


def test_the_sandbox_laser_charges_too():
    sb = Sandbox(Quiet(), Quiet(), Tuning())
    sb.arsenal.select("laser")
    sb.step(DT, Controls(), True, None)
    assert sb.arsenal.charging


def test_you_can_only_pick_weapons_you_own():
    game = campaign()
    game.arsenal.select("laser")
    assert game.arsenal.weapon == "auto"
    game.arsenal.cycle(1)
    assert game.arsenal.weapon == "auto"
    game.arsenal.own("sniper")
    game.arsenal.cycle(1)
    assert game.arsenal.weapon == "sniper"


# ------------------------------------------------------------ the station screen's contents


def test_every_page_of_the_station_screen_renders():
    from art import station as ST
    from bitminer.ui.station_screen import page_content
    game = campaign()
    game.credits = 260
    game.stage.hull *= 0.5
    for page in PAGES:
        for sel in range(len(PAGE_ITEMS[page])):
            rows, det = page_content(game, page, sel)
            spots = {}
            img = ST.station_panel(page, rows, sel, det, game.credits, spots=spots)
            assert img.size == (ST.PANEL_W, ST.PANEL_H)
            assert len(spots["rows"]) == len(rows) and len(spots["tabs"]) == 3 and "buy" in spots
