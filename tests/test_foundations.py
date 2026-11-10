"""Pacing guide sprint A: the game plays the same at any frame rate (towing, fire rates), and
upgrades have as many levels as the data file gives them."""

import pytest

from art import station as ST
from bitminer import selftest
from bitminer.combat import gear
from bitminer.combat.arsenal import Arsenal
from bitminer.combat.campaign import Campaign
from bitminer.combat.specs import SHOP, WEAPONS
from bitminer.combat.stage import Stage
from bitminer.field import SIZES, SLEEP_SPEED, AsteroidField
from bitminer.flight import Controls
from bitminer.selftest import Quiet
from bitminer.settings import Tuning
from bitminer.ui.station_screen import page_content


def campaign(**tuning) -> Campaign:
    game = Campaign(Quiet(), Quiet(), Tuning(**tuning), scale=3)
    game.fleet.timer = 1e9
    return game


def towing(hz: int, boost: int = 0, size: int = max(SIZES)):
    """A game with nothing in it but your ship and one asteroid on the lasso behind it."""
    game = campaign()
    st = game.stage
    f = AsteroidField(game.world.width, game.world.height)
    game.world.field = st.field = f
    game.gear.levels["lasso"] = 3
    game.gear.levels["boost"] = boost
    st.ship.x, st.ship.y, st.ship.angle = 3000.0, 3000.0, 0.0
    f.add(st.ship.x, st.ship.y - 46 - size / 2, size, 0, True)
    game.step(1 / hz, Controls(aim=0.0), False, None, lasso=True)
    assert game.haul.rock == 0
    return game


def seconds_to_tow(game: Campaign, hz: int, distance: float = 1000.0, boost: bool = False, limit: float = 20.0):
    ship = game.stage.ship
    start = ship.uy
    for k in range(int(limit * hz)):
        game.step(1 / hz, Controls(forward=True, aim=0.0), False, None, boost=boost)
        if ship.uy - start >= distance:
            return (k + 1) / hz
    return None


# ------------------------------------------------------------ towing


@pytest.mark.parametrize("hz", [60, 75, 144, 165, 240])
def test_the_biggest_rock_tows_without_boost_at_any_frame_rate(hz):
    t = seconds_to_tow(towing(hz), hz)
    assert t is not None and t == pytest.approx(6.7, abs=0.3)


def test_boost_only_makes_towing_quicker():
    plain = seconds_to_tow(towing(144), 144)
    boosted = seconds_to_tow(towing(144, boost=3), 144, boost=True)
    assert boosted < plain - 0.5


def test_a_rock_on_the_lasso_is_never_put_to_sleep_and_one_let_go_can_be():
    game = towing(240)
    f = game.stage.field
    assert f.held == {0}
    game.step(1 / 240, Controls(forward=True, aim=0.0), False, None)
    speed = (f.vx[0] ** 2 + f.vy[0] ** 2) ** 0.5
    assert 0 < speed < SLEEP_SPEED            # slower than a loose rock is allowed to be, but still moving
    game.step(1 / 240, Controls(aim=0.0), False, None, lasso=True)      # let go
    assert not f.held and game.haul.rock < 0
    game.step(1 / 240, Controls(aim=0.0), False, None)
    assert f.vx[0] == 0 and f.vy[0] == 0


def test_a_towed_rock_that_crumbles_is_no_longer_held():
    game = towing(60)
    f = game.stage.field
    f.remove(0)
    assert not f.held


# ------------------------------------------------------------ fire rates


def shots_fired(weapon: str, hz: int, seconds: float) -> int:
    st = Stage(Quiet(), Quiet())
    arsenal = Arsenal(st, owned=["auto", "sniper"])
    arsenal.select(weapon)
    n = 0
    for _ in range(round(seconds * hz)):
        st.events = []
        arsenal.step(1 / hz, True, None)
        n += sum(1 for ev in st.events if ev == ("fire", weapon))
    return n


@pytest.mark.parametrize("hz", [30, 60, 75, 144, 240])
@pytest.mark.parametrize("weapon", ["auto", "sniper"])
def test_guns_fire_at_their_set_rate_at_any_frame_rate(weapon, hz):
    seconds = 20.0
    want = WEAPONS[weapon]["fire_rate"] * seconds
    assert shots_fired(weapon, hz, seconds) == pytest.approx(want + 1, abs=1)      # one leaves on the press


def test_a_fast_gun_fires_more_than_once_in_a_long_frame(monkeypatch):
    monkeypatch.setitem(WEAPONS["auto"], "fire_rate", 50)
    assert shots_fired("auto", 20, 10.0) == pytest.approx(500, abs=3)       # 2 or 3 leave each frame


