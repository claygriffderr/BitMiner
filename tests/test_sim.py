"""Pacing guide sprint A: the balance simulator. A bot plays Secure the Base with no graphics through
the same controls you have, and a report judges the pacing marks in `data/sim.json`."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from bitminer.combat.campaign import Campaign
from bitminer.combat.specs import SHOP
from bitminer.combat.stage import dist
from bitminer.selftest import Quiet
from bitminer.settings import Tuning
from bitminer.sim import load_spec
from bitminer.sim.__main__ import main, parse
from bitminer.sim.bot import RING_STAND, Act, Bot, parse_item
from bitminer.sim.report import judge, render, summarise
from bitminer.sim.run import crossover, marks, play, run_batch

SPEC = load_spec()
RATE = 30


def scene(buy=(), seed: int = 1, plan=None, preset: str = "motivated"):
    """A full-size game with no waves, the things in `buy` already bought, and a bot to play it."""
    game = Campaign(Quiet(), Quiet(), Tuning(), seed=seed)
    game.fleet.timer = 1e9
    game.credits = 10 ** 6
    for key in buy:
        assert game.shop.buy(key), key
    game.credits = 0
    bot = Bot(game, SPEC["presets"][preset], plan or {"early": []}, SPEC["bot"], seed=seed)
    return game, bot


def run(game, bot, seconds: float) -> list:
    """Let the bot play for `seconds`; returns everything that happened."""
    seen, events = [], []
    for _ in range(int(seconds * RATE)):
        act = bot.act(1 / RATE, events)
        events = game.step(1 / RATE, act.controls, act.trigger, act.cursor, set_drill=act.set_drill,
                           boost=act.boost, lay_mines=act.lay_mines, place_sentry=act.place_sentry,
                           lasso=act.lasso, ring_key=act.ring_key)
        seen += events
    return seen


@pytest.fixture(scope="module")
def short_game() -> dict:
    return play(seed=1, minutes=4)


# ------------------------------------------------------------ the data file

def test_the_data_file_explains_itself_and_has_the_three_players():
    assert len(SPEC["about"]) > 200
    assert set(SPEC["presets"]) == {"careful", "average", "motivated"}
    keys = {"aim_error", "pause", "shop_seconds", "cruise", "tow_speed", "engage", "keep", "sniper_from", "repair_at"}
    for preset in SPEC["presets"].values():
        assert set(preset) == keys


def test_the_shopping_list_only_names_things_the_guide_plans_for():
    known = set(SHOP["items"]) | set(SHOP["upgrades"]) | {"drill_yield"}
    for phase, items in SPEC["plan"].items():
        assert phase in ("early", "mid", "late")
        for item in items:
            key, tier = parse_item(item)
            assert key in known, item
            assert tier is None or 1 <= tier <= 3


def test_every_pass_mark_is_something_a_game_measures(short_game):
    for mark in SPEC["marks"]:
        assert mark["key"] in short_game["marks"]
        assert mark["low"] <= mark["high"]
        assert mark["unit"] in ("min", "deaths")


def test_shopping_list_items_with_a_tier():
    assert parse_item("sentry_missile:3") == ("sentry_missile", 3)
    assert parse_item("drill") == ("drill", None)


# ------------------------------------------------------------ one game

def test_a_game_reports_everything_the_guide_asks_for(short_game):
    g = short_game
    assert len(g["mining"]) == len(g["combat"]) == len(g["out"]) == len(g["balance"]) == 4
    assert sum(g["mining"]) > 200                 # one drill digs 120 a minute
    assert g["purchases"][0]["key"] == "sniper" and g["bought"]["sniper"] < 3.0
    assert g["waves"][0]["n"] == 1 and g["waves"][0]["size"] == 3
    assert g["waves"][0]["killed"] + g["waves"][0]["home"] <= 3
    assert sum(g["kills"].values()) >= 1 and sum(g["combat"]) > 0
    assert g["step_ms"]["mean"] > 0 and g["step_ms"]["worst_second"] >= g["step_ms"]["mean"]
    assert abs(sum(g["time_in"].values()) - 240.0) < 0.5
    assert g["marks"]["earned"] == sum(g["mining"]) + sum(g["combat"])
    json.dumps(g)                                 # plain numbers and lists all the way down


def test_the_same_map_plays_out_the_same_way_twice():
    a, b = play(seed=3, minutes=2), play(seed=3, minutes=2)
    for key in ("mining", "combat", "out", "balance", "purchases", "waves", "deaths", "kills", "time_in"):
        assert a[key] == b[key], key


def test_a_different_map_is_a_different_game():
    a, b = play(seed=3, minutes=2), play(seed=4, minutes=2)
    assert a["time_in"] != b["time_in"]


def test_something_the_shop_does_not_sell_yet_is_skipped_and_reported():
    game, bot = scene(plan={"early": ["drill_yield", "sniper"]})
    game.credits = 500
    run(game, bot, 20)
    assert bot.skipped == ["drill_yield"]
    assert "sniper" in game.arsenal.owned
    assert "early" in bot.done_at


# ------------------------------------------------------------ the bot at work

def test_the_bot_only_uses_the_controls_a_player_has():
    game, bot = scene()
    act = bot.act(1 / RATE)
    assert isinstance(act, Act)
    assert set(vars(act)) == {"controls", "trigger", "cursor", "set_drill", "boost", "lay_mines", "place_sentry",
                              "lasso", "ring_key"}


def test_the_bot_sets_its_drill_and_sells_ore_by_hand():
    game, bot = scene(buy=["drill", "drill"])
    seen = run(game, bot, 150)
    assert len(game.drills) == 3
    assert sum(ev[2] for ev in seen if ev[0] == "unload") > 300      # three drills dig 360 a minute


def test_the_bot_sets_the_ring_tows_ore_into_it_and_lets_it_sell():
    game, bot = scene(buy=["drill"] * 3 + ["lasso"] * 3 + ["ring", "boost"])
    seen = run(game, bot, 150)
    ring = game.haul.ring
    assert game.haul.has_ring() and game.haul.rings_carried == 0
    caught = [ev for ev in seen if ev[0] == "ring_caught"]
    assert any(bot.ore_left(i) > 0 or game.stage.field.gone[i] for i in ring.slots if i >= 0) or caught
    assert sum(ev[1] for ev in seen if ev[0] == "ring_sale") > 200
    assert bot.time_in.get("tow", 0) > 5


def test_the_bot_pulls_a_useless_rock_out_of_the_ring():
    game, bot = scene(buy=["lasso"] * 3 + ["ring"])
    run(game, bot, 12)
    ring = game.haul.ring
    assert game.haul.has_ring()
    f = game.stage.field
    junk = next(i for i in range(len(f.size)) if not f.ore[i] and f.size[i] == 32 and not f.gone[i])
    f.x[junk], f.y[junk] = ring.x % f.width, ring.y % f.height      # a plain rock drifts in
    f.vx[junk] = f.vy[junk] = 0.0
    f._refile(junk)
    bot.h = {**bot.h, "tow_range": 0}             # nothing to tow: only the clearing job is left
    seen = run(game, bot, 3)
    assert junk in ring.slots
    seen += run(game, bot, 40)
    assert junk not in ring.slots
    assert bot.time_in.get("clear", 0) > 0


def test_the_bot_looks_further_out_once_the_ore_near_home_is_gone():
    game, bot = scene()
    bot.h = {**bot.h, "mine_range": 60, "range_grow": 2.0, "range_max": 4000}
    assert list(bot._reaches("mine_range")) == [60, 120, 240, 480, 960, 1920, 3840, 4000]
    far = bot._drill_rock()
    assert far is not None and bot.ore_left(far) > 0
    bot.h = {**bot.h, "range_max": 60}
    assert list(bot._reaches("mine_range")) == [60]
    assert bot._drill_rock() is None              # nothing that near, and it may not look further
    bot.h = {**bot.h, "mine_range": 0}
    assert list(bot._reaches("mine_range")) == [0]


def test_the_bot_leaves_the_ring_to_fight():
    game, bot = scene(buy=["ring"])
    run(game, bot, 12)
    ring = game.haul.ring
    assert game.haul.has_ring()
    ship = game.stage.ship
    ship.x, ship.y, ship.vx, ship.vy = ring.x, ring.y, 0.0, 0.0
    game.stage.recentre()
    ring = game.haul.ring
    foe = game.stage.spawn("guard", ring.x + 330.0, ring.y + 40.0, warp=False)
    foe.immune = True
    run(game, bot, 4)
    ring = game.haul.ring
    assert dist(ship.x, ship.y, ring.x, ring.y) > RING_STAND - 40.0      # out of the ring, clear of its rocks
    assert bot.time_in.get("fight", 0) > 3


def test_the_bot_fights_what_comes_at_it():
    game, bot = scene()
    game.fleet.call_now()
    seen = run(game, bot, 150)
    assert sum(1 for ev in seen if ev[0] == "kill") >= 2
    assert bot.time_in.get("fight", 0) > 3


def test_a_careful_player_wastes_more_time_than_a_motivated_one():
    careful, keen = play(seed=2, preset="careful", minutes=4), play(seed=2, preset="motivated", minutes=4)
    assert careful["time_in"].get("pause", 0) > 2 * keen["time_in"].get("pause", 0)
    visits = lambda g: sum(1 for p in g["purchases"])
    assert careful["time_in"]["shop"] / max(1, visits(careful)) > keen["time_in"]["shop"] / max(1, visits(keen))


# ------------------------------------------------------------ the marks and the report

def test_combat_passes_mining_at_the_end_of_the_first_stretch_it_stays_ahead():
    mining = [100] * 10
    assert crossover(mining, [0] * 10, 5) is None
    assert crossover(mining, [0, 0, 0, 0, 0, 200, 200, 200, 200, 200], 5) == 8.0
    assert crossover(mining, [500, 500, 0, 0, 0, 0, 0, 0, 0, 0], 5) is None       # ahead early, then behind
    assert crossover([0] * 10, [0] * 10, 5) is None


def test_marks_come_from_what_was_bought_and_when():
    result = {"purchases": [{"t": 3000.0, "key": "sentry_missile", "price": 7200, "step": 3},
                            {"t": 3100.0, "key": "sentry_missile", "price": 3200, "step": 1},
                            {"t": 3300.0, "key": "sentry_missile", "price": 7200, "step": 3}],
              "waves": [{"n": 29, "t": 1700.0}, {"n": 30, "t": 1800.0}], "deaths": [100.0, 1900.0],
              "mining": [100] * 60, "combat": [0] * 60}
    m = marks(result, {"early": 600.0, "mid": 1800.0}, SPEC)
    assert m["early_done"] == 10.0 and m["mid_done"] == 30.0 and m["late_done"] is None
    assert m["two_missile_t3"] == 55.0
    assert m["wave_30"] == 30.0 and m["deaths_before_wave_30"] == 1 and m["deaths"] == 2
    assert m["earned"] == 6000


def games_with(key: str, values: list) -> list[dict]:
    return [{"marks": {key: v}} for v in values]


def test_each_mark_is_judged_on_the_median_game():
    mark = {"key": "early_done", "label": "Early list bought", "low": 10, "high": 14, "unit": "min"}
    assert judge(mark, games_with("early_done", [11, 12, 30]))["verdict"] == "PASS"
    assert judge(mark, games_with("early_done", [8, 9, 12]))["verdict"] == "TOO EARLY"
    assert judge(mark, games_with("early_done", [12, 20, 22]))["verdict"] == "TOO LATE"
    rare = judge(mark, games_with("early_done", [12, None, None]))
    assert rare["verdict"] == "NOT REACHED" and rare["reached"] == 1 and rare["value"] is None
    deaths = {"key": "deaths_before_wave_30", "label": "Deaths", "low": 0, "high": 3, "unit": "deaths"}
    assert judge(deaths, games_with("deaths_before_wave_30", [0, 1, 2]))["verdict"] == "PASS"
    assert judge(deaths, games_with("deaths_before_wave_30", [4, 5, 9]))["verdict"] == "TOO MANY"


def test_the_report_covers_the_marks_income_purchases_waves_and_cost(short_game):
    other = play(seed=2, minutes=4)
    summary = summarise([short_game, other], SPEC)
    assert summary["games"] == 2 and summary["seeds"] == [1, 2]
    assert [m["key"] for m in summary["marks"]] == [m["key"] for m in SPEC["marks"]]
    assert summary["income"][0]["mining"] > 0
    assert summary["bought"][0]["item"] == "sniper"
    assert summary["waves"][0]["n"] == 1
    json.dumps(summary)
    text = render(summary)
    for heading in ("# BitMiner balance report: motivated player", "## Pass marks", "## Income",
                    "## When things were bought", "## Waves", "## Deaths", "## Where the time went",
                    "## Cost of a step"):
        assert heading in text
    assert "NOT REACHED" in text and "Early list bought" in text


# ------------------------------------------------------------ the command

def test_the_command_defaults_to_ten_motivated_games():
    args = parse([])
    assert (args.preset, args.seeds, args.first_seed, args.minutes) == ("motivated", 10, 1, None)


def test_the_command_prints_the_report_and_writes_the_files(tmp_path, capsys):
    out, data = tmp_path / "report.md", tmp_path / "games.json"
    assert main(["--seeds", "1", "--minutes", "1", "--jobs", "1", "--out", str(out), "--json", str(data)]) == 0
    printed = capsys.readouterr().out
    assert "## Pass marks" in printed
    assert out.read_text(encoding="utf-8").strip() == printed.strip()
    saved = json.loads(data.read_text(encoding="utf-8"))
    assert len(saved["games"]) == 1 and saved["summary"]["minutes"] == 1


def test_games_can_be_played_side_by_side():
    games = run_batch([1, 2], "motivated", 0.5, jobs=2)
    assert [g["seed"] for g in games] == [1, 2]


def test_the_command_itself_runs_games_side_by_side(tmp_path):
    """Run the way the build runs it: as a program, with worker processes started fresh."""
    done = subprocess.run([sys.executable, "-m", "bitminer.sim", "--seeds", "2", "--minutes", "0.5", "--jobs", "2"],
                          capture_output=True, text=True, timeout=300, cwd=Path(__file__).resolve().parent.parent)
    assert done.returncode == 0, done.stderr[-2000:]
    assert "## Pass marks" in done.stdout and "seeds 1, 2" in done.stdout