def test_time_spent_not_firing_is_not_saved_up():
    st = Stage(Quiet(), Quiet())
    arsenal = Arsenal(st, owned=["auto"])
    for _ in range(120):
        arsenal.step(1 / 60, False, None)
    st.events = []
    arsenal.step(1 / 60, True, None)
    assert st.events.count(("fire", "auto")) == 1
    assert arsenal.cooldown == pytest.approx(1 / WEAPONS["auto"]["fire_rate"])


def test_a_late_shot_flies_the_part_of_the_frame_it_missed():
    st = Stage(Quiet(), Quiet())
    arsenal = Arsenal(st, owned=["auto"])
    arsenal.step(1 / 60, True, None)
    assert st.shots[-1].lead == 0.0           # the first shot leaves on the press
    leads = []
    for _ in range(30):
        before = len(st.shots)
        arsenal.step(1 / 60, True, None)
        leads += [s.lead for s in st.shots[before:]]
    assert leads and all(0.0 <= v <= 1 / 60 + 1e-9 for v in leads) and any(v > 0 for v in leads)
    shot = st.shots[-1]
    shot.lead = 0.01
    x0, y0, life = shot.x, shot.y, shot.life
    st._step_shots(1 / 60)
    flown = ((shot.x - x0) ** 2 + (shot.y - y0) ** 2) ** 0.5
    speed = (shot.vx ** 2 + shot.vy ** 2) ** 0.5
    assert flown == pytest.approx(speed * (1 / 60 + 0.01)) and shot.lead == 0.0
    assert shot.life == pytest.approx(life - 1 / 60 - 0.01)


def test_the_frame_rate_check_passes_and_is_in_the_self_test():
    results = selftest.frame_rate_check(seconds=4.0)
    assert set(results) == set(selftest.RATES) == {60, 144, 240}
    tows = [r["tow"] for r in results.values()]
    assert max(tows) - min(tows) <= 0.02 * max(tows)


def test_the_frame_rate_check_fails_when_the_rates_disagree(monkeypatch):
    real = selftest.frame_rate_scene

    def skewed(hz, seconds=6.0):
        r = real(hz, 2.0)
        if hz == 240:
            r["tow"] *= 0.9
        return r

    monkeypatch.setattr(selftest, "frame_rate_scene", skewed)
    with pytest.raises(AssertionError, match="tow differs"):
        selftest.frame_rate_check()


# ------------------------------------------------------------ upgrade levels


def test_every_upgrade_has_as_many_levels_as_prices():
    game = campaign()
    for key, up in SHOP["upgrades"].items():
        assert gear.max_level(key) == len(up["prices"])
        assert key in game.gear.levels


def test_a_one_level_upgrade_is_bought_once_and_then_maxed(monkeypatch):
    monkeypatch.setitem(SHOP["upgrades"], "lasso", {"prices": [500], "max_size": [96]})
    game = campaign()
    game.credits = 5000
    assert gear.max_level("lasso") == 1
    assert game.shop.offer("lasso").price == 500
    assert game.shop.buy("lasso") and game.gear.level("lasso") == 1 and game.credits == 4500
    o = game.shop.offer("lasso")
    assert o.price is None and o.blocked == "MAX" and not game.shop.buy("lasso")
    assert game.haul.max_size(game.gear.level("lasso")) == 96


@pytest.mark.parametrize("levels", [1, 2, 3, 4])
def test_the_station_shows_an_upgrade_with_any_number_of_levels(monkeypatch, levels):
    prices = [300, 900, 2700, 5000][:levels]
    monkeypatch.setitem(SHOP["upgrades"], "boost", {**SHOP["upgrades"]["boost"], "prices": prices,
                                                    "gain": [0.2, 0.4, 0.8, 1.0][:levels]})
    game = campaign()
    sel = 2                                    # the boost row on the Ship page
    for owned in range(levels + 1):
        game.gear.levels["boost"] = owned
        rows, det = page_content(game, "ship", sel)
        assert rows[sel].kind == "boost" and rows[sel].level == owned and rows[sel].levels == levels
        assert len(det.steps) == levels
        assert [s.state for s in det.steps].count("owned") == owned
        if owned == levels:
            assert det.subtitle == f"LEVEL {levels} OF {levels}" and det.price is None
        img = ST.station_panel("ship", rows, sel, det, game.credits)
        assert img.size == (ST.PANEL_W, ST.PANEL_H)
